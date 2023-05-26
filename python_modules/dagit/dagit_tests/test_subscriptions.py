import gc
import sys
from contextlib import contextmanager
from unittest import mock

import objgraph
import pytest
from dagit.graphql import GraphQLWS
from dagit.webserver import DagitWebserver
from dagster import job, op
from dagster._core.test_utils import environ, instance_for_test
from dagster._core.workspace.context import WorkspaceProcessContext
from dagster._core.workspace.load_target import WorkspaceFileTarget
from dagster._utils import file_relative_path
from starlette.testclient import TestClient

EVENT_LOG_SUBSCRIPTION = """
    subscription PipelineRunLogsSubscription($runId: ID!) {
        pipelineRunLogs(runId: $runId) {
            __typename
        }
    }
"""

COMPUTE_LOG_SUBSCRIPTION = """
    subscription ComputeLogsSubscription(
        $runId: ID!
        $stepKey: String!
        $ioType: ComputeIOType!
    ) {
        computeLogs(runId: $runId, stepKey: $stepKey, ioType: $ioType) {
            __typename
        }
    }
"""


@contextmanager
def create_asgi_client(instance):
    yaml_paths = [file_relative_path(__file__, "./workspace.yaml")]

    with WorkspaceProcessContext(
        instance=instance,
        workspace_load_target=WorkspaceFileTarget(paths=yaml_paths),
        version="",
        read_only=True,
    ) as process_context:
        yield TestClient(DagitWebserver(process_context).create_asgi_app())


def send_subscription_message(ws, op, payload=None):
    ws.send_json({"id": 1, "type": op, "payload": payload or {}})


def start_subscription(ws, query, variables=None):
    start_payload = {
        "query": query,
        "variables": variables or {},
    }

    send_subscription_message(ws, GraphQLWS.CONNECTION_INIT)
    ws.receive_json()
    send_subscription_message(ws, GraphQLWS.START, start_payload)
    rx = ws.receive_json()
    assert rx["type"] != GraphQLWS.ERROR, rx
    return rx


def end_subscription(ws):
    send_subscription_message(ws, GraphQLWS.STOP)
    send_subscription_message(ws, GraphQLWS.CONNECTION_TERMINATE)
    ws.close()


@op
def example_op():
    return 1


@job
def example_job():
    example_op()


def test_event_log_subscription():
    with instance_for_test() as instance:
        run = example_job.execute_in_process(instance=instance)
        assert run.success
        assert run.run_id

        with create_asgi_client(instance) as client:
            with client.websocket_connect("/graphql", GraphQLWS.PROTOCOL) as ws:
                start_subscription(ws, EVENT_LOG_SUBSCRIPTION, {"runId": run.run_id})
                gc.collect()
                assert len(objgraph.by_type("async_generator")) == 1
                end_subscription(ws)

            gc.collect()
            assert len(objgraph.by_type("async_generator")) == 0


@pytest.mark.skipif(
    sys.version_info < (3, 8),
    reason="Inconsistent GC on the async_generator in 3.7",
)
def test_event_log_subscription_chunked():
    with instance_for_test() as instance, environ({"DAGIT_EVENT_LOAD_CHUNK_SIZE": "2"}):
        run = example_job.execute_in_process(instance=instance)
        assert run.success
        assert run.run_id

        with create_asgi_client(instance) as client:
            with client.websocket_connect("/graphql", GraphQLWS.PROTOCOL) as ws:
                start_subscription(ws, EVENT_LOG_SUBSCRIPTION, {"runId": run.run_id})
                gc.collect()
                assert len(objgraph.by_type("async_generator")) == 1

                end_subscription(ws)

        gc.collect()
        assert len(objgraph.by_type("async_generator")) == 0


@mock.patch(
    "dagster._core.storage.local_compute_log_manager.LocalComputeLogManager.is_watch_completed"
)
def test_compute_log_subscription(mock_watch_completed):
    mock_watch_completed.return_value = False

    with instance_for_test() as instance:
        run = example_job.execute_in_process(instance=instance)
        assert run.success
        assert run.run_id

        with create_asgi_client(instance) as client:
            with client.websocket_connect("/graphql", GraphQLWS.PROTOCOL) as ws:
                start_subscription(
                    ws,
                    COMPUTE_LOG_SUBSCRIPTION,
                    {
                        "runId": run.run_id,
                        "stepKey": "example_op",
                        "ioType": "STDERR",
                    },
                )
                gc.collect()
                assert len(objgraph.by_type("ComputeLogSubscription")) == 1
                end_subscription(ws)

            gc.collect()
            assert len(objgraph.by_type("ComputeLogSubscription")) == 0
