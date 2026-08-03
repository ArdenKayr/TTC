from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import Report, ReportMessage
from bot.enums import CLOSED_REPORT_STATUSES


async def create(session: AsyncSession, author_tg_id: int, author_name: str, text: str) -> Report:
    report = Report(author_tg_id=author_tg_id, author_name=author_name, text=text)
    session.add(report)
    # flush, а не commit: номер репорта нужен прямо сейчас — он идёт в карточку
    # админам и в ответ автору, а решение о сохранении принимает вызывающий код.
    await session.flush()
    return report


async def get(session: AsyncSession, report_id: int) -> Report | None:
    return await session.get(Report, report_id)


async def add_message(
    session: AsyncSession,
    report: Report,
    *,
    from_admin: bool,
    author_tg_id: int | None,
    author_name: str,
    text: str,
) -> ReportMessage:
    message = ReportMessage(
        report_id=report.report_id,
        from_admin=from_admin,
        author_tg_id=author_tg_id,
        author_name=author_name,
        text=text,
    )
    session.add(message)
    await session.flush()
    return message


async def messages(session: AsyncSession, report_id: int) -> list[ReportMessage]:
    result = await session.execute(
        select(ReportMessage)
        .where(ReportMessage.report_id == report_id)
        .order_by(ReportMessage.created_at, ReportMessage.message_id)
    )
    return list(result.scalars())


async def message_count(session: AsyncSession, report_id: int) -> int:
    result = await session.execute(
        select(ReportMessage.message_id).where(ReportMessage.report_id == report_id)
    )
    return len(result.scalars().all())


async def list_open(session: AsyncSession, limit: int = 20) -> list[Report]:
    """Незакрытые репорты, самые новые сверху — это и есть очередь работы."""
    result = await session.execute(
        select(Report)
        .where(Report.status.notin_(list(CLOSED_REPORT_STATUSES)))
        .order_by(Report.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars())


async def list_by_author(session: AsyncSession, author_tg_id: int, limit: int = 10) -> list[Report]:
    result = await session.execute(
        select(Report)
        .where(Report.author_tg_id == author_tg_id)
        .order_by(Report.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars())


async def count_open_by_author(session: AsyncSession, author_tg_id: int) -> int:
    """Сколько незакрытых репортов у человека — защита от потока одинаковых жалоб."""
    result = await session.execute(
        select(Report.report_id).where(
            Report.author_tg_id == author_tg_id,
            Report.status.notin_(list(CLOSED_REPORT_STATUSES)),
        )
    )
    return len(result.scalars().all())
