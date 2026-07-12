from aiogram.filters.callback_data import CallbackData


class RegReviewCB(CallbackData, prefix="regrev"):
    action: str  # approve | reject
    request_id: str


class UniversityPickCB(CallbackData, prefix="unipick"):
    university_id: int


class UniversityNewCB(CallbackData, prefix="uninew"):
    pass


class RegFormCB(CallbackData, prefix="regform"):
    action: str  # submit | restart | cancel


class StartCB(CallbackData, prefix="start"):
    action: str  # register | about


class ContentSlotCB(CallbackData, prefix="cslot"):
    slot: str


class ContentActionCB(CallbackData, prefix="cact"):
    action: str  # remove_file | cancel
