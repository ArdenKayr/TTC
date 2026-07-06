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
