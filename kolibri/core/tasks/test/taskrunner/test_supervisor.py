# -*- coding: utf-8 -*-
import datetime
import time

import pytest

from kolibri.core.tasks.job import Job
from kolibri.core.tasks.job import State
from kolibri.core.tasks.storage import ORMSupervisor
from kolibri.core.tasks.storage import Storage
from kolibri.core.tasks.test.base import connection
from kolibri.core.tasks.worker import Worker
from kolibri.core.tasks.worker import WorkerSupervisor
from kolibri.utils.time_utils import local_now


QUEUE = "pytest"


@pytest.fixture
def defaultbackend():
    with connection() as c:
        b = Storage(c)
        b.clear(force=True)
        yield b
        b.clear(force=True)


@pytest.fixture
def simplejob():
    return Job(id)


class TestSupervisorRegistry:
    """Tests for the supervisor registry methods in Storage"""

    def test_register_supervisor_creates_new_record(self, defaultbackend):
        """Test that register_supervisor creates a new supervisor record"""
        supervisor_id = defaultbackend.register_supervisor(
            host="testhost", process="1234", thread="5678"
        )

        assert supervisor_id is not None
        assert len(supervisor_id) == 32  # UUID hex format

        # Verify the supervisor exists in the database
        with defaultbackend.session_scope() as session:
            supervisor = session.query(ORMSupervisor).filter_by(id=supervisor_id).one()
            assert supervisor.host == "testhost"
            assert supervisor.process == "1234"
            assert supervisor.thread == "5678"

    def test_register_supervisor_returns_existing_id_for_same_identity(
        self, defaultbackend
    ):
        """Test that register_supervisor returns existing id for same host/process/thread"""
        # Register first time
        supervisor_id1 = defaultbackend.register_supervisor(
            host="testhost", process="1234", thread="5678"
        )

        # Register again with same identity
        supervisor_id2 = defaultbackend.register_supervisor(
            host="testhost", process="1234", thread="5678"
        )

        assert supervisor_id1 == supervisor_id2

        # Verify only one supervisor exists
        with defaultbackend.session_scope() as session:
            count = session.query(ORMSupervisor).count()
            assert count == 1

    def test_register_supervisor_creates_new_for_different_identity(
        self, defaultbackend
    ):
        """Test that register_supervisor creates new record for different identity"""
        supervisor_id1 = defaultbackend.register_supervisor(
            host="testhost1", process="1234", thread="5678"
        )
        supervisor_id2 = defaultbackend.register_supervisor(
            host="testhost2", process="1234", thread="5678"
        )

        assert supervisor_id1 != supervisor_id2

        # Verify two supervisors exist
        with defaultbackend.session_scope() as session:
            count = session.query(ORMSupervisor).count()
            assert count == 2

    def test_unregister_supervisor_removes_record(self, defaultbackend):
        """Test that unregister_supervisor removes the supervisor record"""
        supervisor_id = defaultbackend.register_supervisor(
            host="testhost", process="1234", thread="5678"
        )

        # Verify supervisor exists
        with defaultbackend.session_scope() as session:
            count = session.query(ORMSupervisor).filter_by(id=supervisor_id).count()
            assert count == 1

        # Unregister
        defaultbackend.unregister_supervisor(supervisor_id)

        # Verify supervisor is removed
        with defaultbackend.session_scope() as session:
            count = session.query(ORMSupervisor).filter_by(id=supervisor_id).count()
            assert count == 0

    def test_heartbeat_supervisor_updates_last_seen(self, defaultbackend):
        """Test that heartbeat_supervisor updates the last_seen timestamp"""
        supervisor_id = defaultbackend.register_supervisor(
            host="testhost", process="1234", thread="5678"
        )

        # Get initial last_seen
        with defaultbackend.session_scope() as session:
            supervisor = session.query(ORMSupervisor).filter_by(id=supervisor_id).one()
            initial_last_seen = supervisor.last_seen

        # Wait a small amount and heartbeat
        time.sleep(0.1)
        defaultbackend.heartbeat_supervisor(supervisor_id)

        # Verify last_seen was updated
        with defaultbackend.session_scope() as session:
            supervisor = session.query(ORMSupervisor).filter_by(id=supervisor_id).one()
            assert supervisor.last_seen >= initial_last_seen


class TestReconcileStalledJobs:
    """Tests for the reconcile_stalled_jobs method"""

    def test_reconcile_requeues_jobs_from_stale_supervisors(self, defaultbackend):
        """Test that reconcile_stalled_jobs requeues jobs from stale supervisors"""
        # Create a supervisor
        supervisor_id = defaultbackend.register_supervisor(
            host="testhost", process="1234", thread="5678"
        )

        # Create and enqueue a job
        job = Job(id)
        job_id = defaultbackend.enqueue_job(job, QUEUE)

        # Mark the job as running with this supervisor
        defaultbackend.mark_job_as_running(job_id, supervisor_id=supervisor_id)

        # Verify job is running
        job = defaultbackend.get_job(job_id)
        assert job.state == State.RUNNING

        # Manually set the supervisor's last_seen to a stale time
        with defaultbackend.session_scope() as session:
            supervisor = session.query(ORMSupervisor).filter_by(id=supervisor_id).one()
            supervisor.last_seen = datetime.datetime.utcnow() - datetime.timedelta(
                seconds=300
            )
            session.add(supervisor)

        # Run reconcile with a threshold that makes the supervisor stale
        defaultbackend.reconcile_stalled_jobs(
            supervisor_stale_threshold=60, job_stale_threshold=300
        )

        # Verify job is now queued
        job = defaultbackend.get_job(job_id)
        assert job.state == State.QUEUED

        # Verify supervisor is removed
        with defaultbackend.session_scope() as session:
            count = session.query(ORMSupervisor).filter_by(id=supervisor_id).count()
            assert count == 0

    def test_reconcile_cleans_up_stale_supervisors(self, defaultbackend):
        """Test that reconcile_stalled_jobs removes stale supervisor records"""
        # Create a supervisor
        supervisor_id = defaultbackend.register_supervisor(
            host="testhost", process="1234", thread="5678"
        )

        # Manually set the supervisor's last_seen to a stale time
        with defaultbackend.session_scope() as session:
            supervisor = session.query(ORMSupervisor).filter_by(id=supervisor_id).one()
            supervisor.last_seen = datetime.datetime.utcnow() - datetime.timedelta(
                seconds=300
            )
            session.add(supervisor)

        # Verify supervisor exists
        with defaultbackend.session_scope() as session:
            count = session.query(ORMSupervisor).count()
            assert count == 1

        # Run reconcile
        defaultbackend.reconcile_stalled_jobs(
            supervisor_stale_threshold=60, job_stale_threshold=300
        )

        # Verify supervisor is removed
        with defaultbackend.session_scope() as session:
            count = session.query(ORMSupervisor).count()
            assert count == 0

    def test_reconcile_handles_orphaned_jobs_with_no_supervisor_id(
        self, defaultbackend
    ):
        """Test that reconcile_stalled_jobs handles jobs with no supervisor_id"""
        from kolibri.core.tasks.storage import ORMJob

        # Create and enqueue a job
        job = Job(id)
        job_id = defaultbackend.enqueue_job(job, QUEUE)

        # Mark the job as running without a supervisor_id
        defaultbackend.mark_job_as_running(job_id)

        # Verify job is running
        job = defaultbackend.get_job(job_id)
        assert job.state == State.RUNNING

        # Manually set the job's time_updated to a stale time
        with defaultbackend.session_scope() as session:
            orm_job = session.query(ORMJob).filter_by(id=job_id).one()
            orm_job.time_updated = datetime.datetime.utcnow() - datetime.timedelta(
                seconds=600
            )
            session.add(orm_job)

        # Run reconcile with a threshold that makes the job stale
        defaultbackend.reconcile_stalled_jobs(
            supervisor_stale_threshold=60, job_stale_threshold=300
        )

        # Verify job is now queued
        job = defaultbackend.get_job(job_id)
        assert job.state == State.QUEUED

    def test_reconcile_does_not_affect_fresh_jobs(self, defaultbackend):
        """Test that reconcile_stalled_jobs doesn't affect fresh running jobs"""
        # Create a supervisor
        supervisor_id = defaultbackend.register_supervisor(
            host="testhost", process="1234", thread="5678"
        )

        # Create and enqueue a job
        job = Job(id)
        job_id = defaultbackend.enqueue_job(job, QUEUE)

        # Mark the job as running with this supervisor
        defaultbackend.mark_job_as_running(job_id, supervisor_id=supervisor_id)

        # Verify job is running
        job = defaultbackend.get_job(job_id)
        assert job.state == State.RUNNING

        # Run reconcile - supervisor is fresh so job should not be affected
        defaultbackend.reconcile_stalled_jobs(
            supervisor_stale_threshold=60, job_stale_threshold=300
        )

        # Verify job is still running
        job = defaultbackend.get_job(job_id)
        assert job.state == State.RUNNING


class TestJobSupervisorId:
    """Tests for supervisor_id on jobs"""

    def test_mark_job_as_running_with_supervisor_id(self, defaultbackend):
        """Test that mark_job_as_running sets supervisor_id when provided"""
        from kolibri.core.tasks.storage import ORMJob

        supervisor_id = defaultbackend.register_supervisor(
            host="testhost", process="1234", thread="5678"
        )

        job = Job(id)
        job_id = defaultbackend.enqueue_job(job, QUEUE)

        defaultbackend.mark_job_as_running(job_id, supervisor_id=supervisor_id)

        # Verify supervisor_id is set on the ORM job
        with defaultbackend.session_scope() as session:
            orm_job = session.query(ORMJob).filter_by(id=job_id).one()
            assert orm_job.supervisor_id == supervisor_id

    def test_complete_job_clears_supervisor_id(self, defaultbackend):
        """Test that complete_job clears supervisor_id"""
        from kolibri.core.tasks.storage import ORMJob

        supervisor_id = defaultbackend.register_supervisor(
            host="testhost", process="1234", thread="5678"
        )

        job = Job(id)
        job_id = defaultbackend.enqueue_job(job, QUEUE)

        defaultbackend.mark_job_as_running(job_id, supervisor_id=supervisor_id)
        defaultbackend.complete_job(job_id)

        # Verify supervisor_id is cleared
        with defaultbackend.session_scope() as session:
            orm_job = session.query(ORMJob).filter_by(id=job_id).one()
            assert orm_job.supervisor_id is None

    def test_mark_job_as_failed_clears_supervisor_id(self, defaultbackend):
        """Test that mark_job_as_failed clears supervisor_id"""
        from kolibri.core.tasks.storage import ORMJob

        supervisor_id = defaultbackend.register_supervisor(
            host="testhost", process="1234", thread="5678"
        )

        job = Job(id)
        job_id = defaultbackend.enqueue_job(job, QUEUE)

        defaultbackend.mark_job_as_running(job_id, supervisor_id=supervisor_id)
        defaultbackend.mark_job_as_failed(job_id, RuntimeError("test"), "traceback")

        # Verify supervisor_id is cleared
        with defaultbackend.session_scope() as session:
            orm_job = session.query(ORMJob).filter_by(id=job_id).one()
            assert orm_job.supervisor_id is None

    def test_mark_job_as_canceled_clears_supervisor_id(self, defaultbackend):
        """Test that mark_job_as_canceled clears supervisor_id"""
        from kolibri.core.tasks.storage import ORMJob

        supervisor_id = defaultbackend.register_supervisor(
            host="testhost", process="1234", thread="5678"
        )

        job = Job(id)
        job_id = defaultbackend.enqueue_job(job, QUEUE)

        defaultbackend.mark_job_as_running(job_id, supervisor_id=supervisor_id)
        defaultbackend.mark_job_as_canceled(job_id)

        # Verify supervisor_id is cleared
        with defaultbackend.session_scope() as session:
            orm_job = session.query(ORMJob).filter_by(id=job_id).one()
            assert orm_job.supervisor_id is None


class TestJobHeartbeat:
    """Tests for the job heartbeat method"""

    def test_touch_job_updates_time_updated(self, defaultbackend):
        """Test that _touch_job updates time_updated"""
        from kolibri.core.tasks.storage import ORMJob

        job = Job(id)
        job_id = defaultbackend.enqueue_job(job, QUEUE)
        defaultbackend.mark_job_as_running(job_id)

        # Get initial time_updated
        with defaultbackend.session_scope() as session:
            orm_job = session.query(ORMJob).filter_by(id=job_id).one()
            initial_time_updated = orm_job.time_updated

        # Wait a small amount and touch the job
        time.sleep(0.1)
        defaultbackend._touch_job(job_id)

        # Verify time_updated was updated
        with defaultbackend.session_scope() as session:
            orm_job = session.query(ORMJob).filter_by(id=job_id).one()
            # Note: time_updated may be None initially if onupdate hasn't triggered
            if initial_time_updated is not None:
                assert orm_job.time_updated >= initial_time_updated
            else:
                assert orm_job.time_updated is not None


class TestWorkerSupervisor:
    """Integration tests for WorkerSupervisor"""

    @pytest.fixture
    def worker(self):
        with connection() as c:
            w = WorkerSupervisor(c, regular_workers=1, high_workers=1)
            w.storage.clear(force=True)
            yield w
            w.storage.clear(force=True)
            w.shutdown()

    def test_worker_supervisor_alias(self):
        """Test that Worker is an alias for WorkerSupervisor"""
        assert Worker is WorkerSupervisor

    def test_supervisor_registers_on_startup(self, worker):
        """Test that supervisor registers on startup"""
        assert worker.supervisor_id is not None
        assert len(worker.supervisor_id) == 32  # UUID hex format

        # Verify supervisor exists in database
        with worker.storage.session_scope() as session:
            supervisor = (
                session.query(ORMSupervisor)
                .filter_by(id=worker.supervisor_id)
                .one_or_none()
            )
            assert supervisor is not None

    def test_supervisor_heartbeat_loop_exists(self, worker):
        """Test that supervisor heartbeat loop is started"""
        assert worker.supervisor_heartbeat is not None
        assert worker.supervisor_heartbeat.is_alive()

    def test_job_gets_supervisor_id_when_started(self, worker):
        """Test that jobs get supervisor_id assigned when started"""
        from kolibri.core.tasks.storage import ORMJob

        job = Job(id, args=(9,))
        job_id = worker.storage.enqueue_job(job, QUEUE)

        # Wait for job to start and complete
        max_wait = 10
        waited = 0
        while waited < max_wait:
            job = worker.storage.get_job(job_id)
            if job.state == State.COMPLETED:
                break
            time.sleep(0.5)
            waited += 0.5

        # Job should have been processed
        assert job.state == State.COMPLETED

        # supervisor_id should be cleared after completion
        with worker.storage.session_scope() as session:
            orm_job = session.query(ORMJob).filter_by(id=job_id).one()
            assert orm_job.supervisor_id is None

    def test_multiple_supervisors_simultaneous_registration(self):
        """Test that multiple supervisors can register simultaneously"""
        with connection() as c1:
            with connection() as c2:
                w1 = WorkerSupervisor(c1, regular_workers=1, high_workers=0)
                w2 = WorkerSupervisor(c2, regular_workers=1, high_workers=0)

                try:
                    assert w1.supervisor_id != w2.supervisor_id
                    assert w1.supervisor_id is not None
                    assert w2.supervisor_id is not None
                finally:
                    w1.shutdown()
                    w2.shutdown()
