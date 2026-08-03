from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Чаты боевого сообщества. Не секрет: они и так лежат в .env.example и в
# документации. Нужны здесь ради одной проверки — самой дорогой ошибки
# тестового контура: тестовый бот тоже админ с правом удалять сообщения, и
# запущенный по недосмотру в боевой группе он начнёт наводить там порядок.
PRODUCTION_CHATS = frozenset({"-1004492113804", "@the_true_course_spb"})


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # «prod» — боевой сервер, «test» — тестовый контур (docs/TEST_ENV.md).
    env_name: str = "prod"

    bot_token: str
    admin_chat_id: int
    admin_topic_applications_id: int | None = None
    admin_topic_reports_id: int | None = None

    # Numeric -100... id or public @username (resolved to the numeric id at startup).
    group_chat_id: int | str | None = None
    topic_announcements_id: int | None = None
    topic_afisha_id: int | None = None
    topic_voting_id: int | None = None

    @field_validator(
        "group_chat_id",
        "admin_topic_applications_id",
        "admin_topic_reports_id",
        "topic_announcements_id",
        "topic_afisha_id",
        "topic_voting_id",
        mode="before",
    )
    @classmethod
    def _empty_str_as_none(cls, value):
        return None if value == "" else value

    @field_validator("group_chat_id", mode="after")
    @classmethod
    def _numeric_str_to_int(cls, value):
        if isinstance(value, str) and value.lstrip("-").isdigit():
            return int(value)
        return value

    database_url: str
    redis_url: str

    @property
    def is_test(self) -> bool:
        return self.env_name.strip().lower() == "test"

    @model_validator(mode="after")
    def _test_bot_stays_away_from_production(self):
        """Тестовый бот не запускается, если видит боевые чаты.

        Проверка стоит на старте, а не в деплое, потому что перепутать `.env`
        можно любым способом — скопировать боевой файл в тестовую папку,
        поправить не ту строку. Здесь ошибка ловится один раз и навсегда:
        контейнер просто не поднимется, вместо того чтобы молча начать удалять
        сообщения в живой группе.
        """
        if not self.is_test:
            return self
        used = {
            name: value
            for name, value in (
                ("ADMIN_CHAT_ID", self.admin_chat_id),
                ("GROUP_CHAT_ID", self.group_chat_id),
            )
            if value is not None and str(value).strip().lower() in PRODUCTION_CHATS
        }
        if used:
            where = ", ".join(f"{name}={value}" for name, value in used.items())
            raise ValueError(
                f"ENV_NAME=test, но в настройках боевые чаты сообщества: {where}. "
                "Тестовый бот — админ с правом удалять сообщения, в боевой группе "
                "ему делать нечего. Заведите для теста отдельную группу и отдельный "
                "чат админов (docs/TEST_ENV.md)."
            )
        return self


settings = Settings()