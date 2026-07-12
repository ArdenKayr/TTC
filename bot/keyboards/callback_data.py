from aiogram.filters.callback_data import CallbackData


class RegReviewCB(CallbackData, prefix="regrev"):
    action: str  # approve | reject
    request_id: str


class UniversityPickCB(CallbackData, prefix="unipick"):
    university_id: int


class UniReqCB(CallbackData, prefix="unireq"):
    action: str  # approve | reject | edit
    request_id: str


class AliasSugCB(CallbackData, prefix="aliassug"):
    action: str  # approve | reject | edit
    suggestion_id: str


class ReviewEditCB(CallbackData, prefix="revedit"):
    action: str  # cancel


class StartCB(CallbackData, prefix="start"):
    action: str  # register | about


class ContentSlotCB(CallbackData, prefix="cslot"):
    slot: str


class ContentActionCB(CallbackData, prefix="cact"):
    action: str  # remove_file | cancel
