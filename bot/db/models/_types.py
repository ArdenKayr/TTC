import sqlalchemy as sa

from bot.enums import ActivityStatus, ActorType, RequestStatus, UserRole


def _values(enum_cls):
    return [member.value for member in enum_cls]


user_role_enum = sa.Enum(UserRole, name="user_role", values_callable=_values)
request_status_enum = sa.Enum(RequestStatus, name="request_status", values_callable=_values)
actor_type_enum = sa.Enum(ActorType, name="actor_type", values_callable=_values)
activity_status_enum = sa.Enum(ActivityStatus, name="activity_status", values_callable=_values)
