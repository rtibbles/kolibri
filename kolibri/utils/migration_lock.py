import errno
import logging
import os
from contextlib import contextmanager
from contextlib import ExitStack

from kolibri.utils.conf import KOLIBRI_HOME

logger = logging.getLogger(__name__)

MIGRATION_LOCK_FILE = os.path.join(KOLIBRI_HOME, "migration.lock")


class LockNotAcquired(Exception):
    pass


if os.name == "posix":
    import fcntl

    HELD_ERRNOS = (errno.EACCES, errno.EAGAIN)

    def _lock(fileno):
        fcntl.flock(fileno, fcntl.LOCK_EX | fcntl.LOCK_NB)


else:
    import msvcrt

    HELD_ERRNOS = (errno.EACCES, errno.EDEADLOCK)

    def _lock(fileno):
        msvcrt.locking(fileno, msvcrt.LK_NBLCK, 1)


def _lock_exclusively(fileno):
    """
    Raises LockNotAcquired if another process holds the lock, or OSError if this
    filesystem has no locking to offer - some network shares fail that way.
    """
    try:
        _lock(fileno)
    except OSError as e:
        if e.errno in HELD_ERRNOS:
            raise LockNotAcquired(MIGRATION_LOCK_FILE)
        raise


@contextmanager
def migration_lock():
    """
    Hold an exclusive lock across processes for the duration of the block, raising
    LockNotAcquired if another process holds it.

    The lock is the kernel's, not the file's contents, so it is released when this
    process exits however it exits: a crash or a power cut leaves nothing stale behind.
    """
    # The stack closes the handle after the block rather than before, because closing
    # is what releases the lock. Nothing is entered if the file would not open.
    with ExitStack() as stack:
        try:
            handle = stack.enter_context(open(MIGRATION_LOCK_FILE, "a"))
            _lock_exclusively(handle.fileno())
        except OSError:
            # Being unable to lock is survivable; refusing to start is not.
            logger.warning(
                "Could not take the migration lock at %s, continuing without it",
                MIGRATION_LOCK_FILE,
                exc_info=True,
            )
        yield
