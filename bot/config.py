from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

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


settings = Settings()