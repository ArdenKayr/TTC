import sqlalchemy as sa

from bot.enums import (
    ActivityStatus,
    ActorType,
    AfishaStatus,
    BillingType,
    PaymentStatus,
    RequestStatus,
    TargetType,
    UserRole,
    VotePollStatus,
)


def _values(enum_cls):
    return [member.value for member in enum_cls]


user_role_enum = sa.Enum(UserRole, name="user_role", values_callable=_values)
request_status_enum = sa.Enum(RequestStatus, name="request_status", values_callable=_values)
activity_status_enum = sa.Enum(ActivityStatus, name="activity_status", values_callable=_values)
vote_poll_status_enum = sa.Enum(VotePollStatus, name="vote_poll_status", values_callable=_values)
afisha_status_enum = sa.Enum(AfishaStatus, name="afisha_status", values_callable=_values)
billing_type_enum = sa.Enum(BillingType, name="billing_type", values_callable=_values)
target_type_enum = sa.Enum(TargetType, name="target_type", values_callable=_values)
payment_status_enum = sa.Enum(PaymentStatus, name="payment_status", values_callable=_values)
actor_type_enum = sa.Enum(ActorType, name="actor_type", values_callable=_values)
