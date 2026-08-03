# TTC — Telegram-экосистема студенческого сообщества

Бот + супергруппа с топиками + PostgreSQL. Регистрация с одобрением админом, роли (user/organizer/admin/custom/banned), жизненный цикл активностей, сборы взносов.

## Стек

Python 3.12 · Aiogram 3 · PostgreSQL 16 (+pg_trgm) · SQLAlchemy 2 async + Alembic · Redis (FSM) · APScheduler · Docker Compose

## Структура Telegram-стороны

**Супергруппа сообщества** (форум, задаётся в `GROUP_CHAT_ID` — численный id или @username):

| Топик | Назначение | env-переменная (thread id) |
|---|---|---|
| General | Системный топик, никто не пишет | — |
| Флуд | Свободное общение | — |
| Объявления | Read-only, посты администрации | `TOPIC_ANNOUNCEMENTS_ID` |
| Афиша | Read-only, актуальные активности | `TOPIC_AFISHA_ID` |
| Голосование | Опросы по идеям активностей | `TOPIC_VOTING_ID` |

**Чат админов** — отдельная приватная форум-супергруппа (`ADMIN_CHAT_ID`) с топиками:

| Топик | Назначение | env-переменная (thread id) |
|---|---|---|
| Заявки | Карточки регистраций/активностей/сборов с кнопками | `ADMIN_TOPIC_APPLICATIONS_ID` |
| Репорты | Репорты от пользователей (кнопка «🐞 Репорт») и вызовы `@admin` из группы | `ADMIN_TOPIC_REPORTS_ID` |

Настройка бота: создать у [@BotFather](https://t.me/BotFather), **отключить Group Privacy** (Bot Settings → Group Privacy → Disable), добавить админом в супергруппу (права: приглашение ссылками, удаление сообщений, бан) и участником в чат админов. `message_thread_id` топика — число из его ссылки: `t.me/<группа>/<thread_id>/<message_id>`.

## Запуск

```bash
cp .env.example .env   # заполнить BOT_TOKEN, ADMIN_CHAT_ID, GROUP_CHAT_ID, пароль БД
docker compose up --build -d
```

Миграции применяются автоматически при старте контейнера бота.

Назначить первого админа (дальше админы назначают друг друга через бота):

```bash
docker compose run --rm bot python -m scripts.bootstrap_admin --tg-id 123456789 --name "Имя Фамилия"
```

Загрузить справочник вузов из CSV (колонки: `name;city;aliases`, aliases через `|`; можно позже, таблица может стартовать пустой):

```bash
docker compose run --rm bot python -m scripts.seed_universities data/universities.csv
```

## Разработка

```bash
python -m venv .venv
.venv/Scripts/pip install -r requirements-dev.txt
.venv/Scripts/python -m pytest
```

## Структура

- `bot/routers/` — хендлеры по доменам (registration, admin/, group/)
- `bot/services/` — бизнес-логика (тайм-аут регистрации, роли, инвайт-ссылки, аудит)
- `bot/db/models/`, `bot/db/repositories/` — схема и запросы
- `migrations/` — Alembic
- `scripts/` — bootstrap первого админа, сид вузов, выкатка на сервер (`deploy.py`), сборка статей для Telegraph (`build_user_guide.py`, `build_release.py`)

## Обновления

Проект в бете, обновления выпускаются по регламенту — [docs/RELEASE_RULES.md](docs/RELEASE_RULES.md). Коротко: у обновления есть номер и название (`docs/releases/NN-название.md`), из него собираются две статьи для Telegraph (участникам и админам), документация и карта сценариев правятся тем же изменением, перед выкаткой прогоняются все проверки, после — журнал ошибок под присмотром.

```bash
python -m scripts.build_release   # страницы обновления (обновление.bat)
python -m scripts.deploy          # выкатить на сервер  (бой-выкатить.bat)
```
