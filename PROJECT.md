# TTC — Telegram-экосистема студенческого сообщества

## Что это

Платформа студенческого сообщества «The True Course» (СПб) на базе Telegram: супергруппа-форум + бот **@ttc_adm_bot** + PostgreSQL. Бот ведёт регистрацию с одобрением админами, роли (user/organizer/admin/custom/banned), жизненный цикл активностей (мероприятий) с авто-повышением/понижением роли организатора и финансовый контур (разовые взносы и ежемесячные подписки).

Полный утверждённый план проекта: `C:\Users\Черешня\.claude\plans\jaunty-roaming-babbage.md` (контекст решений). Этот файл — единственный источник правды о текущем состоянии кода.

## Технологии и зависимости

- **Python 3.12**, **Aiogram 3.15+** (long polling, HTML parse mode), **SQLAlchemy 2 async + asyncpg**, **Alembic**, **PostgreSQL 16** (+расширение `pg_trgm` для fuzzy-поиска вузов), **Redis 7** (хранилище FSM), **pydantic-settings**, APScheduler (в requirements, будет задействован в Фазах 2–3), pytest (dev).
- **Docker Compose**: сервисы `postgres` (healthcheck `pg_isready`), `redis` (healthcheck `ping`), `bot` (стартует после healthy; `restart: unless-stopped`). Том `postgres_data`. Миграции применяются автоматически: CMD Dockerfile = `alembic upgrade head && python -m bot.main`.

### Переменные окружения (.env; .env.example — шаблон)
| Переменная | Значение/назначение |
|---|---|
| `BOT_TOKEN` | Токен @ttc_adm_bot (реальный, в .env, git-ignored) |
| `ADMIN_CHAT_ID` | `-1003934977632` — приватная форум-супергруппа админов |
| `ADMIN_TOPIC_APPLICATIONS_ID` | `269` — топик «Заявки» (карточки регистраций) |
| `ADMIN_TOPIC_REPORTS_ID` | `271` — топик «Репорты» (/report и @admin-вызовы) |
| `GROUP_CHAT_ID` | `@The_True_Course_SPB` — группа сообщества; @username резолвится в числовой id при старте (реальный id: `-1004334303503`) |
| `TOPIC_ANNOUNCEMENTS_ID` | `2` — топик «Объявления» (read-only для не-админов) |
| `TOPIC_AFISHA_ID` | `6` — топик «Афиша» (read-only) |
| `TOPIC_VOTING_ID` | `8` — топик «Голосование» (для опросов, Фаза 2) |
| `POSTGRES_USER/PASSWORD/DB` | Учётка БД (пароль `change_me` — сменить перед боевым деплоем!) |
| `DATABASE_URL` | `postgresql+asyncpg://...@postgres:5432/ttc` (должен совпадать с учёткой выше) |
| `REDIS_URL` | `redis://redis:6379/0` |

Топики группы «General» (системный, никто не пишет) и «Флуд» (свободное общение) боту не сконфигурированы — он их не трогает.

## Как запустить и проверить

```bash
docker compose up --build -d          # поднять всё (миграции применятся сами)
docker compose logs -f bot            # логи: миграции, резолв группы, Start polling
docker compose run --rm bot python -m scripts.bootstrap_admin --tg-id <id> --name "Имя"   # первый админ
docker compose run --rm bot python -m scripts.seed_universities data/universities.csv     # сид вузов (CSV: name;city;aliases, алиасы через |)
.venv/Scripts/python -m pytest        # юнит-тесты (локальный venv)
docker compose exec postgres psql -U ttc -d ttc   # прямой доступ к БД
```

Права бота в Telegram: в группе — админ (инвайт-ссылки, удаление сообщений, бан, управление топиками); в админ-чате — участник/админ; Group Privacy у BotFather — отключён.

## Архитектура

### Схема данных (11 таблиц, миграция `0001`)

- **universities** — справочник вузов: `university_id` PK, `canonical_name` uniq, `city`, `is_verified` (false = добавлен пользователем, ждёт проверки админом), GIN trgm-индекс по имени.
- **university_aliases** — сокращения («ВШЭ»): `alias_id` PK, `university_id` FK (CASCADE), `alias_text`, GIN trgm-индекс.
- **users** — только одобренные участники (создаётся при approve, не при /start): `tg_id` PK (bigint, Telegram id), `username`, `display_name`, `university_id` FK null, `university_group`, `birth_date`, `current_role` enum(user/organizer/admin/custom/banned), `role_before_ban` (для восстановления при разбане), `custom_permissions` JSONB, `banned_at/banned_reason`, `registration_date`, `updated_at`.
- **registration_requests** — каждая попытка = новая строка: `request_id` UUID PK, `tg_id` (НЕ FK — юзера ещё нет), `full_name`, `university_id` FK, `university_group`, `birth_date`, `raw_input_snapshot` JSONB (username, введённый текст), `status` enum(pending/approved/rejected), `attempt_number`, `next_allowed_attempt` (тайм-аут), `processed_by/processed_at/admin_comment`.
- **activity_proposals** (Фаза 2) — идея до одобрения: UUID PK, `proposed_by` FK, title/description/plan_url/chat_url/comment, `wants_pre_vote`, `vote_poll_message_id`, `vote_poll_status` enum, `status` enum(pending/approved/rejected), `resulting_activity_id` FK→activities (циркулярный, добавлен ALTER'ом).
- **activities** (Фаза 2) — одобренный проект: UUID PK, title/description, `status` enum(preparing/active/completed/cancelled), `supervising_admin_id` FK, `proposal_id` FK null, `afisha_status` enum(none/requested/published) + timestamps.
- **activity_organizers** (Фаза 2) — связка M:N: составной PK (activity_id, organizer_id), по ней работает авто-повышение/понижение ролей.
- **billing_requests** (Фаза 3) — сбор: UUID PK, `activity_id` FK, `created_by` FK, `billing_type` enum(one_time/monthly), `amount` Numeric(10,2), `currency` (RUB), `target_type` enum(all/specific), `target_users_raw` JSONB, `status` enum, `is_active` (пауза сбора отдельно от статуса), `approved_by/at`.
- **billing_subscriptions** (Фаза 3) — кто подписан: составной PK (billing_id, user_id), `is_active` (это флаг кнопки «Деактивировать»), `enrolled_at/cancelled_at`.
- **transactions** (Фаза 3) — счёт на период: UUID PK, `billing_id`+`user_id` FK, `billing_period` date null (null = one-time), `amount` (снимок), `payment_status` enum(pending/paid/failed/cancelled), `payment_provider_reference` (Фаза 4). Два partial-unique индекса против дублей: (billing_id,user_id) WHERE period IS NULL и (billing_id,user_id,period) WHERE period IS NOT NULL.
- **audit_log** — append-only лог модерации: `log_id` bigserial PK, `actor_tg_id` FK null (null=система), `actor_type` enum(admin/system), `action_type` varchar (НЕ enum — растёт), `target_tg_id`, `target_entity_type/id` (полиморфные), `reason`, `metadata` JSONB (атрибут модели — `meta`).

9 PG ENUM-типов: user_role, request_status, activity_status, vote_poll_status, afisha_status, billing_type, target_type, payment_status, actor_type.

### Файлы и функции

**bot/main.py** — точка входа.
- `resolve_group_chat_id(bot)` — если `settings.group_chat_id` строка (@username) → `get_chat` → числовой id в settings; при ошибке → None + warning.
- `main()` — собирает Bot/RedisStorage/Dispatcher; middlewares: `DbSessionMiddleware` (outer на update), `UserLoaderMiddleware`+`BanGuardMiddleware` (outer на message и callback_query — outer, чтобы `db_user` был доступен в фильтрах); роутеры в порядке: registration_review → moderation → registration → topic_guards → common; `delete_webhook(drop_pending_updates=True)`; резолв группы; polling.

**bot/config.py** — `Settings(BaseSettings)`, singleton `settings`. Валидаторы: пустая строка env → None (для всех опциональных id); числовая строка `group_chat_id` → int.

**bot/enums.py** — все str-Enum'ы: `UserRole`, `RequestStatus`, `ActivityStatus`, `VotePollStatus`, `AfishaStatus`, `BillingType`, `TargetType`, `PaymentStatus`, `ActorType`, `AuditAction` (registration_approved/rejected, user_banned/unbanned, role_changed, university_added).

**bot/db/base.py** — `naming_convention` (fk_/pk_/uq_/ix_), `Base` (DeclarativeBase с конвенцией), `engine`, `async_session_factory` (expire_on_commit=False).

**bot/db/models/** — `_types.py` (общие sa.Enum-объекты, values_callable=значения), `university.py`, `user.py`, `registration.py`, `activity.py`, `billing.py`, `audit.py` — маппинг таблиц из схемы выше. `models/__init__.py` реэкспортирует все модели (импортируется в migrations/env.py для autogenerate).

**bot/db/repositories/** — тонкий слой запросов, без бизнес-логики, без commit (кроме явных мест):
- `user_repo.get_by_tg_id(session, tg_id) -> User|None`
- `user_repo.get_by_username(session, username) -> User|None` — ilike, срезает @.
- `user_repo.upsert_from_registration(session, *, tg_id, username, display_name, university_id, university_group, birth_date) -> User` — INSERT ON CONFLICT DO UPDATE, ставит role=user.
- `university_repo.get(session, id)`; `.find_by_exact_name(session, name)` — точное без регистра; `.create_unverified(session, name)` — is_verified=False + flush; `.search(session, query, limit=5) -> list[University]` — similarity>0.2 по имени ИЛИ ilike ИЛИ similarity>0.3/ilike по алиасам, сортировка по max(score).
- `registration_repo.get(session, request_id)`; `.has_pending(session, tg_id) -> bool`; `.latest_next_allowed_attempt(session, tg_id) -> datetime|None` (по последней заявке); `.next_attempt_number(session, tg_id) -> int` (MAX+1); `.try_mark_processed(session, request_id, new_status, admin_tg_id, processed_at, next_allowed_attempt=None) -> bool` — атомарный UPDATE WHERE status='pending', False = гонка (другой админ успел).
- `audit_repo.add(session, action, *, actor_tg_id=None, actor_type=ADMIN, target_tg_id=None, target_entity_type=None, target_entity_id=None, reason=None, meta=None)` — session.add строки, без commit.

**bot/services/** — бизнес-логика, commit'ят сами:
- `throttle.py`: `TIMEOUT_CAP_MINUTES=4320`; `rejection_timeout_minutes(attempt_number) -> int` — исправленная формула `10*(2^(n-1)-1)` с капом: 0,10,30,70,150… мин. Чистая функция (покрыта тестами).
- `notification_service.py`: `send_admin_card(bot, text, keyboard=None)` — в админ-чат, топик «Заявки»; `send_admin_report(bot, text)` — топик «Репорты»; `dm_user(bot, tg_id, text) -> bool` — ЛС, ловит TelegramAPIError.
- `registration_service.py`: `INVITE_LINK_TTL=15 мин`. `check_can_apply(session, tg_id) -> str|None` — None=можно, иначе текст ошибки (зарегистрирован/забанен/pending-заявка/тайм-аут с остатком минут). `submit_request(session, bot, applicant, form) -> RegistrationRequest` — резолвит вуз или создаёт unverified (+audit UNIVERSITY_ADDED от system), считает attempt_number, вставляет заявку, шлёт карточку с кнопками в «Заявки», commit. `approve(session, bot, request_id, admin) -> (bool, str)` — атомарный захват заявки, upsert user, инвайт-ссылка (member_limit=1, 15 мин; если GROUP_CHAT_ID нет или нет прав — предупреждение в ответе), ЛС юзеру, audit, commit; str = строка статуса для дописывания в карточку. `reject(session, bot, request_id, admin, reason=None) -> (bool, str)` — тайм-аут от attempt_number, next_allowed_attempt, ЛС с причиной/временем ожидания, audit, commit.
- `role_service.py`: `ASSIGNABLE_ROLES={user,organizer,admin,custom}`. `set_role(session, actor, target, new_role) -> str|None` — ошибка текстом или None; запрещает banned через setrole и смену роли у забаненного; audit ROLE_CHANGED (old/new в meta). `ban_user(session, bot, actor, target, reason) -> str|None` — сохраняет role_before_ban, ставит banned+banned_at/reason, кикает из группы (ban_chat_member), audit. `unban_user(session, bot, actor, target) -> str|None` — восстанавливает role_before_ban или user, unban_chat_member(only_if_banned), audit.

**bot/keyboards/** — `callback_data.py`: `RegReviewCB(action, request_id)` prefix regrev; `UniversityPickCB(university_id)`; `UniversityNewCB`; `RegFormCB(action)`. `registration_kb.py`: `university_results_kb(universities)` — кнопки вузов (имя+город, обрезка 60) + «➕ Моего вуза нет в списке»; `confirm_kb()` — Отправить/Заполнить заново/Отмена. `admin_kb.py`: `registration_review_kb(request_id)` — ✅ Принять / ❌ Отклонить.

**bot/states/registration_states.py** — `RegistrationForm`: full_name → university_search → (university_new_name) → university_group → birth_date → confirm.

**bot/middlewares/** — `db_session.py`: `DbSessionMiddleware` — AsyncSession на каждый update → `data["session"]`. `role_guard.py`: `UserLoaderMiddleware` — грузит User по from_user.id → `data["db_user"]`, обновляет username при смене. `ban_guard.py`: `BanGuardMiddleware` — если role=banned: alert на callback / ответ в ЛС, обрывает обработку.

**bot/filters/role_filter.py** — `IsAdmin`, `IsOrganizerOrAbove` — проверяют `db_user` из data.

**bot/routers/**:
- `common.py`: `cmd_start` (/start, private) — приветствие с ролью или приглашение к /register; `cmd_report` (/report <текст>, private, только зарегистрированным) — репорт в топик «Репорты».
- `registration.py` — FSM-хендлеры: `cmd_register` (гейт check_can_apply), `form_full_name` (≥2 слова, 5–255), `form_university_search` (поиск → клавиатура), `form_university_pick` / `form_university_new` (callback'и), `form_university_new_name` (5–255), `form_university_group` (≤50), `form_birth_date` (ДД.ММ.ГГГГ, возраст 14–100), `form_confirm` (submit → повторный check_can_apply → submit_request; restart; cancel).
- `admin/registration_review.py`: `cb_approve`/`cb_reject` (IsAdmin; сервис → `_apply_review_result` редактирует карточку, дописывая статус, снимает кнопки); `cb_not_admin` — fallback-alert не-админам.
- `admin/moderation.py` (весь роутер под IsAdmin): `_resolve_target(session, ref)` — по tg_id или @username; `cmd_ban` (/ban <id|@user> [причина], запрет self-ban), `cmd_unban`, `cmd_setrole` (/setrole <id|@user> <роль из ASSIGNABLE_ROLES>).
- `group/topic_guards.py`: `group_message` — только в GROUP_CHAT_ID; удаляет сообщения не-админов в read-only топиках (Объявления=2, Афиша=6); при «@admin» в тексте шлёт репорт со ссылкой на сообщение (`_message_link` — t.me/c/<id без -100>/<msg_id>).

**scripts/**: `bootstrap_admin.py` — `run(tg_id, name, username)` upsert users с role=admin; CLI `--tg-id --name [--username]`. `seed_universities.py` — `run(path)` импорт CSV `name;city;aliases` (алиасы через |), пропускает существующие вузы/алиасы; CLI: путь к файлу.

**migrations/versions/0001_initial_schema.py** — вся схема: CREATE EXTENSION pg_trgm, 9 ENUM-типов (create_type=False + явный .create), 11 таблиц, GIN-индексы, partial-unique на transactions, циркулярный FK proposals→activities через отдельный create_foreign_key. `migrations/env.py` — подставляет `settings.database_url`, target_metadata=Base.metadata.

**tests/test_registration_throttle.py** — формула тайм-аута: последовательность 0/10/30/70/150/310, кап на больших n, монотонность. `conftest.py` в корне — пустой (для sys.path).

## План и прогресс

- ✅ **Фаза 0 — Каркас**: структура, Docker Compose, конфиг, Alembic, рабочий /start.
- ✅ **Фаза 1 — Регистрация, роли, аудит, инвайты**: FSM регистрации с автокомплитом вузов, approve/reject с атомарным захватом, исправленный тайм-аут (10×(2^(n-1)−1), кап 72ч), одноразовые ссылки (15 мин), ban/unban/setrole, ban-guard, read-only топики, @admin-вызовы, /report, audit_log.
- ✅ **Корректировка под реальную топологию**: админ-чат-форум («Заявки»=269, «Репорты»=271), реальные id топиков группы, GROUP_CHAT_ID по @username.
- ✅ **Локальная проверка Docker**: миграции применились, бот поллит, группа резолвится (стек работал часами стабильно).
- 🔄 **Деплой**: локально работает; GitHub и VPS — впереди.
- ⬜ **Фаза 2 — Активности**: proposals FSM, пре-голосования, статусы с авто-promote/demote ролей, Афиша, safety-net крон (APScheduler).
- ⬜ **Фаза 3 — Биллинг (ручное подтверждение)**: billing FSM, подписки, счета, дашборд организатора, отписка, месячный крон.
- ⬜ **Фаза 4 — ЮKassa (Telegram Payments)** + очередь верификации вузов.

**Сейчас находимся:** между локальной проверкой и деплоем (GitHub → VPS).
**Сделано последним:** локальный запуск проверен; скиллы project-state/project-load; этот файл.
**Осталось до боевого запуска:** push на GitHub → аренда VPS → деплой (git clone + .env со сменённым паролем БД + compose up) → bootstrap первого админа → e2e-прогон регистрации живьём.
**Следующий шаг:** после `gh auth login` пользователя — создать приватный репозиторий и запушить.
**Заблокировано:** `gh auth login` (действие пользователя); выбор/аренда VPS (решение пользователя); tg_id пользователя для bootstrap_admin — не известен.

## Журнал сессий

### 2026-07-07 — план и Фазы 0–1
- Утверждён план (см. путь в начале файла): исправлена формула тайм-аута из ТЗ (не совпадала с собственными примерами), решения: платёжный шлюз → Фаза 4 (в v1 ручное подтверждение), чаты активностей — ссылкой, справочник вузов стартует пустым (+CSV-сид).
- Написан весь каркас и Фаза 1 (63 файла), коммит `7793707`.
- Правки под реальную топологию чатов (админ-форум, /report, @username группы), коммит `2d1bd81`. Реальный BOT_TOKEN и id чатов — в .env.

### 2026-07-08 — локальный запуск и план хостинга
- `docker compose up --build` локально: миграции ок, 11 таблиц + pg_trgm, бот @ttc_adm_bot поллит, группа резолвнулась в -1004334303503. Редкие сетевые обрывы до api.telegram.org (домашний провайдер) — aiogram сам переподключается.
- Решение по хостингу: VPS (1–2 ГБ, Ubuntu, ~150–300 ₽/мес), доставка кода через приватный GitHub. Установлены Docker Desktop (запущен) и GitHub CLI; ожидается gh auth login от пользователя.
- Зафиксированы требования к правам бота (BotFather Group Privacy off; в группе: ссылки/удаление/бан/топики).

### 2026-07-12 — скиллы project-state / project-load
- Созданы пользовательские скиллы: `project-state` (ведение PROJECT.md + отчёт о контексте после каждого блока) и `project-load` (загрузка понимания проекта из одного файла по команде). Глобальный `~/.claude/CLAUDE.md` делает их обязательными во всех проектах.
- Написан этот PROJECT.md.
