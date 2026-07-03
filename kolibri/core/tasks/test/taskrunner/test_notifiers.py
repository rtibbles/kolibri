import threading
import time

import pytest
from django.db import connections

from kolibri.core.tasks.models import Job as ORMJob
from kolibri.core.tasks.notifiers import EventNotifier
from kolibri.core.tasks.notifiers import PostgresNotifier


class TestEventNotifier:
    def test_notify_wakes_a_blocked_wait(self):
        """A blocked wait returns True as soon as notify() fires."""
        notifier = EventNotifier()
        started = threading.Event()
        result = [None]

        def waiter():
            started.set()
            result[0] = notifier.wait_for_job(timeout=5.0)

        t = threading.Thread(target=waiter)
        t.start()
        started.wait(timeout=1.0)  # waiter thread is up

        notifier.notify()
        # The waiter's own timeout is 5s; finishing well inside that proves it
        # was woken by notify() rather than sleeping the wait out.
        t.join(timeout=2.0)

        assert not t.is_alive()
        assert result[0] is True

    def test_unnotified_wait_times_out(self):
        """An unnotified wait returns False after roughly the timeout."""
        notifier = EventNotifier()
        start = time.monotonic()
        result = notifier.wait_for_job(timeout=0.1)
        elapsed = time.monotonic() - start

        assert result is False
        assert elapsed >= 0.1

    def test_shutdown_is_noop(self):
        """Shutdown should not raise an exception."""
        notifier = EventNotifier()
        notifier.shutdown()

    def test_event_cleared_after_wait(self):
        """Event should be cleared after each wait, preventing spurious wakeups."""
        notifier = EventNotifier()
        notifier.notify()

        # First wait should return immediately
        result1 = notifier.wait_for_job(timeout=0.01)
        assert result1 is True

        # Second wait should timeout since event was cleared
        result2 = notifier.wait_for_job(timeout=0.05)
        assert result2 is False

    def test_notify_during_timeout_window_not_lost(self):
        """
        A notify() arriving between a timed-out wait() and the notifier's
        bookkeeping must not be erased - it should satisfy the next wait.
        """
        notifier = EventNotifier()
        original_wait = notifier._event.wait

        def wait_then_notify(timeout=None):
            result = original_wait(timeout)
            # Simulate a concurrent notify() landing in the window between
            # the wait returning (timed out) and wait_for_job returning
            notifier.notify()
            return result

        notifier._event.wait = wait_then_notify
        assert notifier.wait_for_job(timeout=0.01) is False
        notifier._event.wait = original_wait

        # The notification from the race window must still be pending
        assert notifier.wait_for_job(timeout=0.01) is True

    def test_multiple_notifies_coalesce(self):
        """Multiple rapid notifies should be handled correctly."""
        notifier = EventNotifier()

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
        notifier = EventNotifier()
        results = [None, None]
        ready = threading.Barrier(3)

        def waiter(index):
            ready.wait()
            results[index] = notifier.wait_for_job(timeout=2.0)

        t1 = threading.Thread(target=waiter, args=(0,))
        t2 = threading.Thread(target=waiter, args=(1,))
        t1.start()
        t2.start()

        ready.wait()  # both waiters are up
        notifier.notify()

        t1.join(timeout=2.0)
        t2.join(timeout=2.0)

        # At least one should have been notified
        assert True in results


class TestPostgresNotifier:
    """
    PostgreSQL tests require a real database connection.
    These tests are skipped if PostgreSQL is not available.
    """

    @pytest.fixture
    def is_postgres(self):
        """Skip if PostgreSQL not available."""
        if connections[ORMJob.objects.db].vendor != "postgresql":
            pytest.skip("PostgreSQL not configured")

    def _degraded_notifier(self):
        """
        A PostgresNotifier with no live LISTEN connection - the state a worker
        lands in on any non-PostgreSQL backend, or after the LISTEN connection
        drops. The self-pipe wake path must work regardless.
        """
        notifier = PostgresNotifier(channel="test_kolibri_channel")
        # Normalise to the degraded state so the test is deterministic even
        # when a real PostgreSQL connection happened to be available.
        notifier._close_connection()
        return notifier

    def test_notify_interrupts_degraded_wait(self):
        # With no LISTEN connection there are no NOTIFYs, but notify() must
        # still wake a blocked wait promptly - this is what lets shutdown stop
        # the supervisor loop instead of hanging until the timeout elapses.
        notifier = self._degraded_notifier()
        try:
            started = threading.Event()
            result = [None]

            def waiter():
                started.set()
                result[0] = notifier.wait_for_job(timeout=5.0)

            t = threading.Thread(target=waiter)
            t.start()
            started.wait(timeout=1.0)  # waiter thread is up

            notifier.notify()
            # Finishing well inside the 5s wait proves notify() woke it.
            t.join(timeout=2.0)

            assert not t.is_alive()
            assert result[0] is True
        finally:
            notifier.shutdown()

    def test_degraded_wait_times_out(self):
        # With nothing to wait on, a degraded wait still returns False after
        # roughly the timeout rather than blocking forever.
        notifier = self._degraded_notifier()
        try:
            start = time.monotonic()
            result = notifier.wait_for_job(timeout=0.1)
            elapsed = time.monotonic() - start

            assert result is False
            assert elapsed >= 0.1
        finally:
            notifier.shutdown()

    def test_degraded_wait_retries_connection_throttled(self):
        # A dropped LISTEN connection is retried, not written off for the life
        # of the process (which would silently degrade cross-process job pickup
        # to slow polling) - but retries are throttled so a persistently
        # unreachable database is not hammered on every wait.
        notifier = self._degraded_notifier()
        try:
            attempts = []
            original = notifier._setup_connection

            def counting():
                attempts.append(1)
                original()

            notifier._setup_connection = counting

            notifier.wait_for_job(timeout=0.01)
            assert len(attempts) == 1

            notifier.wait_for_job(timeout=0.01)
            assert len(attempts) == 1  # throttled - no second attempt
        finally:
            notifier.shutdown()

    def test_invalid_channel_name_rejected(self):
        """Channel names with invalid characters should be rejected."""
        with pytest.raises(ValueError):
            PostgresNotifier(channel="invalid;channel")

        with pytest.raises(ValueError):
            PostgresNotifier(channel="invalid'channel")

        with pytest.raises(ValueError):
            PostgresNotifier(channel="123invalid")

    def test_uses_dedicated_connection(self, is_postgres):
        """
        The LISTEN connection must not be Django's thread-local connection -
        that connection is used for ORM queries by other threads, and the
        job checker thread waits on the notifier's connection concurrently.
        """
        notifier = PostgresNotifier(channel="test_kolibri_channel")
        try:
            assert notifier._connection is not None
            assert notifier._connection is not connections[ORMJob.objects.db].connection
        finally:
            notifier.shutdown()

    def test_shutdown_closes_connection(self, is_postgres):
        """Shutdown should close the dedicated LISTEN connection."""
        notifier = PostgresNotifier(channel="test_kolibri_channel")
        connection = notifier._connection
        notifier.shutdown()

        assert connection.closed
        assert notifier._connection is None
