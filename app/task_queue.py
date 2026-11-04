"""Queue document ingestion jobs with Redis/RQ and a local thread fallback."""
import logging
import threading

from app.config import REDIS_ENABLED, REDIS_TIMEOUT, REDIS_URL, WORKER_QUEUE

log = logging.getLogger("ashore.queue")


def enqueue_document_job(job_id: str) -> str:
    if REDIS_ENABLED:
        try:
            from redis import Redis
            from rq import Queue

            connection = Redis.from_url(
                REDIS_URL, socket_connect_timeout=REDIS_TIMEOUT,
                socket_timeout=REDIS_TIMEOUT,
            )
            connection.ping()
            Queue(WORKER_QUEUE, connection=connection).enqueue(
                "app.worker.process_document_job",
                job_id,
                job_timeout=1800,
                result_ttl=86400,
                failure_ttl=86400,
            )
            return "rq"
        except Exception as error:
            log.warning("RQ unavailable, using local thread: %s", error)

    def run():
        from app.worker import process_document_job
        try:
            process_document_job(job_id)
        except Exception:
            log.exception("local document job failed: %s", job_id)

    threading.Thread(target=run, name=f"ingest-{job_id[:8]}", daemon=True).start()
    return "thread"
