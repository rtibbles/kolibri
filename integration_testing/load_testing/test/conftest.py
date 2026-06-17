import os
import sys

import pytest

# Modules in load_testing/ import each other flatly (`from logger import info`),
# so tests need the directory itself on sys.path.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture()
def hub(tmp_path):
    # Deferred import: hub.py is only importable after the sys.path insert
    # above, and import-reordering hooks would move a top-level import first.
    from hub import Hub

    # poll_hold shortened so empty-queue long-polls don't sit for 25s in tests
    hub = Hub(
        host="127.0.0.1", port=0, token_file=str(tmp_path / "token"), poll_hold=0.5
    )
    hub.start()
    yield hub
    hub.stop()
