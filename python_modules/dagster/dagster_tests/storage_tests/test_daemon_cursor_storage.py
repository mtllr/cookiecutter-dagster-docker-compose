import pytest

from .test_run_storage import (
    create_in_memory_storage,
    create_legacy_run_storage,
    create_non_bucket_sqlite_run_storage,
    create_sqlite_run_storage,
)
from .utils.daemon_cursor_storage import TestDaemonCursorStorage


class TestDaemonCursorStorages(TestDaemonCursorStorage):
    __test__ = True

    @pytest.fixture(
        name="storage",
        params=[
            create_in_memory_storage,
            create_sqlite_run_storage,
            create_non_bucket_sqlite_run_storage,
            create_legacy_run_storage,
        ],
    )
    def cursor_storage(self, request):
        with request.param() as s:
            yield s
