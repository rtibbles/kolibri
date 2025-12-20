"""
Job notification mechanisms for event-driven job processing.

This module provides notifier implementations for different database backends:
- PostgreSQL: Uses LISTEN/NOTIFY for true event-driven notifications
- SQLite: Uses threading.Event for single-process notifications
- Fallback: Uses adaptive polling for unsupported backends
"""
import logging
import re
import threading
import time

logger = logging.getLogger(__name__)


class BaseNotifier:
    """
    Base class for job notification mechanisms.

    Notifiers are used by workers to efficiently wait for new jobs
    instead of continuously polling the database.
    """

    def __init__(self, poll_interval):
        """
        Initialize the notifier.

        :param poll_interval: Maximum time to wait between job checks, even without notification.
        """
        self.poll_interval = poll_interval

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
        Signal that a job has been enqueued.

        This is a no-op for some implementations (e.g., PostgreSQL where
        NOTIFY is done in the database transaction).
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


class PollingNotifier(BaseNotifier):
    """
    Fallback notifier that uses simple polling.

    Used when no better notification mechanism is available.
    """

    def __init__(self):
        super().__init__(poll_interval=1.0)

    def _wait_for_notification(self, timeout):
        """
        Sleep for the minimum of timeout and poll_interval.

        Always returns False since we're just sleeping, not receiving notifications.
        """
        time.sleep(min(timeout, self.poll_interval))
        return False

    def notify(self):
        """No-op for polling notifier."""
        pass


class ThreadNotifier(BaseNotifier):
    """
    Notifier that uses threading.Event for in-process signaling.

    This is used for SQLite deployments where all workers run in
    the same process and can share a threading.Event.
    """

    def __init__(self):
        super().__init__(poll_interval=30.0)
        self._event = threading.Event()

    def _wait_for_notification(self, timeout):
        """
        Wait on the threading.Event.

        Returns True if the event was set (job notification received),
        False if we timed out waiting.
        """
        effective_timeout = min(timeout, self.poll_interval)
        notified = self._event.wait(timeout=effective_timeout)
        self._event.clear()
        return notified

    def notify(self):
        """
        Signal that a job has been enqueued.

        Wakes up any thread waiting on the event.
        """
        self._event.set()


# Validate channel name: alphanumeric and underscores only, starting with letter or underscore
CHANNEL_PATTERN = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")


class PostgresNotifier(BaseNotifier):
    """
    Notifier that uses PostgreSQL LISTEN/NOTIFY for event-driven notifications.

    This creates a dedicated connection that listens for notifications
    on a specified channel. When a job is enqueued, the storage layer
    issues a NOTIFY in the same transaction as the INSERT, ensuring
    atomic notification.
    """

    def __init__(self, raw_connection, channel):
        """
        Initialize the PostgreSQL notifier.

        :param raw_connection: A raw psycopg2 connection (from engine.raw_connection()).
        :param channel: The channel name to listen on.
        :raises ValueError: If channel name contains invalid characters.
        """
        super().__init__(poll_interval=30.0)

        if not CHANNEL_PATTERN.match(channel):
            raise ValueError(f"Invalid channel name: {channel}")

        self._channel = channel
        self._connection = raw_connection
        self._connection_valid = True

        try:
            # Set autocommit mode for LISTEN to work properly
            self._connection.set_isolation_level(0)
            cursor = self._connection.cursor()
            cursor.execute(f"LISTEN {self._channel}")
            cursor.close()
        except Exception as e:
            logger.warning(f"Failed to setup LISTEN: {e}")
            self._connection_valid = False

    def _wait_for_notification(self, timeout):
        """
        Wait for a PostgreSQL NOTIFY event using select().

        Falls back to sleeping if the connection is no longer valid.
        """
        if not self._connection_valid:
            time.sleep(min(timeout, self.poll_interval))
            return False

        try:
            import select

            effective_timeout = min(timeout, self.poll_interval)
            readable, _, _ = select.select(
                [self._connection], [], [], effective_timeout
            )

            if readable:
                self._connection.poll()
                # Drain all pending notifications
                while self._connection.notifies:
                    self._connection.notifies.pop(0)
                return True
            return False
        except Exception as e:
            logger.warning(
                f"Error waiting for notification, falling back to polling: {e}"
            )
            self._connection_valid = False
            time.sleep(min(timeout, self.poll_interval))
            return False

    def notify(self):
        """
        No-op for PostgreSQL.

        NOTIFY is issued by the Storage layer in the same transaction
        as the job INSERT, ensuring atomic notification.
        """
        pass

    def shutdown(self):
        """
        Clean up the dedicated LISTEN connection.
        """
        if self._connection:
            try:
                cursor = self._connection.cursor()
                cursor.execute(f"UNLISTEN {self._channel}")
                cursor.close()
                self._connection.close()
            except Exception as e:
                logger.warning(f"Error during notifier shutdown: {e}")
            finally:
                self._connection = None
                self._connection_valid = False
