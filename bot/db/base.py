from sqlalchemy import MetaData
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from bot.config import settings

naming_convention = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=naming_convention)


# Подключения к базе берутся из пула. По умолчанию их 15 (5 + 10 запасных), и
# на наплыве этого мало: события бот обрабатывает одновременно, а обработчик
# держит подключение всё время своей работы — включая походы в Telegram. При
# разборе заявок бот ходит туда трижды (ссылка, личка человеку, правка
# карточки), и если Telegram попросил подождать, подключение стоит занятым всю
# паузу. Кончился пул — событие ждёт `pool_timeout` и падает с ошибкой, хотя
# ни база, ни Telegram ни при чём.
#
# 30 подключений на 4 ГБ памяти сервер держит спокойно: Postgres по умолчанию
# разрешает 100, а каждое стоит несколько мегабайт.
engine = create_async_engine(
    settings.database_url, pool_size=10, max_overflow=20, pool_timeout=60
)
async_session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)