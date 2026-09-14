"""Redis-backed ingestion queue (FR3).

Uploads enqueue a job and return immediately; an RQ worker does the
chunk + embed work out of process.
"""

from __future__ import annotations

from redis import Redis
from rq import Queue
from rq.job import Job

from app import config
from app.ingestion import ingest_documents

_queue = None


def get_queue() -> Queue:
    global _queue
    if _queue is None:
        _queue = Queue(
            config.QUEUE_NAME, connection=Redis.from_url(config.REDIS_URL)
        )
    return _queue


def enqueue_ingestion(collection_name: str, documents: list[tuple[str, bytes]]):
    """Hand the ingestion off to the worker and return the queued job."""
    return get_queue().enqueue(
        ingest_documents, collection_name, documents, job_timeout=900
    )


def fetch_job(job_id: str) -> Job | None:
    try:
        return Job.fetch(job_id, connection=get_queue().connection)
    except Exception:
        return None


def job_state(job_id: str) -> dict:
    """UI-friendly status: queued / started / finished / failed."""
    job = fetch_job(job_id)
    if job is None:
        return {"status": "unknown", "result": None, "error": None}
    return {
        "status": job.get_status(refresh=True) or "unknown",
        "result": job.result,
        "error": job.exc_info,
    }
