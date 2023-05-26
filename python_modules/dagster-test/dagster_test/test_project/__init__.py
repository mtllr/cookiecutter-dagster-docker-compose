import base64
import os
import subprocess
import sys
from contextlib import contextmanager
from typing import Any, Mapping, Optional

import dagster._check as check
from dagster._core.code_pointer import FileCodePointer
from dagster._core.definitions.job_definition import JobDefinition
from dagster._core.definitions.reconstruct import ReconstructableJob, ReconstructableRepository
from dagster._core.definitions.selector import InstigatorSelector
from dagster._core.execution.api import create_execution_plan
from dagster._core.execution.build_resources import build_resources
from dagster._core.execution.context.output import build_output_context
from dagster._core.host_representation import (
    ExternalJob,
    ExternalSchedule,
    GrpcServerCodeLocationOrigin,
    InProcessCodeLocationOrigin,
)
from dagster._core.host_representation.origin import (
    ExternalInstigatorOrigin,
    ExternalJobOrigin,
    ExternalRepositoryOrigin,
)
from dagster._core.instance import DagsterInstance
from dagster._core.origin import (
    DEFAULT_DAGSTER_ENTRY_POINT,
    JobPythonOrigin,
    RepositoryPythonOrigin,
)
from dagster._core.test_utils import in_process_test_workspace
from dagster._core.types.loadable_target_origin import LoadableTargetOrigin
from dagster._serdes import create_snapshot_id
from dagster._utils import file_relative_path, git_repository_root

IS_BUILDKITE = os.getenv("BUILDKITE") is not None


def cleanup_memoized_results(
    job_def: JobDefinition, instance: DagsterInstance, run_config: Mapping[str, Any]
) -> None:
    # Clean up any memoized outputs from the s3 bucket
    from dagster_aws.s3 import s3_pickle_io_manager, s3_resource

    execution_plan = create_execution_plan(
        job_def,
        run_config=run_config,
        instance_ref=instance.get_ref(),
    )

    with build_resources(
        {"s3": s3_resource, "io_manager": s3_pickle_io_manager},
        resource_config=run_config["resources"],
    ) as resources:
        io_manager = resources.io_manager
        for step_output_handle, version in execution_plan.step_output_versions.items():
            output_context = build_output_context(
                step_key=step_output_handle.step_key,
                name=step_output_handle.output_name,
                version=version,
            )

            key = io_manager._get_path(output_context)  # noqa: SLF001
            io_manager.unlink(key)


def get_test_repo_path():
    return os.path.join(
        git_repository_root(), "python_modules", "dagster-test", "dagster_test", "test_project"
    )


def get_test_project_environments_path():
    return os.path.join(get_test_repo_path(), "environments")


def get_buildkite_registry_config():
    import boto3

    ecr_client = boto3.client("ecr", region_name="us-west-2")
    token = ecr_client.get_authorization_token()
    username, password = (
        base64.b64decode(token["authorizationData"][0]["authorizationToken"])
        .decode("utf-8")
        .split(":")
    )
    registry = token["authorizationData"][0]["proxyEndpoint"]

    return {
        "url": registry,
        "username": username,
        "password": password,
    }


def find_local_test_image(docker_image):
    import docker

    try:
        client = docker.from_env()
        client.images.get(docker_image)
        print(  # noqa: T201
            "Found existing image tagged {image}, skipping image build. To rebuild, first run: "
            "docker rmi {image}".format(image=docker_image)
        )
    except docker.errors.ImageNotFound:
        build_and_tag_test_image(docker_image)


def build_and_tag_test_image(tag):
    check.str_param(tag, "tag")

    base_python = "3.8.8"

    # Build and tag local dagster test image
    return subprocess.check_output(["./build.sh", base_python, tag], cwd=get_test_repo_path())


def get_test_project_recon_job(
    job_name: str,
    container_image: Optional[str] = None,
    container_context: Optional[Mapping[str, object]] = None,
    filename: Optional[str] = None,
) -> "ReOriginatedReconstructableJobForTest":
    filename = filename or "repo.py"
    return ReOriginatedReconstructableJobForTest(
        ReconstructableRepository.for_file(
            file_relative_path(__file__, f"test_jobs/{filename}"),
            "define_demo_execution_repo",
            container_image=container_image,
            container_context=container_context,
        ).get_reconstructable_job(job_name)
    )


class ReOriginatedReconstructableJobForTest(ReconstructableJob):
    def __new__(
        cls,
        reconstructable_job: ReconstructableJob,
    ):
        return super(ReOriginatedReconstructableJobForTest, cls).__new__(
            cls,
            reconstructable_job.repository,
            reconstructable_job.job_name,
            reconstructable_job.op_selection,
        )

    def get_python_origin(self):
        """Hack! Inject origin that the docker-celery images will use. The BK image uses a different
        directory structure (/workdir/python_modules/dagster-test/dagster_test/test_project) than
        the test that creates the ReconstructableJob. As a result the normal origin won't
        work, we need to inject this one.
        """
        return JobPythonOrigin(
            self.job_name,
            RepositoryPythonOrigin(
                executable_path="python",
                code_pointer=FileCodePointer(
                    "/dagster_test/test_project/test_jobs/repo.py",
                    "define_demo_execution_repo",
                ),
                container_image=self.repository.container_image,
                entry_point=DEFAULT_DAGSTER_ENTRY_POINT,
                container_context=self.repository.container_context,
            ),
        )


class ReOriginatedExternalJobForTest(ExternalJob):
    def __init__(
        self, external_job: ExternalJob, container_image=None, container_context=None, filename=None
    ):
        self._container_image = container_image
        self._container_context = container_context
        self._filename = filename or "repo.py"
        super(ReOriginatedExternalJobForTest, self).__init__(
            external_job.external_job_data,
            external_job.repository_handle,
        )

    def get_python_origin(self):
        """Hack! Inject origin that the k8s images will use. The BK image uses a different directory
        structure (/workdir/python_modules/dagster-test/dagster_test/test_project) than the images
        inside the kind cluster (/dagster_test/test_project). As a result the normal origin won't
        work, we need to inject this one.
        """
        return JobPythonOrigin(
            self._job_index.name,
            RepositoryPythonOrigin(
                executable_path="python",
                code_pointer=FileCodePointer(
                    f"/dagster_test/test_project/test_jobs/{self._filename}",
                    "define_demo_execution_repo",
                ),
                container_image=self._container_image,
                entry_point=DEFAULT_DAGSTER_ENTRY_POINT,
                container_context=self._container_context,
            ),
        )

    def get_external_origin(self) -> ExternalJobOrigin:
        """Hack! Inject origin that the k8s images will use. The BK image uses a different directory
        structure (/workdir/python_modules/dagster-test/dagster_test/test_project) than the images
        inside the kind cluster (/dagster_test/test_project). As a result the normal origin won't
        work, we need to inject this one.
        """
        return ExternalJobOrigin(
            external_repository_origin=ExternalRepositoryOrigin(
                code_location_origin=InProcessCodeLocationOrigin(
                    loadable_target_origin=LoadableTargetOrigin(
                        executable_path="python",
                        python_file=f"/dagster_test/test_project/test_jobs/{self._filename}",
                        attribute="define_demo_execution_repo",
                    ),
                    container_image=self._container_image,
                    entry_point=DEFAULT_DAGSTER_ENTRY_POINT,
                ),
                repository_name="demo_execution_repo",
            ),
            job_name=self._job_index.name,
        )


class ReOriginatedExternalScheduleForTest(ExternalSchedule):
    def __init__(
        self,
        external_schedule: ExternalSchedule,
        container_image=None,
    ):
        self._container_image = container_image
        super(ReOriginatedExternalScheduleForTest, self).__init__(
            external_schedule._external_schedule_data,  # noqa: SLF001
            external_schedule.handle.repository_handle,
        )

    def get_external_origin(self):
        """Hack! Inject origin that the k8s images will use. The k8s helm chart workspace uses a
        gRPC server repo location origin. As a result the normal origin won't work, we need to
        inject this one.
        """
        return ExternalInstigatorOrigin(
            external_repository_origin=ExternalRepositoryOrigin(
                code_location_origin=GrpcServerCodeLocationOrigin(
                    host="user-code-deployment-1",
                    port=3030,
                    location_name="user-code-deployment-1",
                ),
                repository_name="demo_execution_repo",
            ),
            instigator_name=self.name,
        )

    @property
    def selector_id(self):
        """Hack! Inject a selector that matches the one that the k8s helm chart will use."""
        return create_snapshot_id(
            InstigatorSelector(
                "user-code-deployment-1",
                "demo_execution_repo",
                self.name,
            )
        )


@contextmanager
def get_test_project_workspace(instance, container_image=None, filename=None):
    filename = filename or "repo.py"
    with in_process_test_workspace(
        instance,
        loadable_target_origin=LoadableTargetOrigin(
            executable_path=sys.executable,
            python_file=file_relative_path(__file__, f"test_jobs/{filename}"),
            attribute="define_demo_execution_repo",
        ),
        container_image=container_image,
    ) as workspace:
        yield workspace


@contextmanager
def get_test_project_external_job_hierarchy(
    instance, job_name, container_image=None, filename=None
):
    with get_test_project_workspace(instance, container_image, filename) as workspace:
        location = workspace.get_code_location(workspace.code_location_names[0])
        repo = location.get_repository("demo_execution_repo")
        job = repo.get_full_external_job(job_name)
        yield workspace, location, repo, job


@contextmanager
def get_test_project_external_repo(instance, container_image=None, filename=None):
    with get_test_project_workspace(instance, container_image, filename) as workspace:
        location = workspace.get_code_location(workspace.code_location_names[0])
        yield location, location.get_repository("demo_execution_repo")


@contextmanager
def get_test_project_workspace_and_external_job(
    instance, job_name, container_image=None, filename=None
):
    with get_test_project_external_job_hierarchy(instance, job_name, container_image, filename) as (
        workspace,
        _location,
        _repo,
        job,
    ):
        yield workspace, job


@contextmanager
def get_test_project_external_schedule(
    instance, schedule_name, container_image=None, filename=None
):
    with get_test_project_external_repo(
        instance, container_image=container_image, filename=filename
    ) as (_, repo):
        yield repo.get_external_schedule(schedule_name)


def get_test_project_docker_image():
    docker_repository = os.getenv("DAGSTER_DOCKER_REPOSITORY")
    image_name = os.getenv("DAGSTER_DOCKER_IMAGE", "test-project")
    docker_image_tag = os.getenv("DAGSTER_DOCKER_IMAGE_TAG")

    if IS_BUILDKITE:
        assert docker_image_tag is not None, (
            "This test requires the environment variable DAGSTER_DOCKER_IMAGE_TAG to be set "
            "to proceed"
        )
        assert docker_repository is not None, (
            "This test requires the environment variable DAGSTER_DOCKER_REPOSITORY to be set "
            "to proceed"
        )

    # This needs to be a domain name to avoid the k8s machinery automatically prefixing it with
    # `docker.io/` and attempting to pull images from Docker Hub
    if not docker_repository:
        docker_repository = "dagster.io.priv"

    if not docker_image_tag:
        # Detect the python version we're running on
        majmin = str(sys.version_info.major) + str(sys.version_info.minor)

        docker_image_tag = "py{majmin}-{image_version}".format(
            majmin=majmin, image_version="latest"
        )

    final_docker_image = "{repository}/{image_name}:{tag}".format(
        repository=docker_repository, image_name=image_name, tag=docker_image_tag
    )
    print("Using Docker image: %s" % final_docker_image)  # noqa: T201
    return final_docker_image
