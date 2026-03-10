"""
On-premises Exchange does not support Graph API webhooks.
Change detection is performed via EWS polling (subscription_tasks.py).

This module is kept as a placeholder for compatibility.
"""
import structlog
from worker.celery_config import app

logger = structlog.get_logger()


@app.task(name="worker.tasks.webhook_tasks.process_graph_notification_task")
def process_graph_notification_task(notification: dict):
    """No-op: Graph webhooks are not used with on-premises Exchange."""
    logger.warning("process_graph_notification_task called — not applicable for on-premises EWS")
