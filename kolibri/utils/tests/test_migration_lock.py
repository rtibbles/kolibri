import errno
import os
import shutil

import pytest

from kolibri.utils.migration_lock import LockNotAcquired
from kolibri.utils.migration_lock import migration_lock
from kolibri.utils.migration_lock import MIGRATION_LOCK_FILE


def _clear_lock_file():
    if os.path.isdir(MIGRATION_LOCK_FILE):
        shutil.rmtree(MIGRATION_LOCK_FILE, ignore_errors=True)
    elif os.path.exists(MIGRATION_LOCK_FILE):
        os.remove(MIGRATION_LOCK_FILE)


@pytest.fixture(autouse=True)
def no_lock_file():
    _clear_lock_file()
    yield
    _clear_lock_file()


def test_holds_the_lock_while_the_body_runs():
    with migration_lock():
        with pytest.raises(LockNotAcquired):
            with migration_lock():
                pass


def test_releases_the_lock_on_exit():
    with migration_lock():
        pass
    # An unreleased lock would be refused.
    with migration_lock():
        pass


def test_releases_the_lock_when_the_body_raises():
    # An OSError, because the lock's own failures are OSErrors too and the two must
    # not be confused: EACCES is how a held lock announces itself.
    with pytest.raises(PermissionError):
        with migration_lock():
            raise PermissionError(errno.EACCES, "raised by a migration")
    with migration_lock():
        pass


@pytest.mark.skipif(not hasattr(os, "fork"), reason="Requires fork")
def test_takes_the_lock_from_a_process_that_died_holding_it():
    pid = os.fork()
    if pid == 0:
        with migration_lock():
            # Die holding the lock, as a killed process or a power cut would.
            os._exit(0)
    os.waitpid(pid, 0)
    with migration_lock():
        pass


def test_runs_unlocked_when_the_lock_file_cannot_be_opened():
    # A directory where the lock file belongs cannot be opened as a file.
    os.makedirs(MIGRATION_LOCK_FILE)
    ran = False
    with migration_lock():
        ran = True
    assert ran
