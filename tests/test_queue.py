"""FR3 — uploading enqueues an ingestion job and returns immediately."""

import pytest

from app import jobs, vectorstore
from app.ingestion import ingest_documents


class FakeJob:
    def __init__(self, func, args, kwargs):
        self.id = "job-1"
        self.func = func
        self.args = args
        self.kwargs = kwargs
        self._status = "queued"

    def get_status(self, refresh=True):
        return self._status


class FakeQueue:
    """Stands in for RQ: records the enqueue instead of running the work."""

    def __init__(self):
        self.calls = []

    def enqueue(self, func, *args, **kwargs):
        job = FakeJob(func, args, kwargs)
        self.calls.append(job)
        return job


@pytest.fixture
def fake_queue(monkeypatch):
    queue = FakeQueue()
    monkeypatch.setattr(jobs, "get_queue", lambda: queue)
    return queue


def test_upload_enqueues_job(fake_queue, persist_dir):
    """The upload path hands work to the queue rather than doing it inline:
    the job is queued, nothing has been embedded yet, and the UI has a job
    id to show a processing state against."""
    documents = [("notes.txt", b"One sentence. Two sentence.")]
    job = jobs.enqueue_ingestion("set-alpha", documents)

    assert len(fake_queue.calls) == 1
    queued = fake_queue.calls[0]
    assert queued.func is ingest_documents
    assert queued.args == ("set-alpha", documents)
    assert queued.kwargs["job_timeout"] > 0

    # Returned immediately: the chunk + embed work has not run.
    assert vectorstore.list_collections(persist_dir) == []
    assert job.id
    assert job.get_status() == "queued"


def test_job_state_reports_unknown_for_missing_job(fake_queue, monkeypatch):
    monkeypatch.setattr(jobs, "fetch_job", lambda job_id: None)
    assert jobs.job_state("nope")["status"] == "unknown"
