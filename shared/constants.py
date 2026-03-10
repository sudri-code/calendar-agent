from enum import StrEnum


class EventRole(StrEnum):
    PRIMARY = "primary"
    MIRROR = "mirror"


class SyncGroupState(StrEnum):
    ACTIVE = "active"
    DEGRADED = "degraded"
    DELETED = "deleted"


class AccountStatus(StrEnum):
    ACTIVE = "active"
    EXPIRED = "expired"
    REVOKED = "revoked"
    ERROR = "error"


class TaskType(StrEnum):
    CREATE_EVENT = "create_event"
    RESCHEDULE_EVENT = "reschedule_event"
    DELETE_EVENT = "delete_event"
    FIND_SLOT = "find_slot"


class RecurrenceEditMode(StrEnum):
    SINGLE = "single"
    THIS_AND_FOLLOWING = "this_and_following"
    ALL = "all"


class RecurrenceDeleteMode(StrEnum):
    SINGLE = "single"
    THIS_AND_FOLLOWING = "this_and_following"
    ALL = "all"
