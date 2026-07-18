from aiogram.filters.callback_data import CallbackData


class RegReviewCB(CallbackData, prefix="regrev"):
    action: str  # approve | reject
    request_id: str


class UniversityPickCB(CallbackData, prefix="unipick"):
    university_id: int


class UniPageCB(CallbackData, prefix="unipage"):
    page: int


class UniShowAllCB(CallbackData, prefix="unishowall"):
    pass


class NoopCB(CallbackData, prefix="noop"):
    """Декоративная кнопка (например, счётчик страниц) — нажатие ничего не делает."""


class AdminCallCB(CallbackData, prefix="admcall"):
    """«Возьмусь» под вызовом админов в админ-чате."""


class PermHomeCB(CallbackData, prefix="phome"):
    pass


class PermNewGroupCB(CallbackData, prefix="pgnew"):
    pass


class PermPersonCB(CallbackData, prefix="ppers"):
    pass


class PermCancelCB(CallbackData, prefix="pcancel"):
    pass


class GroupOpenCB(CallbackData, prefix="pgopen"):
    group_id: int


class GroupToggleCB(CallbackData, prefix="pgtgl"):
    group_id: int
    module: str


class GroupMembersCB(CallbackData, prefix="pgmem"):
    group_id: int


class GroupDeleteCB(CallbackData, prefix="pgdel"):
    group_id: int
    confirmed: bool = False


class UserGroupSetCB(CallbackData, prefix="pusetg"):
    tg_id: int
    group_id: int  # 0 = без группы


class UserModToggleCB(CallbackData, prefix="pumod"):
    tg_id: int
    module: str


class UniReqCB(CallbackData, prefix="unireq"):
    action: str  # approve | reject | edit
    request_id: str


class AliasSugCB(CallbackData, prefix="aliassug"):
    action: str  # approve | reject | edit
    suggestion_id: str


class ReviewEditCB(CallbackData, prefix="revedit"):
    action: str  # cancel


class ActReviewCB(CallbackData, prefix="actrev"):
    action: str  # approve | reject
    request_id: str


class VoteReviewCB(CallbackData, prefix="voterev"):
    action: str  # approve | reject
    request_id: str


class ActLifecycleCB(CallbackData, prefix="actlife"):
    action: str  # complete | cancel
    activity_id: str


class SuperUserCB(CallbackData, prefix="suser"):
    action: str  # custom | make_admin | remove_admin | ban
    tg_id: int


class ProfileEditCB(CallbackData, prefix="profedit"):
    field: str  # nick | group | birth | about


class ProfileDeleteCB(CallbackData, prefix="profdel"):
    confirmed: bool = False


class StartCB(CallbackData, prefix="start"):
    action: str  # register | about


class ContentSlotCB(CallbackData, prefix="cslot"):
    slot: str


class ContentActionCB(CallbackData, prefix="cact"):
    action: str  # remove_file | cancel


class ScenGroupCB(CallbackData, prefix="sgrp"):
    g: int  # индекс в scenario_service.GROUPS


class ScenKeyCB(CallbackData, prefix="skey"):
    key: str


class ScenActionCB(CallbackData, prefix="sact"):
    action: str  # reset | rmfile | back
    key: str


class CrudHomeCB(CallbackData, prefix="crhome"):
    pass


class CrudTableCB(CallbackData, prefix="crtab"):
    t: str  # короткий код таблицы из crud_service.TABLES


class CrudPageCB(CallbackData, prefix="crpage"):
    t: str
    page: int


class CrudRowCB(CallbackData, prefix="crrow"):
    t: str
    pk: str
    page: int = 0


class CrudFieldCB(CallbackData, prefix="crfld"):
    t: str
    pk: str
    i: int  # индекс колонки в crud_service.columns()


class CrudDelCB(CallbackData, prefix="crdel"):
    t: str
    pk: str
    confirmed: bool = False


class CrudNewCB(CallbackData, prefix="crnew"):
    t: str


class CrudCancelCB(CallbackData, prefix="crcancel"):
    pass
