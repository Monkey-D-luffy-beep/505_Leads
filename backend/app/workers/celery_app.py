"""
Celery application configuration.
Uses Upstash Redis as broker and result backend.
"""

from celery import Celery
from app.config import settings

celery_app = Celery(
    "outbound_tool",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=[
        "app.workers.scrape_tasks",
        "app.workers.email_tasks",
        "app.workers.signal_tasks",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    # ── Rate limiting for scrape tasks (max 3 concurrent) ──────────────
    task_routes={
        "scrape_tasks.*": {"queue": "scrape"},
        "email_tasks.*": {"queue": "email"},
        "signal_tasks.*": {"queue": "default"},
    },
    worker_concurrency=4,
    task_annotations={
        "scrape_tasks.run_scrape_job": {"rate_limit": "3/m"},
    },
    # ── Celery Beat periodic schedule ──────────────────────────────────
    beat_schedule={
        "run-send-loop": {
            "task": "app.workers.email_tasks.run_send_loop",
            "schedule": 900.0,  # every 15 minutes
        },
        "poll-replies": {
            "task": "app.workers.email_tasks.poll_replies_task",
            "schedule": 600.0,  # every 10 minutes
        },
    },
)
