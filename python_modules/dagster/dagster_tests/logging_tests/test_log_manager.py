import logging
import sys
import textwrap

import pytest
from dagster import DagsterEvent
from dagster._core.definitions.dependency import NodeHandle
from dagster._core.errors import DagsterUserCodeExecutionError, user_code_error_boundary
from dagster._core.execution.plan.objects import ErrorSource, StepFailureData
from dagster._core.execution.plan.outputs import StepOutputData, StepOutputHandle
from dagster._core.log_manager import (
    DagsterLoggingMetadata,
    DagsterLogHandler,
    DagsterLogManager,
    DagsterMessageProps,
    construct_log_string,
)
from dagster._utils.error import serializable_error_info_from_exc_info


def test_metadata_event_tags():
    logging_metadata = DagsterLoggingMetadata(
        run_id="f79a8a93-27f1-41b5-b465-b35d0809b26d",
        job_name="my_job",
        job_tags={"foo": "bar"},
    )

    all_tags = logging_metadata.all_tags()
    event_tags = logging_metadata.event_tags()

    assert all_tags["job_name"] == "my_job"
    assert all_tags["job_tags"] == "{'foo': 'bar'}"

    assert event_tags["job_name"] == "my_job"
    assert "job_tags" not in event_tags


def test_construct_log_string_for_event():
    step_output_event = DagsterEvent(
        event_type_value="STEP_OUTPUT",
        job_name="my_job",
        step_key="op2",
        node_handle=NodeHandle("op2", None),
        step_kind_value="COMPUTE",
        logging_tags={},
        event_specific_data=StepOutputData(step_output_handle=StepOutputHandle("op2", "result")),
        message='Yielded output "result" of type "Any" for step "op2". (Type check passed).',
        pid=54348,
    )

    logging_metadata = DagsterLoggingMetadata(
        run_id="f79a8a93-27f1-41b5-b465-b35d0809b26d", job_name="my_job"
    )

    dagster_message_props = DagsterMessageProps(
        orig_message=step_output_event.message,
        dagster_event=step_output_event,
    )

    assert (
        construct_log_string(logging_metadata=logging_metadata, message_props=dagster_message_props)
        == "my_job - f79a8a93-27f1-41b5-b465-b35d0809b26d - 54348 - STEP_OUTPUT - Yielded"
        ' output "result" of type "Any" for step "op2". (Type check passed).'
    )


def test_construct_log_string_for_log():
    logging_metadata = DagsterLoggingMetadata(
        run_id="f79a8a93-27f1-41b5-b465-b35d0809b26d", job_name="my_job"
    )
    dagster_message_props = DagsterMessageProps(orig_message="hear my tale")
    assert (
        construct_log_string(logging_metadata, dagster_message_props)
        == "my_job - f79a8a93-27f1-41b5-b465-b35d0809b26d - hear my tale"
    )


def make_log_string(error, error_source=None):
    step_failure_event = DagsterEvent(
        event_type_value="STEP_FAILURE",
        job_name="my_job",
        step_key="op2",
        node_handle=NodeHandle("op2", None),
        step_kind_value="COMPUTE",
        logging_tags={},
        event_specific_data=StepFailureData(
            error=error, user_failure_data=None, error_source=error_source
        ),
        message='Execution of step "op2" failed.',
        pid=54348,
    )

    logging_metadata = DagsterLoggingMetadata(
        run_id="f79a8a93-27f1-41b5-b465-b35d0809b26d", job_name="my_job"
    )
    dagster_message_props = DagsterMessageProps(
        orig_message=step_failure_event.message,
        dagster_event=step_failure_event,
    )
    return construct_log_string(logging_metadata, dagster_message_props)


def test_construct_log_string_with_error():
    error = None
    try:
        raise ValueError("some error")
    except ValueError:
        error = serializable_error_info_from_exc_info(sys.exc_info())

    log_string = make_log_string(error)
    expected_start = textwrap.dedent(
        """
        my_job - f79a8a93-27f1-41b5-b465-b35d0809b26d - 54348 - STEP_FAILURE - Execution of step "op2" failed.

        ValueError: some error

        Stack Trace:
          File "
        """
    ).strip()
    assert log_string.startswith(expected_start)


def test_construct_log_string_with_user_code_error():
    error = None
    try:
        with user_code_error_boundary(
            DagsterUserCodeExecutionError, lambda: "Error occurred while eating a banana"
        ):
            raise ValueError("some error")
    except DagsterUserCodeExecutionError:
        error = serializable_error_info_from_exc_info(sys.exc_info())

    log_string = make_log_string(error, error_source=ErrorSource.USER_CODE_ERROR)
    expected_start = textwrap.dedent(
        """
        my_job - f79a8a93-27f1-41b5-b465-b35d0809b26d - 54348 - STEP_FAILURE - Execution of step "op2" failed.

        dagster._core.errors.DagsterUserCodeExecutionError: Error occurred while eating a banana:

        ValueError: some error

        Stack Trace:
          File "
        """
    ).strip()

    assert log_string.startswith(expected_start)


def test_construct_log_string_with_error_raise_from():
    error = None
    try:
        try:
            try:
                raise ValueError("inner error")
            except ValueError:
                raise ValueError("middle error")
        except ValueError as e:
            raise ValueError("outer error") from e
    except ValueError:
        error = serializable_error_info_from_exc_info(sys.exc_info())

    log_string = make_log_string(error)
    expected_start = textwrap.dedent(
        """
        my_job - f79a8a93-27f1-41b5-b465-b35d0809b26d - 54348 - STEP_FAILURE - Execution of step "op2" failed.

        ValueError: outer error

        Stack Trace:
          File "
        """
    ).strip()

    assert log_string.startswith(expected_start)

    expected_cause_substr = textwrap.dedent(
        """
        The above exception was caused by the following exception:
        ValueError: middle error

        Stack Trace:
          File "
        """
    ).strip()

    assert expected_cause_substr in log_string

    expected_context_substr = textwrap.dedent(
        """
        The above exception occurred during handling of the following exception:
        ValueError: inner error

        Stack Trace:
          File "
        """
    ).strip()

    assert expected_context_substr in log_string


@pytest.mark.parametrize("use_handler", [True, False])
def test_user_code_error_boundary_python_capture(use_handler):
    class TestHandler(logging.Handler):
        def __init__(self):
            self.captured = []
            super().__init__()

        def emit(self, record):
            self.captured.append(record)

    capture_handler = TestHandler()
    user_logger = logging.getLogger("user_logger")
    user_logger.addHandler(capture_handler)

    test_extra = {"foo": 1, "bar": {2: 3, "baz": 4}}

    with user_code_error_boundary(
        DagsterUserCodeExecutionError,
        lambda: "Some Error Message",
        log_manager=DagsterLogManager(
            dagster_handler=DagsterLogHandler(
                logging_metadata=DagsterLoggingMetadata(
                    run_id="123456", job_name="job", step_key="some_step"
                ),
                loggers=[user_logger] if not use_handler else [],
                handlers=[capture_handler] if use_handler else [],
            ),
            managed_loggers=[logging.getLogger("python_log")],
        ),
    ):
        python_log = logging.getLogger("python_log")
        python_log.setLevel(logging.INFO)

        python_log.debug("debug")
        python_log.critical("critical msg", extra=test_extra)

    assert len(capture_handler.captured) == 1
    captured_record = capture_handler.captured[0]

    assert captured_record.name == "python_log" if use_handler else "user_logger"
    assert captured_record.msg == "job - 123456 - some_step - critical msg"
    assert captured_record.levelno == logging.CRITICAL
    assert captured_record.dagster_meta["orig_message"] == "critical msg"

    for k, v in test_extra.items():
        assert getattr(captured_record, k) == v


def test_log_handler_emit_by_handlers_level():
    class TestHandler(logging.Handler):
        def __init__(self, level=logging.NOTSET):
            self.captured = []
            super().__init__(level)

        def emit(self, record):
            self.captured.append(record)

    capture_handler = TestHandler(level=logging.ERROR)
    test_extra = {"foo": 1, "bar": {2: 3, "baz": 4}}

    with user_code_error_boundary(
        DagsterUserCodeExecutionError,
        lambda: "Some Error Message",
        log_manager=DagsterLogManager(
            dagster_handler=DagsterLogHandler(
                logging_metadata=DagsterLoggingMetadata(
                    run_id="123456",
                    job_name="job",
                    step_key="some_step",
                ),
                loggers=[],
                handlers=[capture_handler],
            ),
            managed_loggers=[logging.getLogger()],
        ),
    ):
        python_log = logging.getLogger()
        python_log.setLevel(logging.INFO)

        python_log.debug("debug")
        python_log.critical("critical msg", extra=test_extra)

    assert len(capture_handler.captured) == 1
    captured_record = capture_handler.captured[0]

    assert captured_record.name == "root"
    assert captured_record.msg == "job - 123456 - some_step - critical msg"
    assert captured_record.levelno == logging.CRITICAL
    assert captured_record.dagster_meta["orig_message"] == "critical msg"

    for k, v in test_extra.items():
        assert getattr(captured_record, k) == v
