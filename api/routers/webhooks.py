"""
Webhooks are not used with on-premises Exchange Server.
Change detection is performed via EWS polling (worker/tasks/subscription_tasks.py).

This module is kept as a placeholder.
"""
from fastapi import APIRouter

router = APIRouter(prefix="/api/v1/webhooks", tags=["webhooks"])
