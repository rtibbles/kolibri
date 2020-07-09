import tempfile
import time

import pytest

from kolibri.core.tasks.job import Job
from kolibri.core.tasks.job import State
from kolibri.core.tasks.main import connection
from kolibri.core.tasks.queue import Queue
from kolibri.core.tasks.utils import get_current_job
from kolibri.core.tasks.utils import import_stringified_func
from kolibri.core.tasks.utils import stringify_func
from kolibri.core.tasks.worker import Worker


@pytest.fixture
def inmem_queue():
    e = Worker(queues="pytest", connection=connection)
    c = Queue(queue="pytest", connection=connection)
    yield c
    e.storage.clear()
    e.shutdown()


@pytest.fixture
def simplejob():
    return Job("builtins.id", 1)


@pytest.fixture
def enqueued_job(inmem_queue, simplejob):
    job_id = inmem_queue.enqueue(simplejob)
    return inmem_queue.storage.get_job(job_id)


def cancelable_job():
    """
    Test function for checking if a job is cancelable. Meant to be used in a job cancel
    test case.

    It then calls the check_for_cancel, followed by a time.sleep function, 3 times.

    :param check_for_cancel: A function that the BBQ framework passes in when a job is set to be cancellable.
    Calling this function makes the thread check if a cancellation has been requested, and then exits early if true.
    :return: None
    """
    job = get_current_job()
    for _ in range(10):
        time.sleep(0.5)
        if job.check_for_cancel():
            return


def set_flag(filepath, val):
    with open(filepath, "w") as f:
        f.write(val)


def make_job_updates():
    job = get_current_job()
    for j in range(3):
        job.update_progress(j, 2)


def failing_func():
    raise Exception("Test function failing_func has failed as it's supposed to.")


def update_progress_cancelable_job():
    """
    Test function for checking if a job is cancelable when it updates progress.
    Meant to be used in a job cancel with progress update test case.

    It then calls the check_for_cancel, followed by a time.sleep function, 10 times.

    :param update_progress: A function that is called to update progress
    :param check_for_cancel: A function that the iceqube framework passes in when a job is set to be cancellable.
    Calling this function makes the thread check if a cancellation has been requested, and then exits early if true.
    :return: None
    """
    job = get_current_job()
    for i in range(10):
        time.sleep(0.5)
        job.update_progress(i, 9)
        if job.check_for_cancel():
            return


class TestQueue(object):
    def test_enqueues_a_function(self, inmem_queue):
        job_id = inmem_queue.enqueue(id, 1)

        # is the job recorded in the chosen backend?
        assert inmem_queue.fetch_job(job_id).job_id == job_id

    def test_enqueue_preserves_extra_metadata(self, inmem_queue):
        metadata = {"saved": True}
        job_id = inmem_queue.enqueue(id, 1, extra_metadata=metadata)

        # Do we get back the metadata we save?
        assert inmem_queue.fetch_job(job_id).extra_metadata == metadata

    def test_enqueue_runs_function(self, inmem_queue):
        _, filepath = tempfile.mkstemp()
        job_id = inmem_queue.enqueue(set_flag, filepath, "flag")

        interval = 0.1
        time_spent = 0
        job = inmem_queue.fetch_job(job_id)
        while job.state != State.COMPLETED:
            time.sleep(interval)
            time_spent += interval
            job = inmem_queue.fetch_job(job_id)
            assert time_spent < 5
        with open(filepath, "r") as f:
            assert f.read() == "flag"

    def test_enqueued_job_can_receive_job_updates(self, inmem_queue):
        job_id = inmem_queue.enqueue(make_job_updates, track_progress=True)

        # sleep for half a second to make us switch to another thread
        time.sleep(0.5)

        for i in range(2):
            job = inmem_queue.fetch_job(job_id)
            assert job.state in [State.QUEUED, State.RUNNING, State.COMPLETED]

    def test_can_get_notified_of_job_failure(self, inmem_queue):
        job_id = inmem_queue.enqueue(failing_func)

        interval = 0.1
        time_spent = 0
        job = inmem_queue.fetch_job(job_id)
        while job.state != State.FAILED:
            time.sleep(interval)
            time_spent += interval
            job = inmem_queue.fetch_job(job_id)
            assert time_spent < 5
        assert job.state == State.FAILED

    def test_stringify_func_is_importable(self):
        funcstring = stringify_func(set_flag)
        func = import_stringified_func(funcstring)

        assert set_flag == func

    def test_can_get_job_details(self, inmem_queue, enqueued_job):
        assert inmem_queue.fetch_job(enqueued_job.job_id).job_id == enqueued_job.job_id

    def test_can_cancel_a_job(self, inmem_queue):
        job_id = inmem_queue.enqueue(cancelable_job, cancellable=True)

        interval = 0.1
        job = inmem_queue.fetch_job(job_id)
        while job.state != State.RUNNING:
            time.sleep(interval)
            job = inmem_queue.fetch_job(job_id)
        # Job should be running after this point

        # Now let's cancel...
        inmem_queue.cancel(job_id)
        # And check the job state to make sure it's marked as cancelling
        job = inmem_queue.fetch_job(job_id)
        assert job.state == State.CANCELING
        while job.state != State.CANCELED:
            time.sleep(interval)
            job = inmem_queue.fetch_job(job_id)
        # and hopefully it's canceled by this point
        assert job.state == State.CANCELED

    def test_can_cancel_a_job_that_updates_progress(self, inmem_queue):
        job_id = inmem_queue.enqueue(
            update_progress_cancelable_job, cancellable=True, track_progress=True
        )

        interval = 0.1
        job = inmem_queue.fetch_job(job_id)
        while job.state != State.RUNNING:
            time.sleep(interval)
            job = inmem_queue.fetch_job(job_id)
        # Job should be running after this point

        # Now let's cancel...
        inmem_queue.cancel(job_id)
        # And check the job state to make sure it's marked as cancelling
        job = inmem_queue.fetch_job(job_id)
        assert job.state == State.CANCELING
        while job.state != State.CANCELED:
            time.sleep(interval)
            job = inmem_queue.fetch_job(job_id)
        # and hopefully it's canceled by this point
        assert job.state == State.CANCELED
