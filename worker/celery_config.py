import os
from celery import Celery
from celery.schedules import crontab

redis_url = os.environ.get("REDIS_URL", "redis://redis:6379/0")

app = Celery(
    "calendar_worker",
    broker=redis_url,
    backend=redis_url,
    include=[
        "worker.tasks.sync_tasks",
        "worker.tasks.webhook_tasks",
        "worker.tasks.subscription_tasks",
        "worker.tasks.reconciliation_tasks",
    ],
)

app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    beat_schedule={
        "renew-expiring-subscriptions": {
            "task": "worker.tasks.subscription_tasks.renew_expiring_subscriptions_task",
            "schedule": crontab(minute=0, hour="*/6"),
        },
        "reconcile-sync-groups": {
            "task": "worker.tasks.reconciliation_tasks.reconcile_sync_groups_task",
            "schedule": crontab(minute=0, hour=3),
        },
        "sync-all-contacts": {
            "task": "worker.tasks.sync_tasks.sync_all_contacts_task",
            "schedule": crontab(minute=0, hour="*/12"),
        },
    },
)
