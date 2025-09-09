from celery import Celery
from kombu import Queue

from .config import get_settings


settings = get_settings()


broker_url = settings.redis_url or "redis://localhost:6379/0"
backend_url = broker_url

celery_app = Celery(
    "evm_decoder",
    broker=broker_url,
    backend=backend_url,
    include=[
        "evm_decoder.workers.ingest",
        "evm_decoder.workers.decode",
        "evm_decoder.workers.prices",
        "evm_decoder.workers.analytics",
    ],
)

celery_app.conf.update(
    task_queues=[
        Queue("ingest"),
        Queue("decode"),
        Queue("prices"),
        Queue("analytics"),
    ],
    task_default_queue="ingest",
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
)

