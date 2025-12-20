import threading
import time

import pytest

from kolibri.core.tasks.notifiers import PollingNotifier
from kolibri.core.tasks.notifiers import ThreadNotifier


class TestPollingNotifier:
    def test_wait_returns_false(self):
        """Polling notifier should always return False (timed out, not notified)."""
        notifier = PollingNotifier()
        start = time.time()
        result = notifier.wait_for_job(timeout=0.1)
        elapsed = time.time() - start

        assert result is False
        assert elapsed >= 0.1
        assert elapsed < 0.2

    def test_notify_is_noop(self):
        """Notify should not raise an exception."""
        notifier = PollingNotifier()
        notifier.notify()  # Should not raise

    def test_shutdown_is_noop(self):
        """Shutdown should not raise an exception."""
        notifier = PollingNotifier()
        notifier.shutdown()  # Should not raise


class TestThreadNotifier:
    def test_wait_returns_true_on_notify(self):
        """ThreadNotifier should return True when notified."""
        notifier = ThreadNotifier()
        result = [None]

        def waiter():
            result[0] = notifier.wait_for_job(timeout=5.0)

        t = threading.Thread(target=waiter)
        t.start()

        time.sleep(0.05)  # Let waiter start blocking
        notifier.notify()
        t.join(timeout=1.0)

        assert result[0] is True

    def test_wait_returns_false_on_timeout(self):
        """ThreadNotifier should return False on timeout."""
        notifier = ThreadNotifier()
        start = time.time()
        result = notifier.wait_for_job(timeout=0.1)
        elapsed = time.time() - start

        assert result is False
        assert elapsed >= 0.1

    def test_event_cleared_after_wait(self):
        """Event should be cleared after each wait, preventing spurious wakeups."""
        notifier = ThreadNotifier()
        notifier.notify()

        # First wait should return immediately
        result1 = notifier.wait_for_job(timeout=0.01)
        assert result1 is True

        # Second wait should timeout since event was cleared
        result2 = notifier.wait_for_job(timeout=0.05)
        assert result2 is False

    def test_multiple_notifies_coalesce(self):
        """Multiple rapid notifies should be handled correctly."""
        notifier = ThreadNotifier()

        # Send multiple notifies
        for _ in range(5):
            notifier.notify()

        # First wait should return immediately
        result = notifier.wait_for_job(timeout=0.01)
        assert result is True

        # Second wait should timeout (event cleared)
        result2 = notifier.wait_for_job(timeout=0.05)
        assert result2 is False

    def test_notify_wakes_multiple_waiters(self):
        """
        If somehow multiple threads are waiting, notify should wake at least one.
        In practice, we expect only one waiter (the job checker thread).
        """
        notifier = ThreadNotifier()
        results = [None, None]

        def waiter(index):
            results[index] = notifier.wait_for_job(timeout=2.0)

        t1 = threading.Thread(target=waiter, args=(0,))
        t2 = threading.Thread(target=waiter, args=(1,))
        t1.start()
        t2.start()

        time.sleep(0.05)  # Let both waiters start blocking
        notifier.notify()

        t1.join(timeout=1.0)
        t2.join(timeout=1.0)

        # At least one should have been notified
        assert True in results


class TestPostgresNotifier:
    """
    PostgreSQL tests require a real database connection.
    These tests are skipped if PostgreSQL is not available.
    """

    @pytest.fixture
    def postgres_connection(self):
        """Skip if PostgreSQL not available."""
        pytest.importorskip("psycopg2")
        from kolibri.utils import conf

        if conf.OPTIONS["Database"]["DATABASE_ENGINE"] != "postgres":
            pytest.skip("PostgreSQL not configured")

        from kolibri.core.tasks.utils import db_connection

        engine = db_connection()
        raw_conn = engine.raw_connection()
        yield raw_conn
        try:
            raw_conn.close()
        except Exception:
            pass
        engine.dispose()

    def test_invalid_channel_name_rejected(self, postgres_connection):
        """Channel names with invalid characters should be rejected."""
        from kolibri.core.tasks.notifiers import PostgresNotifier

        with pytest.raises(ValueError):
            PostgresNotifier(postgres_connection, channel="invalid;channel")

        with pytest.raises(ValueError):
            PostgresNotifier(postgres_connection, channel="invalid'channel")

        with pytest.raises(ValueError):
            PostgresNotifier(postgres_connection, channel="123invalid")

    def test_valid_channel_names_accepted(self, postgres_connection):
        """Valid channel names should be accepted."""
        from kolibri.core.tasks.notifiers import PostgresNotifier

        # Valid names
        notifier1 = PostgresNotifier(postgres_connection, channel="valid_channel")
        notifier1.shutdown()

        # Need a new connection for each notifier
        from kolibri.core.tasks.utils import db_connection

        engine = db_connection()
        raw_conn = engine.raw_connection()
        notifier2 = PostgresNotifier(raw_conn, channel="_underscore_start")
        notifier2.shutdown()
        raw_conn.close()
        engine.dispose()

    def test_listen_notify_roundtrip(self, postgres_connection):
        """Test that NOTIFY wakes up the waiting notifier."""
        from kolibri.core.tasks.notifiers import PostgresNotifier

        notifier = PostgresNotifier(postgres_connection, channel="test_channel")
        result = [None]

        def waiter():
            result[0] = notifier.wait_for_job(timeout=5.0)

        t = threading.Thread(target=waiter)
        t.start()

        time.sleep(0.1)  # Let LISTEN establish

        # Send NOTIFY from separate connection
        from kolibri.core.tasks.utils import db_connection

        engine = db_connection()
        with engine.connect() as conn:
            conn.execute("NOTIFY test_channel")
            conn.commit()
        engine.dispose()

        t.join(timeout=2.0)
        assert result[0] is True

        notifier.shutdown()

    def test_timeout_when_no_notify(self, postgres_connection):
        """Test that wait times out if no NOTIFY is received."""
        from kolibri.core.tasks.notifiers import PostgresNotifier

        notifier = PostgresNotifier(postgres_connection, channel="test_channel_2")

        start = time.time()
        result = notifier.wait_for_job(timeout=0.2)
        elapsed = time.time() - start

        assert result is False
        assert elapsed >= 0.2
        assert elapsed < 0.5

        notifier.shutdown()
