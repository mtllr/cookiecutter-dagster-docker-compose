import pytest
from dagster._core.test_utils import instance_for_test


@pytest.fixture()
def instance():
    with instance_for_test() as instance:
        yield instance
