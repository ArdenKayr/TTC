"""обязательная картинка к мероприятию

Revision ID: 0014
Revises: 0013
Create Date: 2026-08-04

В анкете мероприятия появился обязательный шаг: организатор присылает картинку,
она становится обложкой поста в Афише. Пост, собранный вокруг картинки, читают,
а голый текст пролистывают.

Колонка необязательная: у заявок и мероприятий, поданных до этого шага, картинки
нет и придумать её неоткуда — такие карточки по-прежнему уходят текстом.

`afisha_is_caption` нужна вот почему: в подпись под картинкой Telegram пускает
только 1024 символа, а описание бывает длиннее. Тогда карточка уходит отдельным
сообщением под картинкой, и при закрытии мероприятия править надо текст, а не
подпись. У старых мероприятий колонка «ложь» — они и есть обычный текст.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("activity_requests", sa.Column("photo_file_id", sa.Text(), nullable=True))
    op.add_column("activities", sa.Column("photo_file_id", sa.Text(), nullable=True))
    op.add_column(
        "activities",
        sa.Column(
            "afisha_is_caption", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    )


def downgrade() -> None:
    op.drop_column("activities", "afisha_is_caption")
    op.drop_column("activities", "photo_file_id")
    op.drop_column("activity_requests", "photo_file_id")
