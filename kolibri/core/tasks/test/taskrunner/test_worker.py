import time

import pytest

from kolibri.core.tasks.job import Job
from kolibri.core.tasks.job import State
from kolibri.core.tasks.main import connection
from kolibri.core.tasks.worker import Worker


QUEUE = "pytest"


@pytest.fixture
def worker():
    b = Worker(QUEUE, connection)
    yield b
    b.storage.clear()
    b.shutdown()


class TestWorker:
    def test_enqueue_job_runs_job(self, worker):
        job = Job(id, 9)
        worker.storage.enqueue_job(job, QUEUE)

        while job.state == State.QUEUED:
            job = worker.storage.get_job(job.job_id)
            time.sleep(0.5)
        try:
            # Get the future, or pass if it has already been cleaned up.
            future = worker.future_job_mapping[job.job_id]

            future.result()
        except KeyError:
            pass

        assert job.state == State.COMPLETED
