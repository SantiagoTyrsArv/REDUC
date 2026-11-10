"""Dramatiq worker: runs pipeline executions queued by the API.

dramatiq reduc.worker.main
"""

import uuid

import dramatiq
import structlog
from dramatiq.brokers.redis import RedisBroker
from dramatiq.brokers.stub import StubBroker

from reduc.settings import get_settings

log = structlog.get_logger("reduc.worker")
QUEUE = "pipeline"


def _configure_broker() -> dramatiq.Broker:
    settings = get_settings()
    # The stub broker keeps imports (tests, OpenAPI export) from opening a Redis connection.
    broker: dramatiq.Broker = StubBroker() if settings.worker_broker == "stub" else RedisBroker(url=settings.redis_url)
    dramatiq.set_broker(broker)
    return broker


broker = _configure_broker()


# A run rewrites a whole draft: retrying it blindly would hide the failure recorded on its stage.
@dramatiq.actor(queue_name=QUEUE, max_retries=0, time_limit=6 * 60 * 60 * 1000)
def run_pipeline(run_id: str) -> None:
    from reduc.api.deps import get_storage
    from reduc.core.db.session import SessionLocal
    from reduc.core.pipeline.jobs import execute_run
    from reduc.core.pipeline.wiring import build_deps

    status = execute_run(SessionLocal, uuid.UUID(run_id), build_deps(get_settings(), get_storage()))
    log.info("pipeline_run_finished", run_id=run_id, status=status)


def enqueue_run(run_id: uuid.UUID) -> None:
    """Default way for the API to hand a run to the worker."""
    run_pipeline.send(str(run_id))
