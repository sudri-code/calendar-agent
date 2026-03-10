from typing import Optional


class AppError(Exception):
    def __init__(self, message: str, details: Optional[dict] = None):
        self.message = message
        self.details = details or {}
        super().__init__(message)


class AuthExpiredError(AppError):
    """OAuth token expired or revoked"""
    pass


class InsufficientPermissionsError(AppError):
    """Insufficient Graph API permissions"""
    pass


class CalendarConflictError(AppError):
    """Slot conflict in calendar"""
    def __init__(self, message: str, conflicting_events: Optional[list] = None):
        super().__init__(message)
        self.conflicting_events = conflicting_events or []


class AttendeeBusyError(AppError):
    """Attendee is busy at the requested time"""
    def __init__(self, message: str, busy_attendees: Optional[list[str]] = None):
        super().__init__(message)
        self.busy_attendees = busy_attendees or []


class ContactNotFoundError(AppError):
    """Contact not found"""
    pass


class AmbiguousContactError(AppError):
    """Multiple contacts match the query"""
    def __init__(self, message: str, candidates: Optional[list] = None):
        super().__init__(message)
        self.candidates = candidates or []


class MirrorSyncError(AppError):
    """Failed to sync mirror events"""
    def __init__(self, message: str, failed_calendars: Optional[list[str]] = None):
        super().__init__(message)
        self.failed_calendars = failed_calendars or []


class WebhookValidationError(AppError):
    """Webhook validation failed"""
    pass


class SubscriptionExpiredError(AppError):
    """Graph subscription expired"""
    pass


class LLMParsingError(AppError):
    """LLM failed to parse the request"""
    pass


class ExternalRateLimitError(AppError):
    """External API rate limit hit"""
    def __init__(self, message: str, retry_after: Optional[int] = None):
        super().__init__(message)
        self.retry_after = retry_after


class EventNotFoundError(AppError):
    """Event not found"""
    pass


class SyncGroupNotFoundError(AppError):
    """Sync group not found"""
    pass
