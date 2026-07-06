# TTC — Telegram-экосистема студенческого сообщества

Бот + супергруппа с топиками + PostgreSQL. Регистрация с одобрением админом, роли (user/organizer/admin/custom/banned), жизненный цикл активностей, сборы взносов.

## Стек

Python 3.12 · Aiogram 3 · PostgreSQL 16 (+pg_trgm) · SQLAlchemy 2 async + Alembic · Redis (FSM) · APScheduler · Docker Compose

## Подготовка Telegram-стороны

1. Создать бота у [@BotFather](https://t.me/BotFather), получить `BOT_TOKEN`. В настройках бота **отключить Group Privacy** (Bot Settings → Group Privacy → Disable), иначе бот не увидит сообщения в топиках.
2. Создать супергруппу сообщества, включить Topics (форум). Создать топики: General, Флуд, Объявления, Актуальная афиша, Голосования.
3. Создать **отдельный приватный чат админов** (не топик — топики видны всем участникам группы). Туда бот шлёт карточки заявок.
4. Добавить бота админом в супергруппу (с правами: приглашение ссылками, удаление сообщений, бан) и участником в чат админов.
5. Узнать `chat_id` группы и админ-чата (например через @getidsbot) и `message_thread_id` топиков Объявления/Афиша/Голосования.

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
- `scripts/` — bootstrap первого админа, сид вузов
