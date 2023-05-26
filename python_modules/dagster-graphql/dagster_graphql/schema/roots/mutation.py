from typing import Optional, Sequence, Union

import dagster._check as check
import graphene
from dagster._core.definitions.events import AssetKey
from dagster._core.errors import DagsterInvariantViolationError
from dagster._core.nux import get_has_seen_nux, set_nux_seen
from dagster._core.workspace.permissions import Permissions
from dagster._daemon.asset_daemon import set_auto_materialize_paused

from dagster_graphql.implementation.execution.backfill import (
    cancel_partition_backfill,
    create_and_launch_partition_backfill,
    resume_partition_backfill,
)
from dagster_graphql.implementation.execution.dynamic_partitions import add_dynamic_partition
from dagster_graphql.implementation.execution.launch_execution import (
    launch_pipeline_execution,
    launch_pipeline_reexecution,
    launch_reexecution_from_parent_run,
)

from ...implementation.execution import (
    delete_pipeline_run,
    terminate_pipeline_execution,
    wipe_assets,
)
from ...implementation.external import fetch_workspace, get_full_external_job_or_raise
from ...implementation.telemetry import log_dagit_telemetry_event
from ...implementation.utils import (
    ExecutionMetadata,
    ExecutionParams,
    UserFacingGraphQLError,
    assert_permission_for_location,
    capture_error,
    check_permission,
    pipeline_selector_from_graphql,
    require_permission_check,
)
from ..asset_key import GrapheneAssetKey
from ..backfill import (
    GrapheneCancelBackfillResult,
    GrapheneLaunchBackfillResult,
    GrapheneResumeBackfillResult,
)
from ..errors import (
    GrapheneAssetNotFoundError,
    GrapheneConflictingExecutionParamsError,
    GrapheneError,
    GraphenePresetNotFoundError,
    GraphenePythonError,
    GrapheneReloadNotSupported,
    GrapheneRepositoryLocationNotFound,
    GrapheneRunNotFoundError,
    GrapheneUnauthorizedError,
)
from ..external import GrapheneWorkspace, GrapheneWorkspaceLocationEntry
from ..inputs import (
    GrapheneAssetKeyInput,
    GrapheneExecutionParams,
    GrapheneLaunchBackfillParams,
    GrapheneReexecutionParams,
    GrapheneRepositorySelector,
)
from ..partition_sets import GrapheneAddDynamicPartitionResult
from ..pipelines.pipeline import GrapheneRun
from ..runs import (
    GrapheneLaunchRunReexecutionResult,
    GrapheneLaunchRunResult,
    GrapheneLaunchRunSuccess,
    parse_run_config_input,
)
from ..schedule_dry_run import GrapheneScheduleDryRunMutation
from ..schedules import GrapheneStartScheduleMutation, GrapheneStopRunningScheduleMutation
from ..sensor_dry_run import GrapheneSensorDryRunMutation
from ..sensors import (
    GrapheneSetSensorCursorMutation,
    GrapheneStartSensorMutation,
    GrapheneStopSensorMutation,
)
from ..util import ResolveInfo, non_null_list


def create_execution_params(graphene_info, graphql_execution_params):
    preset_name = graphql_execution_params.get("preset")
    selector = pipeline_selector_from_graphql(graphql_execution_params["selector"])
    if preset_name:
        if graphql_execution_params.get("runConfigData"):
            raise UserFacingGraphQLError(
                GrapheneConflictingExecutionParamsError(conflicting_param="runConfigData")
            )

        if graphql_execution_params.get("mode"):
            raise UserFacingGraphQLError(
                GrapheneConflictingExecutionParamsError(conflicting_param="mode")
            )

        if selector.op_selection:
            raise UserFacingGraphQLError(
                GrapheneConflictingExecutionParamsError(
                    conflicting_param="selector.solid_selection"
                )
            )

        external_pipeline = get_full_external_job_or_raise(
            graphene_info,
            selector,
        )

        if not external_pipeline.has_preset(preset_name):
            raise UserFacingGraphQLError(
                GraphenePresetNotFoundError(preset=preset_name, selector=selector)
            )

        preset = external_pipeline.get_preset(preset_name)

        return ExecutionParams(
            selector=selector.with_op_selection(preset.op_selection),
            run_config=preset.run_config,
            mode=preset.mode,
            execution_metadata=create_execution_metadata(
                graphql_execution_params.get("executionMetadata")
            ),
            step_keys=graphql_execution_params.get("stepKeys"),
        )

    return execution_params_from_graphql(graphql_execution_params)


def execution_params_from_graphql(graphql_execution_params):
    return ExecutionParams(
        selector=pipeline_selector_from_graphql(graphql_execution_params.get("selector")),
        run_config=parse_run_config_input(
            graphql_execution_params.get("runConfigData") or {}, raise_on_error=True
        ),
        mode=graphql_execution_params.get("mode"),
        execution_metadata=create_execution_metadata(
            graphql_execution_params.get("executionMetadata")
        ),
        step_keys=graphql_execution_params.get("stepKeys"),
    )


def create_execution_metadata(graphql_execution_metadata):
    return (
        ExecutionMetadata(
            run_id=graphql_execution_metadata.get("runId"),
            tags={t["key"]: t["value"] for t in graphql_execution_metadata.get("tags", [])},
            root_run_id=graphql_execution_metadata.get("rootRunId"),
            parent_run_id=graphql_execution_metadata.get("parentRunId"),
        )
        if graphql_execution_metadata
        else ExecutionMetadata(run_id=None, tags={})
    )


class GrapheneDeletePipelineRunSuccess(graphene.ObjectType):
    """Output indicating that a run was deleted."""

    runId = graphene.NonNull(graphene.String)

    class Meta:
        name = "DeletePipelineRunSuccess"


class GrapheneDeletePipelineRunResult(graphene.Union):
    """The output from deleting a run."""

    class Meta:
        types = (
            GrapheneDeletePipelineRunSuccess,
            GrapheneUnauthorizedError,
            GraphenePythonError,
            GrapheneRunNotFoundError,
        )
        name = "DeletePipelineRunResult"


class GrapheneDeleteRunMutation(graphene.Mutation):
    """Deletes a run from storage."""

    Output = graphene.NonNull(GrapheneDeletePipelineRunResult)

    class Arguments:
        runId = graphene.NonNull(graphene.String)

    class Meta:
        name = "DeleteRunMutation"

    @capture_error
    @require_permission_check(Permissions.DELETE_PIPELINE_RUN)
    def mutate(
        self, graphene_info: ResolveInfo, runId: str
    ) -> Union[GrapheneRunNotFoundError, GrapheneDeletePipelineRunSuccess]:
        return delete_pipeline_run(graphene_info, runId)


class GrapheneTerminatePipelineExecutionSuccess(graphene.Interface):
    """Interface indicating that a run was terminated."""

    run = graphene.Field(graphene.NonNull(GrapheneRun))

    class Meta:
        name = "TerminatePipelineExecutionSuccess"


class GrapheneTerminateRunSuccess(graphene.ObjectType):
    """Output indicating that a run was terminated."""

    run = graphene.Field(graphene.NonNull(GrapheneRun))

    class Meta:
        interfaces = (GrapheneTerminatePipelineExecutionSuccess,)
        name = "TerminateRunSuccess"


class GrapheneTerminatePipelineExecutionFailure(graphene.Interface):
    """Interface indicating that a run failed to terminate."""

    run = graphene.NonNull(GrapheneRun)
    message = graphene.NonNull(graphene.String)

    class Meta:
        name = "TerminatePipelineExecutionFailure"


class GrapheneTerminateRunFailure(graphene.ObjectType):
    """Output indicating that a run failed to terminate."""

    run = graphene.NonNull(GrapheneRun)
    message = graphene.NonNull(graphene.String)

    class Meta:
        interfaces = (GrapheneTerminatePipelineExecutionFailure,)
        name = "TerminateRunFailure"


class GrapheneTerminateRunResult(graphene.Union):
    """The output from a run termination."""

    class Meta:
        types = (
            GrapheneTerminateRunSuccess,
            GrapheneTerminateRunFailure,
            GrapheneRunNotFoundError,
            GrapheneUnauthorizedError,
            GraphenePythonError,
        )
        name = "TerminateRunResult"


def create_execution_params_and_launch_pipeline_exec(graphene_info, execution_params_dict):
    execution_params = create_execution_params(graphene_info, execution_params_dict)
    assert_permission_for_location(
        graphene_info,
        Permissions.LAUNCH_PIPELINE_EXECUTION,
        execution_params.selector.location_name,
    )
    return launch_pipeline_execution(
        graphene_info,
        execution_params,
    )


class GrapheneLaunchRunMutation(graphene.Mutation):
    """Launches a job run."""

    Output = graphene.NonNull(GrapheneLaunchRunResult)

    class Arguments:
        executionParams = graphene.NonNull(GrapheneExecutionParams)

    class Meta:
        name = "LaunchRunMutation"

    @capture_error
    @require_permission_check(Permissions.LAUNCH_PIPELINE_EXECUTION)
    def mutate(
        self, graphene_info: ResolveInfo, executionParams: GrapheneExecutionParams
    ) -> Union[GrapheneLaunchRunSuccess, GrapheneError, GraphenePythonError]:
        return create_execution_params_and_launch_pipeline_exec(graphene_info, executionParams)


class GrapheneLaunchBackfillMutation(graphene.Mutation):
    """Launches a set of partition backfill runs."""

    Output = graphene.NonNull(GrapheneLaunchBackfillResult)

    class Arguments:
        backfillParams = graphene.NonNull(GrapheneLaunchBackfillParams)

    class Meta:
        name = "LaunchBackfillMutation"

    @capture_error
    @require_permission_check(Permissions.LAUNCH_PARTITION_BACKFILL)
    def mutate(self, graphene_info: ResolveInfo, backfillParams: GrapheneLaunchBackfillParams):
        return create_and_launch_partition_backfill(graphene_info, backfillParams)


class GrapheneCancelBackfillMutation(graphene.Mutation):
    """Cancels a set of partition backfill runs."""

    Output = graphene.NonNull(GrapheneCancelBackfillResult)

    class Arguments:
        backfillId = graphene.NonNull(graphene.String)

    class Meta:
        name = "CancelBackfillMutation"

    @capture_error
    @require_permission_check(Permissions.CANCEL_PARTITION_BACKFILL)
    def mutate(self, graphene_info: ResolveInfo, backfillId: str):
        return cancel_partition_backfill(graphene_info, backfillId)


class GrapheneResumeBackfillMutation(graphene.Mutation):
    """Retries a set of partition backfill runs."""

    Output = graphene.NonNull(GrapheneResumeBackfillResult)

    class Arguments:
        backfillId = graphene.NonNull(graphene.String)

    class Meta:
        name = "ResumeBackfillMutation"

    @capture_error
    @require_permission_check(Permissions.LAUNCH_PARTITION_BACKFILL)
    def mutate(self, graphene_info: ResolveInfo, backfillId: str):
        return resume_partition_backfill(graphene_info, backfillId)


class GrapheneAddDynamicPartitionMutation(graphene.Mutation):
    """Adds a partition to a dynamic partition set."""

    Output = graphene.NonNull(GrapheneAddDynamicPartitionResult)

    class Arguments:
        repositorySelector = graphene.NonNull(GrapheneRepositorySelector)
        partitionsDefName = graphene.NonNull(graphene.String)
        partitionKey = graphene.NonNull(graphene.String)

    class Meta:
        name = "AddDynamicPartitionMutation"

    @capture_error
    @require_permission_check(Permissions.EDIT_DYNAMIC_PARTITIONS)
    def mutate(
        self,
        graphene_info: ResolveInfo,
        repositorySelector: GrapheneRepositorySelector,
        partitionsDefName: str,
        partitionKey: str,
    ):
        return add_dynamic_partition(
            graphene_info, repositorySelector, partitionsDefName, partitionKey
        )


def create_execution_params_and_launch_pipeline_reexec(graphene_info, execution_params_dict):
    execution_params = create_execution_params(graphene_info, execution_params_dict)
    assert_permission_for_location(
        graphene_info,
        Permissions.LAUNCH_PIPELINE_REEXECUTION,
        execution_params.selector.location_name,
    )
    return launch_pipeline_reexecution(graphene_info, execution_params=execution_params)


class GrapheneLaunchRunReexecutionMutation(graphene.Mutation):
    """Re-executes a job run."""

    Output = graphene.NonNull(GrapheneLaunchRunReexecutionResult)

    class Arguments:
        executionParams = graphene.Argument(GrapheneExecutionParams)
        reexecutionParams = graphene.Argument(GrapheneReexecutionParams)

    class Meta:
        name = "LaunchRunReexecutionMutation"

    @capture_error
    @require_permission_check(Permissions.LAUNCH_PIPELINE_REEXECUTION)
    def mutate(
        self,
        graphene_info: ResolveInfo,
        executionParams: Optional[GrapheneExecutionParams] = None,
        reexecutionParams: Optional[GrapheneReexecutionParams] = None,
    ):
        if bool(executionParams) == bool(reexecutionParams):
            raise DagsterInvariantViolationError(
                "Must only provide one of either executionParams or reexecutionParams"
            )

        if executionParams:
            return create_execution_params_and_launch_pipeline_reexec(
                graphene_info,
                execution_params_dict=executionParams,
            )
        elif reexecutionParams:
            return launch_reexecution_from_parent_run(
                graphene_info,
                reexecutionParams["parentRunId"],
                reexecutionParams["strategy"],
            )
        else:
            check.failed("Unreachable")


class GrapheneTerminateRunPolicy(graphene.Enum):
    """The type of termination policy to use for a run."""

    # Default behavior: Only mark as canceled if the termination is successful, and after all
    # resources performing the execution have been shut down.
    SAFE_TERMINATE = "SAFE_TERMINATE"

    # Immediately mark the run as canceled, whether or not the termination was successful.
    # No guarantee that the execution has actually stopped.
    MARK_AS_CANCELED_IMMEDIATELY = "MARK_AS_CANCELED_IMMEDIATELY"

    class Meta:
        name = "TerminateRunPolicy"


class GrapheneTerminateRunMutation(graphene.Mutation):
    """Terminates a run."""

    Output = graphene.NonNull(GrapheneTerminateRunResult)

    class Arguments:
        runId = graphene.NonNull(graphene.String)
        terminatePolicy = graphene.Argument(GrapheneTerminateRunPolicy)

    class Meta:
        name = "TerminateRunMutation"

    @capture_error
    @require_permission_check(Permissions.TERMINATE_PIPELINE_EXECUTION)
    def mutate(
        self,
        graphene_info: ResolveInfo,
        runId: str,
        terminatePolicy: Optional[GrapheneTerminateRunPolicy] = None,
    ):
        return terminate_pipeline_execution(
            graphene_info,
            runId,
            terminatePolicy or GrapheneTerminateRunPolicy.SAFE_TERMINATE,
        )


class GrapheneReloadRepositoryLocationMutationResult(graphene.Union):
    """The output from reloading a code location server."""

    class Meta:
        types = (
            GrapheneWorkspaceLocationEntry,
            GrapheneReloadNotSupported,
            GrapheneRepositoryLocationNotFound,
            GrapheneUnauthorizedError,
            GraphenePythonError,
        )
        name = "ReloadRepositoryLocationMutationResult"


class GrapheneShutdownRepositoryLocationSuccess(graphene.ObjectType):
    """Output indicating that a code location server was shut down."""

    repositoryLocationName = graphene.NonNull(graphene.String)

    class Meta:
        name = "ShutdownRepositoryLocationSuccess"


class GrapheneShutdownRepositoryLocationMutationResult(graphene.Union):
    """The output from shutting down a code location server."""

    class Meta:
        types = (
            GrapheneShutdownRepositoryLocationSuccess,
            GrapheneRepositoryLocationNotFound,
            GrapheneUnauthorizedError,
            GraphenePythonError,
        )
        name = "ShutdownRepositoryLocationMutationResult"


class GrapheneReloadRepositoryLocationMutation(graphene.Mutation):
    """Reloads a code location server."""

    Output = graphene.NonNull(GrapheneReloadRepositoryLocationMutationResult)

    class Arguments:
        repositoryLocationName = graphene.NonNull(graphene.String)

    class Meta:
        name = "ReloadRepositoryLocationMutation"

    @capture_error
    @require_permission_check(Permissions.RELOAD_REPOSITORY_LOCATION)
    def mutate(
        self, graphene_info: ResolveInfo, repositoryLocationName: str
    ) -> Union[
        GrapheneWorkspaceLocationEntry,
        GrapheneReloadNotSupported,
        GrapheneRepositoryLocationNotFound,
    ]:
        assert_permission_for_location(
            graphene_info, Permissions.RELOAD_REPOSITORY_LOCATION, repositoryLocationName
        )

        if not graphene_info.context.has_code_location_name(repositoryLocationName):
            return GrapheneRepositoryLocationNotFound(repositoryLocationName)

        if not graphene_info.context.is_reload_supported(repositoryLocationName):
            return GrapheneReloadNotSupported(repositoryLocationName)

        # The current workspace context is a WorkspaceRequestContext, which contains a reference to the
        # repository locations that were present in the root IWorkspaceProcessContext the start of the
        # request. Reloading a repository location modifies the IWorkspaceProcessContext, rendeirng
        # our current WorkspaceRequestContext outdated. Therefore, `reload_repository_location` returns
        # an updated WorkspaceRequestContext for us to use.
        new_context = graphene_info.context.reload_code_location(repositoryLocationName)
        return GrapheneWorkspaceLocationEntry(
            check.not_none(new_context.get_location_entry(repositoryLocationName))
        )


class GrapheneShutdownRepositoryLocationMutation(graphene.Mutation):
    """Shuts down a code location server."""

    Output = graphene.NonNull(GrapheneShutdownRepositoryLocationMutationResult)

    class Arguments:
        repositoryLocationName = graphene.NonNull(graphene.String)

    class Meta:
        name = "ShutdownRepositoryLocationMutation"

    @capture_error
    @require_permission_check(Permissions.RELOAD_REPOSITORY_LOCATION)
    def mutate(
        self, graphene_info: ResolveInfo, repositoryLocationName: str
    ) -> Union[GrapheneRepositoryLocationNotFound, GrapheneShutdownRepositoryLocationSuccess]:
        assert_permission_for_location(
            graphene_info, Permissions.RELOAD_REPOSITORY_LOCATION, repositoryLocationName
        )
        if not graphene_info.context.has_code_location_name(repositoryLocationName):
            return GrapheneRepositoryLocationNotFound(repositoryLocationName)

        if not graphene_info.context.is_shutdown_supported(repositoryLocationName):
            raise Exception(
                f"Location {repositoryLocationName} does not support shutting down via GraphQL"
            )

        graphene_info.context.shutdown_code_location(repositoryLocationName)
        return GrapheneShutdownRepositoryLocationSuccess(
            repositoryLocationName=repositoryLocationName
        )


class GrapheneReloadWorkspaceMutationResult(graphene.Union):
    """The output from reloading the workspace."""

    class Meta:
        types = (
            GrapheneWorkspace,
            GrapheneUnauthorizedError,
            GraphenePythonError,
        )
        name = "ReloadWorkspaceMutationResult"


class GrapheneReloadWorkspaceMutation(graphene.Mutation):
    """Reloads the workspace and its code location servers."""

    Output = graphene.NonNull(GrapheneReloadWorkspaceMutationResult)

    class Meta:
        name = "ReloadWorkspaceMutation"

    @capture_error
    @check_permission(Permissions.RELOAD_WORKSPACE)
    def mutate(self, graphene_info: ResolveInfo):
        new_context = graphene_info.context.reload_workspace()
        return fetch_workspace(new_context)


class GrapheneAssetWipeSuccess(graphene.ObjectType):
    """Output indicating that asset history was deleted."""

    assetKeys = non_null_list(GrapheneAssetKey)

    class Meta:
        name = "AssetWipeSuccess"


class GrapheneAssetWipeMutationResult(graphene.Union):
    """The output from deleting asset history."""

    class Meta:
        types = (
            GrapheneAssetNotFoundError,
            GrapheneUnauthorizedError,
            GraphenePythonError,
            GrapheneAssetWipeSuccess,
        )
        name = "AssetWipeMutationResult"


class GrapheneAssetWipeMutation(graphene.Mutation):
    """Deletes asset history from storage."""

    Output = graphene.NonNull(GrapheneAssetWipeMutationResult)

    class Arguments:
        assetKeys = graphene.Argument(non_null_list(GrapheneAssetKeyInput))

    class Meta:
        name = "AssetWipeMutation"

    @capture_error
    @check_permission(Permissions.WIPE_ASSETS)
    def mutate(self, graphene_info: ResolveInfo, assetKeys: Sequence[GrapheneAssetKeyInput]):
        return wipe_assets(
            graphene_info, [AssetKey.from_graphql_input(asset_key) for asset_key in assetKeys]
        )


class GrapheneLogTelemetrySuccess(graphene.ObjectType):
    """Output indicating that telemetry was logged."""

    action = graphene.NonNull(graphene.String)

    class Meta:
        name = "LogTelemetrySuccess"


class GrapheneLogTelemetryMutationResult(graphene.Union):
    """The output from logging telemetry."""

    class Meta:
        types = (
            GrapheneLogTelemetrySuccess,
            GraphenePythonError,
        )
        name = "LogTelemetryMutationResult"


class GrapheneLogTelemetryMutation(graphene.Mutation):
    """Log telemetry about the Dagster instance."""

    Output = graphene.NonNull(GrapheneLogTelemetryMutationResult)

    class Arguments:
        action = graphene.Argument(graphene.NonNull(graphene.String))
        clientTime = graphene.Argument(graphene.NonNull(graphene.String))
        clientId = graphene.Argument(graphene.NonNull(graphene.String))
        metadata = graphene.Argument(graphene.NonNull(graphene.String))

    class Meta:
        name = "LogTelemetryMutation"

    @capture_error
    def mutate(
        self, graphene_info: ResolveInfo, action: str, clientTime: str, clientId: str, metadata: str
    ):
        action = log_dagit_telemetry_event(
            graphene_info,
            action=action,
            client_time=clientTime,
            client_id=clientId,
            metadata=metadata,
        )
        return action


class GrapheneSetNuxSeenMutation(graphene.Mutation):
    """Store whether we've shown the nux to any user and they've dismissed or submitted it."""

    Output = graphene.NonNull(graphene.Boolean)

    class Meta:
        name = "SetNuxSeenMutation"

    @capture_error
    def mutate(self, _graphene_info):
        set_nux_seen()
        return get_has_seen_nux()


class GrapheneSetAutoMaterializePausedMutation(graphene.Mutation):
    """Toggle asset auto materializing on or off."""

    Output = graphene.NonNull(graphene.Boolean)

    class Meta:
        name = "SetAutoMaterializedPausedMutation"

    class Arguments:
        paused = graphene.Argument(graphene.NonNull(graphene.Boolean))

    @capture_error
    @check_permission(Permissions.TOGGLE_AUTO_MATERIALIZE)
    def mutate(self, graphene_info, paused: bool):
        set_auto_materialize_paused(graphene_info.context.instance, paused)
        return paused


class GrapheneDagitMutation(graphene.ObjectType):
    """The root for all mutations to modify data in your Dagster instance."""

    class Meta:
        name = "DagitMutation"

    launch_pipeline_execution = GrapheneLaunchRunMutation.Field()
    launch_run = GrapheneLaunchRunMutation.Field()
    launch_pipeline_reexecution = GrapheneLaunchRunReexecutionMutation.Field()
    launch_run_reexecution = GrapheneLaunchRunReexecutionMutation.Field()
    start_schedule = GrapheneStartScheduleMutation.Field()
    stop_running_schedule = GrapheneStopRunningScheduleMutation.Field()
    start_sensor = GrapheneStartSensorMutation.Field()
    set_sensor_cursor = GrapheneSetSensorCursorMutation.Field()
    stop_sensor = GrapheneStopSensorMutation.Field()
    sensor_dry_run = GrapheneSensorDryRunMutation.Field()
    schedule_dry_run = GrapheneScheduleDryRunMutation.Field()
    terminate_pipeline_execution = GrapheneTerminateRunMutation.Field()
    terminate_run = GrapheneTerminateRunMutation.Field()
    delete_pipeline_run = GrapheneDeleteRunMutation.Field()
    delete_run = GrapheneDeleteRunMutation.Field()
    reload_repository_location = GrapheneReloadRepositoryLocationMutation.Field()
    reload_workspace = GrapheneReloadWorkspaceMutation.Field()
    shutdown_repository_location = GrapheneShutdownRepositoryLocationMutation.Field()
    wipe_assets = GrapheneAssetWipeMutation.Field()
    launch_partition_backfill = GrapheneLaunchBackfillMutation.Field()
    resume_partition_backfill = GrapheneResumeBackfillMutation.Field()
    cancel_partition_backfill = GrapheneCancelBackfillMutation.Field()
    log_telemetry = GrapheneLogTelemetryMutation.Field()
    set_nux_seen = GrapheneSetNuxSeenMutation.Field()
    add_dynamic_partition = GrapheneAddDynamicPartitionMutation.Field()
    setAutoMaterializePaused = GrapheneSetAutoMaterializePausedMutation.Field()
