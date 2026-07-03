"""
Job notification mechanisms for event-driven job processing.

This module provides notifier implementations for different database backends:
- PostgreSQL: Uses LISTEN/NOTIFY for cross-process event-driven notifications
- Everything else: Uses threading.Event for in-process notifications
"""

import logging
import re
import select
import socket
import threading
import time

from django.db import connections

from kolibri.core.tasks.constants import JOB_NOTIFICATION_CHANNEL
from kolibri.core.tasks.models import Job as ORMJob

logger = logging.getLogger(__name__)


class BaseNotifier:
    """
    Base class for job notification mechanisms.

    Notifiers are used by workers to efficiently wait for new jobs
    instead of continuously polling the database.
    """

    # Whether notifications reach workers in other processes. When False, an
    # isolated worker process can only discover jobs enqueued elsewhere by
    # polling, so the supervisor falls back to a tight poll interval.
    supports_cross_process_notify = False

    def wait_for_job(self, timeout):
        """
        Wait for notification that a job is available, or timeout.

        Returns True if notification received, False if timed out.
        Caller should process jobs regardless of return value.

        :param timeout: Maximum time to wait in seconds.
        :return: True if notified, False if timed out.
        """
        return self._wait_for_notification(timeout)

    def notify(self):
        """
        Signal that a job event has occurred, waking a blocked wait_for_job.

        The default is a no-op; notifiers that block on an interruptible
        primitive override this to wake the wait (used on shutdown).
        """
        pass

    def shutdown(self):
        """
        Clean up any resources held by the notifier.
        """
        pass

    def _wait_for_notification(self, timeout):
        """
        Abstract method for subclasses to implement waiting logic.

        :param timeout: Maximum time to wait in seconds.
        :return: True if notified, False if timed out.
        """
        raise NotImplementedError


class EventNotifier(BaseNotifier):
    """
    Blocks on a threading.Event, woken in-process by notify().

    Used for every non-PostgreSQL backend. On SQLite all enqueuers share the
    worker's process, so the event is sufficient. On other backends an isolated
    worker process discovers cross-process enqueues by polling (the supervisor's
    loop_interval) instead - the event still wakes in-process enqueuers, and
    lets shutdown interrupt a blocked wait promptly rather than waiting out the
    timeout.
    """

    def __init__(self):
        self._event = threading.Event()

    def _wait_for_notification(self, timeout):
        """
        Wait on the threading.Event.

        Returns True if the event was set (job notification received),
        False if we timed out waiting.
        """
        notified = self._event.wait(timeout=timeout)
        if notified:
            # Only consume the event when the wait was satisfied - clearing
            # unconditionally would erase a notify() that arrived after the
            # wait timed out, losing the wakeup.
            self._event.clear()
        return notified

    def notify(self):
        """
        Signal that a job event has occurred.

        Wakes up any thread waiting on the event.
        """
        self._event.set()


# Validate channel name: alphanumeric and underscores only, starting with letter or underscore
CHANNEL_PATTERN = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")

# Minimum seconds between attempts to re-open a dropped LISTEN connection, so a
# persistently unreachable database is not hit on every wait.
RECONNECT_INTERVAL = 5.0


class PostgresNotifier(BaseNotifier):
    """
    Notifier that uses PostgreSQL LISTEN/NOTIFY for event-driven notifications.

    This opens a dedicated connection that listens for notifications on a
    specified channel - Django's connections are thread-local and used for
    ORM queries by their owning threads, so they cannot also be waited on
    from the job checker thread. The storage layer issues NOTIFY on the
    channel whenever jobs need the worker's attention.

    A self-pipe is also waited on so notify() can interrupt the wait even when
    no NOTIFY is deliverable (e.g. shutdown, or a dropped LISTEN connection).
    """

    # LISTEN/NOTIFY is delivered across connections and processes.
    supports_cross_process_notify = True

    def __init__(self, channel):
        """
        Initialize the PostgreSQL notifier.

        :param channel: The channel name to listen on.
        :raises ValueError: If channel name contains invalid characters.
        """
        if not CHANNEL_PATTERN.match(channel):
            raise ValueError(f"Invalid channel name: {channel}")

        self._channel = channel
        self._connection = None
        self._connection_valid = False
        self._last_reconnect = None
        # Self-pipe so notify() can wake a blocked select() with no NOTIFY to
        # rely on - this is how shutdown stops the supervisor loop promptly.
        self._wake_reader, self._wake_writer = socket.socketpair()
        self._wake_reader.setblocking(False)

        self._setup_connection()

    def _setup_connection(self):
        """Open the dedicated LISTEN connection."""
        try:
            django_connection = connections[ORMJob.objects.db]
            self._connection = django_connection.get_new_connection(
                django_connection.get_connection_params()
            )
            # LISTEN requires autocommit so that notifications arrive as
            # they are delivered, rather than at the end of a transaction
            self._connection.autocommit = True
            cursor = self._connection.cursor()
            cursor.execute(f"LISTEN {self._channel}")
            cursor.close()
            self._connection_valid = True
        except Exception as e:
            logger.warning(f"Failed to setup LISTEN: {e}")
            self._close_connection()

    def _maybe_reconnect(self):
        """
        Retry the LISTEN connection, at most once per RECONNECT_INTERVAL, so a
        transient outage recovers to event-driven delivery instead of leaving
        the worker on slow polling for the rest of its life.
        """
        now = time.monotonic()
        if (
            self._last_reconnect is not None
            and now - self._last_reconnect < RECONNECT_INTERVAL
        ):
            return
        self._last_reconnect = now
        self._setup_connection()

    def _wait_for_notification(self, timeout):
        """
        Wait for a PostgreSQL NOTIFY, or until notify() pokes the self-pipe.

        With no live LISTEN connection, waits on the self-pipe alone - the wait
        still honours the timeout and stays interruptible - and retries the
        connection so delivery can recover.
        """
        if not self._connection_valid:
            self._maybe_reconnect()

        read_set = [self._wake_reader]
        if self._connection_valid:
            read_set.append(self._connection)

        try:
            readable, _, _ = select.select(read_set, [], [], timeout)
        except Exception as e:
            logger.warning(f"Error waiting for notification: {e}")
            self._close_connection()
            return False

        if not readable:
            return False

        if self._wake_reader in readable:
            self._drain_wake()
        if self._connection_valid and self._connection in readable:
            try:
                self._connection.poll()
                # Drain all pending notifications
                del self._connection.notifies[:]
            except Exception as e:
                logger.warning(f"Error reading notification: {e}")
                self._close_connection()
        return True

    def notify(self):
        """
        Poke the self-pipe to wake a blocked wait. Used on shutdown; job
        NOTIFYs otherwise arrive over the LISTEN connection.
        """
        if self._wake_writer is not None:
            try:
                self._wake_writer.send(b"\x00")
            except OSError:
                pass

    def _drain_wake(self):
        sock = self._wake_reader
        if sock is None:
            return
        try:
            while sock.recv(4096):
                pass
        except (BlockingIOError, OSError):
            pass

    def _close_connection(self):
        """Close the LISTEN connection, leaving the self-pipe intact."""
        self._connection_valid = False
        if self._connection is not None:
            try:
                self._connection.close()
            except Exception as e:
                logger.warning(f"Error closing notifier connection: {e}")
            self._connection = None

    def shutdown(self):
        """Close the LISTEN connection and release the self-pipe."""
        self._close_connection()
        for attr in ("_wake_writer", "_wake_reader"):
            sock = getattr(self, attr, None)
            if sock is not None:
                try:
                    sock.close()
                except OSError:
                    pass
                setattr(self, attr, None)


class NotifierSingleton(type):
    """
    Metaclass that makes ``JobNotifier()`` return one shared instance per
    process, so consumers instantiate it like a normal class with no module
    global to coordinate through.

    Modelled on ``kolibri.plugins.SingletonMeta``, with two additions the
    notifier needs: construction is locked (it is built from both the
    supervisor and enqueuer threads) and ``reset()`` tears the instance down.
    """

    def __init__(cls, name, bases, namespace):
        super().__init__(name, bases, namespace)
        cls._instance = None
        cls._lock = threading.Lock()

    def __call__(cls, *args, **kwargs):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__call__(*args, **kwargs)
        return cls._instance

    def reset(cls):
        """Shut down the shared instance so the next call builds a fresh one."""
        with cls._lock:
            instance, cls._instance = cls._instance, None
        if instance is not None:
            instance.shutdown()


class JobNotifier(metaclass=NotifierSingleton):
    """
    Process-wide job notifier. Instantiating returns the one shared instance,
    which delegates to PostgresNotifier (LISTEN/NOTIFY, cross-process) on
    PostgreSQL and EventNotifier (in-process threading.Event) elsewhere.

    The supervisor waits on it and the storage layer wakes it; both just call
    ``JobNotifier()``. Call ``JobNotifier.reset()`` on worker shutdown.
    """

    def __init__(self):
        vendor = connections[ORMJob.objects.db].vendor
        if vendor == "postgresql":
            self._backend = PostgresNotifier(channel=JOB_NOTIFICATION_CHANNEL)
        else:
            self._backend = EventNotifier()

    @property
    def supports_cross_process_notify(self):
        return self._backend.supports_cross_process_notify

    def wait_for_job(self, timeout):
        return self._backend.wait_for_job(timeout)

    def notify(self):
        self._backend.notify()

    def shutdown(self):
        self._backend.shutdown()
