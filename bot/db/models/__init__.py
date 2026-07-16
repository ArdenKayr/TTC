from bot.db.models.audit import AuditLog
from bot.db.models.content import ContentBlock
from bot.db.models.permission import PermissionGroup
from bot.db.models.registration import RegistrationRequest
from bot.db.models.university import (
    AliasSuggestion,
    University,
    UniversityAlias,
    UniversityRequest,
)
from bot.db.models.user import User

__all__ = [
    "AliasSuggestion",
    "AuditLog",
    "ContentBlock",
    "PermissionGroup",
    "RegistrationRequest",
    "University",
    "UniversityAlias",
    "UniversityRequest",
    "User",
]
