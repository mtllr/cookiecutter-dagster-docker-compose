import re
from typing import Any, Mapping, Optional

import pytest
import yaml
from dagster import (
    _check as check,
    _seven,
    asset,
    execute_job,
    job,
    op,
    reconstructable,
)
from dagster._check import CheckError
from dagster._config import Field
from dagster._core.definitions import build_assets_job
from dagster._core.errors import (
    DagsterHomeNotSetError,
    DagsterInvalidConfigError,
    DagsterInvariantViolationError,
)
from dagster._core.execution.api import create_execution_plan
from dagster._core.instance import DagsterInstance, InstanceRef
from dagster._core.instance.config import DEFAULT_LOCAL_CODE_SERVER_STARTUP_TIMEOUT
from dagster._core.launcher import LaunchRunContext, RunLauncher
from dagster._core.run_coordinator.queued_run_coordinator import QueuedRunCoordinator
from dagster._core.secrets.env_file import EnvFileLoader
from dagster._core.snap import (
    create_execution_plan_snapshot_id,
    create_job_snapshot_id,
    snapshot_from_execution_plan,
)
from dagster._core.storage.sqlite_storage import (
    _event_logs_directory,
    _runs_directory,
    _schedule_directory,
)
from dagster._core.storage.tags import (
    ASSET_PARTITION_RANGE_END_TAG,
    ASSET_PARTITION_RANGE_START_TAG,
)
from dagster._core.test_utils import (
    TestSecretsLoader,
    create_run_for_test,
    environ,
    instance_for_test,
)
from dagster._daemon.asset_daemon import AssetDaemon
from dagster._serdes import ConfigurableClass
from dagster._serdes.config_class import ConfigurableClassData
from typing_extensions import Self

from dagster_tests.api_tests.utils import get_bar_workspace


def test_get_run_by_id():
    instance = DagsterInstance.ephemeral()

    assert instance.get_runs() == []
    run = create_run_for_test(instance, job_name="foo_job", run_id="new_run")

    assert instance.get_runs() == [run]

    assert instance.get_run_by_id(run.run_id) == run


def do_test_single_write_read(instance):
    run_id = "some_run_id"

    @job
    def job_def():
        pass

    instance.create_run_for_job(job_def=job_def, run_id=run_id)
    run = instance.get_run_by_id(run_id)
    assert run.run_id == run_id
    assert run.job_name == "job_def"
    assert list(instance.get_runs()) == [run]
    instance.wipe()
    assert list(instance.get_runs()) == []


def test_filesystem_persist_one_run(tmpdir):
    with instance_for_test(temp_dir=str(tmpdir)) as instance:
        do_test_single_write_read(instance)


def test_partial_storage(tmpdir):
    with instance_for_test(
        overrides={
            "run_storage": {
                "module": "dagster._core.storage.runs",
                "class": "SqliteRunStorage",
                "config": {
                    "base_dir": str(tmpdir),
                },
            }
        }
    ) as _instance:
        pass


def test_unified_storage(tmpdir):
    with instance_for_test(
        overrides={
            "storage": {
                "sqlite": {
                    "base_dir": str(tmpdir),
                }
            }
        }
    ) as _instance:
        pass


@pytest.mark.skipif(_seven.IS_WINDOWS, reason="Windows paths formatted differently")
def test_unified_storage_env_var(tmpdir):
    with environ({"SQLITE_STORAGE_BASE_DIR": str(tmpdir)}):
        with instance_for_test(
            overrides={
                "storage": {
                    "sqlite": {
                        "base_dir": {"env": "SQLITE_STORAGE_BASE_DIR"},
                    }
                }
            }
        ) as instance:
            assert _runs_directory(str(tmpdir)) in instance.run_storage._conn_string  # noqa: SLF001
            assert (
                _event_logs_directory(str(tmpdir))
                == instance.event_log_storage._base_dir + "/"  # noqa: SLF001
            )
            assert (
                _schedule_directory(str(tmpdir))
                in instance.schedule_storage._conn_string  # noqa: SLF001
            )


def test_custom_secrets_manager():
    with instance_for_test() as instance:
        assert isinstance(instance._secrets_loader, EnvFileLoader)  # noqa: SLF001

    with instance_for_test(
        overrides={
            "secrets": {
                "custom": {
                    "module": "dagster._core.test_utils",
                    "class": "TestSecretsLoader",
                    "config": {"env_vars": {"FOO": "BAR"}},
                }
            }
        }
    ) as instance:
        assert isinstance(instance._secrets_loader, TestSecretsLoader)  # noqa: SLF001
        assert instance._secrets_loader.env_vars == {"FOO": "BAR"}  # noqa: SLF001


def test_run_queue_key():
    tag_rules = [
        {
            "key": "database",
            "value": "redshift",
            "limit": 2,
        }
    ]

    config = {"max_concurrent_runs": 50, "tag_concurrency_limits": tag_rules}

    with instance_for_test(overrides={"run_queue": config}) as instance:
        assert isinstance(instance.run_coordinator, QueuedRunCoordinator)
        run_queue_config = instance.run_coordinator.get_run_queue_config()
        assert run_queue_config.max_concurrent_runs == 50
        assert run_queue_config.tag_concurrency_limits == tag_rules

    with instance_for_test(
        overrides={
            "run_coordinator": {
                "module": "dagster.core.run_coordinator",
                "class": "QueuedRunCoordinator",
                "config": config,
            }
        }
    ) as instance:
        assert isinstance(instance.run_coordinator, QueuedRunCoordinator)
        run_queue_config = instance.run_coordinator.get_run_queue_config()
        assert run_queue_config.max_concurrent_runs == 50
        assert run_queue_config.tag_concurrency_limits == tag_rules

    # Can't combine them though
    with pytest.raises(
        DagsterInvalidConfigError,
        match=(
            "Found config for `run_queue` which is incompatible with `run_coordinator` config"
            " entry."
        ),
    ):
        with instance_for_test(
            overrides={
                "run_queue": config,
                "run_coordinator": {
                    "module": "dagster.core.run_coordinator",
                    "class": "QueuedRunCoordinator",
                    "config": config,
                },
            }
        ):
            pass


def test_run_coordinator_key():
    tag_rules = [
        {
            "key": "database",
            "value": "redshift",
            "limit": 2,
        }
    ]

    with instance_for_test(
        overrides={"run_queue": {"max_concurrent_runs": 50, "tag_concurrency_limits": tag_rules}}
    ) as instance:
        assert isinstance(instance.run_coordinator, QueuedRunCoordinator)
        run_queue_config = instance.run_coordinator.get_run_queue_config()
        assert run_queue_config.max_concurrent_runs == 50
        assert run_queue_config.tag_concurrency_limits == tag_rules


def test_in_memory_persist_one_run():
    with DagsterInstance.ephemeral() as instance:
        do_test_single_write_read(instance)


@op
def noop_op(_):
    pass


@job
def noop_job():
    noop_op()


@asset
def noop_asset():
    pass


noop_asset_job = build_assets_job(assets=[noop_asset], name="noop_asset_job")


def test_create_job_snapshot():
    with instance_for_test() as instance:
        result = execute_job(reconstructable(noop_job), instance=instance)
        assert result.success

        run = instance.get_run_by_id(result.run_id)

        assert run.job_snapshot_id == create_job_snapshot_id(noop_job.get_job_snapshot())


def test_create_execution_plan_snapshot():
    with instance_for_test() as instance:
        execution_plan = create_execution_plan(noop_job)

        ep_snapshot = snapshot_from_execution_plan(execution_plan, noop_job.get_job_snapshot_id())
        ep_snapshot_id = create_execution_plan_snapshot_id(ep_snapshot)

        result = execute_job(reconstructable(noop_job), instance=instance)
        assert result.success

        run = instance.get_run_by_id(result.run_id)

        assert run.execution_plan_snapshot_id == ep_snapshot_id
        assert run.execution_plan_snapshot_id == create_execution_plan_snapshot_id(ep_snapshot)


def test_submit_run():
    with instance_for_test(
        overrides={
            "run_coordinator": {
                "module": "dagster._core.test_utils",
                "class": "MockedRunCoordinator",
            }
        }
    ) as instance:
        with get_bar_workspace(instance) as workspace:
            external_job = (
                workspace.get_code_location("bar_code_location")
                .get_repository("bar_repo")
                .get_full_external_job("foo")
            )

            run = create_run_for_test(
                instance=instance,
                job_name=external_job.name,
                run_id="foo-bar",
                external_job_origin=external_job.get_external_origin(),
                job_code_origin=external_job.get_python_origin(),
            )

            instance.submit_run(run.run_id, workspace)

            assert len(instance.run_coordinator.queue()) == 1
            assert instance.run_coordinator.queue()[0].run_id == "foo-bar"


def test_create_run_with_asset_partitions():
    with instance_for_test() as instance:
        execution_plan = create_execution_plan(noop_asset_job)

        ep_snapshot = snapshot_from_execution_plan(
            execution_plan, noop_asset_job.get_job_snapshot_id()
        )

        with pytest.raises(
            Exception,
            match=(
                "Cannot have dagster/asset_partition_range_start or"
                " dagster/asset_partition_range_end set without the other"
            ),
        ):
            create_run_for_test(
                instance=instance,
                job_name="foo",
                execution_plan_snapshot=ep_snapshot,
                job_snapshot=noop_asset_job.get_job_snapshot(),
                tags={ASSET_PARTITION_RANGE_START_TAG: "partition_0"},
            )

        with pytest.raises(
            Exception,
            match=(
                "Cannot have dagster/asset_partition_range_start or"
                " dagster/asset_partition_range_end set without the other"
            ),
        ):
            create_run_for_test(
                instance=instance,
                job_name="foo",
                execution_plan_snapshot=ep_snapshot,
                job_snapshot=noop_asset_job.get_job_snapshot(),
                tags={ASSET_PARTITION_RANGE_END_TAG: "partition_0"},
            )

        create_run_for_test(
            instance=instance,
            job_name="foo",
            execution_plan_snapshot=ep_snapshot,
            job_snapshot=noop_asset_job.get_job_snapshot(),
            tags={ASSET_PARTITION_RANGE_START_TAG: "bar", ASSET_PARTITION_RANGE_END_TAG: "foo"},
        )


def test_get_required_daemon_types():
    from dagster._daemon.daemon import (
        BackfillDaemon,
        MonitoringDaemon,
        SchedulerDaemon,
        SensorDaemon,
    )

    with instance_for_test() as instance:
        assert instance.get_required_daemon_types() == [
            SensorDaemon.daemon_type(),
            BackfillDaemon.daemon_type(),
            SchedulerDaemon.daemon_type(),
            AssetDaemon.daemon_type(),
        ]

    with instance_for_test(
        overrides={
            "run_launcher": {
                "module": "dagster_tests.daemon_tests.test_monitoring_daemon",
                "class": "TestRunLauncher",
            },
            "run_monitoring": {"enabled": True},
        }
    ) as instance:
        assert instance.get_required_daemon_types() == [
            SensorDaemon.daemon_type(),
            BackfillDaemon.daemon_type(),
            SchedulerDaemon.daemon_type(),
            MonitoringDaemon.daemon_type(),
            AssetDaemon.daemon_type(),
        ]

    with instance_for_test(
        overrides={
            "auto_materialize": {"enabled": False},
        }
    ) as instance:
        assert instance.get_required_daemon_types() == [
            SensorDaemon.daemon_type(),
            BackfillDaemon.daemon_type(),
            SchedulerDaemon.daemon_type(),
        ]


class TestNonResumeRunLauncher(RunLauncher, ConfigurableClass):
    def __init__(self, inst_data: Optional[ConfigurableClassData] = None):
        self._inst_data = inst_data
        super().__init__()

    @property
    def inst_data(self):
        return self._inst_data

    @classmethod
    def config_type(cls):
        return {}

    @classmethod
    def from_config_value(
        cls, inst_data: ConfigurableClassData, config_value: Mapping[str, Any]
    ) -> Self:
        return TestNonResumeRunLauncher(inst_data=inst_data)

    def launch_run(self, context):
        raise NotImplementedError()

    def join(self, timeout=30):
        raise NotImplementedError()

    def terminate(self, run_id):
        raise NotImplementedError()

    @property
    def supports_check_run_worker_health(self):
        return True


def test_grpc_default_settings():
    with instance_for_test() as instance:
        assert (
            instance.code_server_process_startup_timeout
            == DEFAULT_LOCAL_CODE_SERVER_STARTUP_TIMEOUT
        )


def test_grpc_override_settings():
    with instance_for_test(overrides={"code_servers": {"local_startup_timeout": 60}}) as instance:
        assert instance.code_server_process_startup_timeout == 60


def test_run_monitoring(capsys):
    with instance_for_test(
        overrides={
            "run_monitoring": {"enabled": True},
        }
    ) as instance:
        assert instance.run_monitoring_enabled

    settings = {"enabled": True}
    with instance_for_test(
        overrides={
            "run_launcher": {
                "module": "dagster_tests.daemon_tests.test_monitoring_daemon",
                "class": "TestRunLauncher",
            },
            "run_monitoring": settings,
        }
    ) as instance:
        assert instance.run_monitoring_enabled
        assert instance.run_monitoring_settings == settings
        assert instance.run_monitoring_max_resume_run_attempts == 0

    settings = {"enabled": True, "max_resume_run_attempts": 5}
    with instance_for_test(
        overrides={
            "run_launcher": {
                "module": "dagster_tests.daemon_tests.test_monitoring_daemon",
                "class": "TestRunLauncher",
            },
            "run_monitoring": settings,
        }
    ) as instance:
        assert instance.run_monitoring_enabled
        assert instance.run_monitoring_settings == settings
        assert instance.run_monitoring_max_resume_run_attempts == 5

    with pytest.raises(CheckError):
        with instance_for_test(
            overrides={
                "run_launcher": {
                    "module": "dagster_tests.core_tests.instance_tests.test_instance",
                    "class": "TestNonResumeRunLauncher",
                },
                "run_monitoring": {"enabled": True, "max_resume_run_attempts": 10},
            },
        ) as _:
            pass


def test_cancellation_thread():
    with instance_for_test(
        overrides={
            "run_monitoring": {"cancellation_thread_poll_interval_seconds": 300},
        }
    ) as instance:
        assert instance.cancellation_thread_poll_interval_seconds == 300

    with instance_for_test() as instance:
        assert instance.cancellation_thread_poll_interval_seconds == 10


def test_dagster_home_not_set():
    with environ({"DAGSTER_HOME": ""}):
        with pytest.raises(
            DagsterHomeNotSetError,
            match=r"The environment variable \$DAGSTER_HOME is not set\.",
        ):
            DagsterInstance.get()


def test_invalid_configurable_class():
    with pytest.raises(
        check.CheckError,
        match=re.escape(
            "Couldn't find class MadeUpRunLauncher in module when attempting to "
            "load the configurable class dagster.MadeUpRunLauncher"
        ),
    ):
        with instance_for_test(
            overrides={"run_launcher": {"module": "dagster", "class": "MadeUpRunLauncher"}}
        ) as instance:
            print(instance.run_launcher)  # noqa: T201


def test_invalid_configurable_module():
    with pytest.raises(
        check.CheckError,
        match=re.escape(
            (
                "Couldn't import module made_up_module when attempting to load "
                "the configurable class made_up_module.MadeUpRunLauncher"
            ),
        ),
    ):
        with instance_for_test(
            overrides={
                "run_launcher": {
                    "module": "made_up_module",
                    "class": "MadeUpRunLauncher",
                }
            }
        ) as instance:
            print(instance.run_launcher)  # noqa: T201


@pytest.mark.parametrize("dirname", (".", ".."))
def test_dagster_home_not_abspath(dirname):
    with environ({"DAGSTER_HOME": dirname}):
        with pytest.raises(
            DagsterInvariantViolationError,
            match=re.escape(f'$DAGSTER_HOME "{dirname}" must be an absolute path.'),
        ):
            DagsterInstance.get()


def test_dagster_home_not_dir():
    dirname = "/this/path/does/not/exist"

    with environ({"DAGSTER_HOME": dirname}):
        with pytest.raises(
            DagsterInvariantViolationError,
            match=re.escape(f'$DAGSTER_HOME "{dirname}" is not a directory or does not exist.'),
        ):
            DagsterInstance.get()


class TestInstanceSubclass(DagsterInstance):
    def __init__(self, *args, foo=None, baz=None, **kwargs):
        self._foo = foo
        self._baz = baz
        super().__init__(*args, **kwargs)

    def foo(self):
        return self._foo

    @property
    def baz(self):
        return self._baz

    @classmethod
    def config_schema(cls):
        return {
            "foo": Field(str, is_required=True),
            "baz": Field(str, is_required=False),
        }

    @staticmethod
    def config_defaults(base_dir):
        defaults = InstanceRef.config_defaults(base_dir)
        defaults["run_coordinator"] = ConfigurableClassData(
            "dagster._core.run_coordinator.queued_run_coordinator",
            "QueuedRunCoordinator",
            yaml.dump({}),
        )
        return defaults


def test_instance_subclass():
    with instance_for_test(
        overrides={
            "instance_class": {
                "module": "dagster_tests.core_tests.instance_tests.test_instance",
                "class": "TestInstanceSubclass",
            },
            "foo": "bar",
        }
    ) as subclass_instance:
        assert isinstance(subclass_instance, DagsterInstance)

        # isinstance(subclass_instance, TestInstanceSubclass) does not pass
        # Likely because the imported/dynamically loaded class is different from the local one

        assert subclass_instance.__class__.__name__ == "TestInstanceSubclass"
        assert subclass_instance.foo() == "bar"
        assert subclass_instance.baz is None

        assert isinstance(subclass_instance.run_coordinator, QueuedRunCoordinator)

    with instance_for_test(
        overrides={
            "instance_class": {
                "module": "dagster_tests.core_tests.instance_tests.test_instance",
                "class": "TestInstanceSubclass",
            },
            "foo": "bar",
            "baz": "quux",
        }
    ) as subclass_instance:
        assert isinstance(subclass_instance, DagsterInstance)

        assert subclass_instance.__class__.__name__ == "TestInstanceSubclass"
        assert subclass_instance.foo() == "bar"
        assert subclass_instance.baz == "quux"

    # omitting foo leads to a config schema validation error

    with pytest.raises(DagsterInvalidConfigError):
        with instance_for_test(
            overrides={
                "instance_class": {
                    "module": "dagster_tests.core_tests.instance_tests.test_instance",
                    "class": "TestInstanceSubclass",
                },
                "baz": "quux",
            }
        ) as subclass_instance:
            pass


# class that doesn't implement needed methods on ConfigurableClass
class InvalidRunLauncher(RunLauncher, ConfigurableClass):
    def launch_run(self, context: LaunchRunContext) -> None:
        pass

    def terminate(self, run_id):
        pass


def test_configurable_class_missing_methods():
    with pytest.raises(
        NotImplementedError,
        match="InvalidRunLauncher must implement the config_type classmethod",
    ):
        with instance_for_test(
            overrides={
                "run_launcher": {
                    "module": "dagster_tests.core_tests.instance_tests.test_instance",
                    "class": "InvalidRunLauncher",
                }
            }
        ) as instance:
            print(instance.run_launcher)  # noqa: T201
