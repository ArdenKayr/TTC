from enum import Enum


class UserRole(str, Enum):
    USER = "user"
    ORGANIZER = "organizer"
    ADMIN = "admin"
    CUSTOM = "custom"
    BANNED = "banned"


class RequestStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class ActivityStatus(str, Enum):
    PREPARING = "preparing"
    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class VotePollStatus(str, Enum):
    NOT_REQUESTED = "not_requested"
    PENDING_ADMIN_APPROVAL = "pending_admin_approval"
    POSTED = "posted"
    CLOSED = "closed"


class AfishaStatus(str, Enum):
    NONE = "none"
    REQUESTED = "requested"
    PUBLISHED = "published"


class BillingType(str, Enum):
    ONE_TIME = "one_time"
    MONTHLY = "monthly"


class TargetType(str, Enum):
    ALL = "all"
    SPECIFIC = "specific"


class PaymentStatus(str, Enum):
    PENDING = "pending"
    PAID = "paid"
    FAILED = "failed"
    CANCELLED = "cancelled"


class PermissionModule(str, Enum):
    """Независимые модули админских прав (подключаются группе или человеку)."""

    REGISTRATION = "registration"  # заявки на регистрацию
    UNIVERSITIES = "universities"  # заявки на вузы и варианты поиска
    CONTENT = "content"  # редактор текстов и файлов (/content)
    MODERATION = "moderation"  # бан/разбан


class ActorType(str, Enum):
    ADMIN = "admin"
    SYSTEM = "system"


class AuditAction(str, Enum):
    REGISTRATION_APPROVED = "registration_approved"
    REGISTRATION_REJECTED = "registration_rejected"
    USER_BANNED = "user_banned"
    USER_UNBANNED = "user_unbanned"
    ROLE_CHANGED = "role_changed"
    UNIVERSITY_ADDED = "university_added"
    UNIVERSITY_REQUEST_APPROVED = "university_request_approved"
    UNIVERSITY_REQUEST_REJECTED = "university_request_rejected"
    UNIVERSITY_REQUEST_EDITED = "university_request_edited"
    ALIAS_APPROVED = "alias_approved"
    ALIAS_REJECTED = "alias_rejected"
    ALIAS_EDITED = "alias_edited"
    CONTENT_UPDATED = "content_updated"
    PERM_GROUP_CREATED = "perm_group_created"
    PERM_GROUP_UPDATED = "perm_group_updated"
    PERM_GROUP_DELETED = "perm_group_deleted"
    USER_PERMISSIONS_CHANGED = "user_permissions_changed"
