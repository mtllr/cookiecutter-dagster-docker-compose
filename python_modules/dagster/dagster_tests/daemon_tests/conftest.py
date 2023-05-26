import os
import sys
from typing import Iterator, Optional, cast

import pytest
from dagster import DagsterInstance
from dagster._core.host_representation import (
    CodeLocation,
    ExternalRepository,
    InProcessCodeLocationOrigin,
)
from dagster._core.test_utils import (
    InProcessTestWorkspaceLoadTarget,
    create_test_daemon_workspace_context,
    instance_for_test,
)
from dagster._core.types.loadable_target_origin import LoadableTargetOrigin
from dagster._core.workspace.context import WorkspaceProcessContext


@pytest.fixture(name="instance_module_scoped", scope="module")
def instance_module_scoped_fixture() -> Iterator[DagsterInstance]:
    with instance_for_test(
        overrides={
            "run_launcher": {
                "module": "dagster._core.launcher.sync_in_memory_run_launcher",
                "class": "SyncInMemoryRunLauncher",
            }
        }
    ) as instance:
        yield instance


@pytest.fixture(name="instance", scope="function")
def instance_fixture(instance_module_scoped) -> Iterator[DagsterInstance]:
    instance_module_scoped.wipe()
    instance_module_scoped.wipe_all_schedules()
    yield instance_module_scoped


def workspace_load_target(attribute=None):
    return InProcessTestWorkspaceLoadTarget(
        InProcessCodeLocationOrigin(
            loadable_target_origin=loadable_target_origin(attribute=attribute),
            location_name="test_location",
        )
    )


@pytest.fixture(name="workspace_context", scope="module")
def workspace_fixture(instance_module_scoped) -> Iterator[WorkspaceProcessContext]:
    with create_test_daemon_workspace_context(
        workspace_load_target=workspace_load_target(), instance=instance_module_scoped
    ) as workspace_context:
        yield workspace_context


@pytest.fixture(name="external_repo", scope="module")
def external_repo_fixture(
    workspace_context: WorkspaceProcessContext,
) -> Iterator[ExternalRepository]:
    yield cast(
        CodeLocation,
        next(
            iter(workspace_context.create_request_context().get_workspace_snapshot().values())
        ).code_location,
    ).get_repository("the_repo")


def loadable_target_origin(attribute: Optional[str] = None) -> LoadableTargetOrigin:
    return LoadableTargetOrigin(
        executable_path=sys.executable,
        module_name="dagster_tests.daemon_tests.test_backfill",
        working_directory=os.getcwd(),
        attribute=attribute,
    )
