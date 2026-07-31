"""Сборка «Карты сценариев» — HTML-страницы, по которой владелец проекта видит
все кнопки и команды бота, кому они доступны и что происходит после нажатия.

Зачем нужен генератор, а не просто написанный руками файл: карта, написанная
руками, устаревает через две недели. Здесь всё, что можно вычислить из кода,
вычисляется из кода при каждой сборке:

* подписи кнопок берутся из ``bot/texts.py`` (класс ``BTN``) по ссылке вида
  ``BTN.START_REGISTER`` — переименовали кнопку, карта показывает новое имя;
* список команд вычитывается из декораторов в ``bot/routers/``;
* модули прав, слоты контента, сценарии, таблицы CRUD и роли — из их реестров;
* таблицы базы — из моделей SQLAlchemy.

Руками (в ``docs/scenario-map.json``) описывается только то, что из кода
не вычисляется в принципе: что действие означает для человека и куда он
попадает дальше. За тем, чтобы это описание не разошлось с кодом, следит
автотест ``tests/test_scenario_map.py``.

Запуск:  python -m scripts.build_scenario_map
Результат: docs/scenario-map.html (открыть двойным кликом)
"""

from __future__ import annotations

import html
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPEC_PATH = ROOT / "docs" / "scenario-map.json"
OUT_PATH = ROOT / "docs" / "scenario-map.html"
ROUTERS_DIR = ROOT / "bot" / "routers"

sys.path.insert(0, str(ROOT))


# --------------------------------------------------------------------------
# Часть 1. Что вычитывается из живого кода
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class CodeFacts:
    """Снимок фактов о боте, собранный из исходников на момент сборки."""

    buttons: dict[str, str]  # BTN.START_REGISTER -> "📝 Регистрация"
    commands: dict[str, str]  # "start" -> "bot/routers/common.py"
    scenarios: dict[str, str]  # ключ сценария -> человеческое название
    modules: dict[str, str]  # ключ модуля прав -> название
    slots: dict[str, str]  # ключ блока /content -> название
    crud_tables: dict[str, str]  # код таблицы в CRUD -> название
    roles: list[str]  # значения UserRole
    db_tables: list[str]  # имена таблиц из моделей


def _collect_buttons() -> dict[str, str]:
    from bot.texts import BTN

    return {
        f"BTN.{name}": value
        for name, value in vars(BTN).items()
        if name.isupper() and isinstance(value, str)
    }


_COMMAND_CALL = re.compile(r"Command\(([^)]*)\)", re.S)
_QUOTED = re.compile(r"[\"']([A-Za-z_][A-Za-z0-9_]*)[\"']")


def _collect_commands() -> dict[str, str]:
    """Ищет по роутерам все команды, зарегистрированные через Command(...)."""
    found: dict[str, str] = {}
    for path in sorted(ROUTERS_DIR.rglob("*.py")):
        source = path.read_text(encoding="utf-8")
        rel = path.relative_to(ROOT).as_posix()
        if "CommandStart(" in source:
            found.setdefault("start", rel)
        for call in _COMMAND_CALL.findall(source):
            for name in _QUOTED.findall(call):
                found.setdefault(name, rel)
    return found


def _registry_titles(registry: dict, *attrs: str) -> dict[str, str]:
    """Превращает реестр {ключ: объект} в {ключ: человеческое название}."""
    titles: dict[str, str] = {}
    for key, item in registry.items():
        label = str(key)
        for attr in attrs:
            value = getattr(item, attr, None)
            if isinstance(value, str) and value:
                label = value
                break
        titles[str(key)] = label
    return titles


def collect_code_facts() -> CodeFacts:
    from bot.db.base import Base
    from bot.enums import UserRole
    from bot.services import content_service, crud_service, permission_service
    from bot.services import scenario_service

    import bot.db.models  # noqa: F401  — регистрирует все таблицы в Base.metadata

    return CodeFacts(
        buttons=_collect_buttons(),
        commands=_collect_commands(),
        scenarios=_registry_titles(scenario_service.SCENARIOS, "title", "name"),
        modules=_registry_titles(permission_service.MODULES, "title", "name", "label"),
        slots=_registry_titles(content_service.SLOTS, "title", "name", "label"),
        crud_tables=_registry_titles(crud_service.TABLES, "title", "name", "label"),
        roles=[role.value for role in UserRole],
        db_tables=sorted(Base.metadata.tables.keys()),
    )


# --------------------------------------------------------------------------
# Часть 2. Разрешение ссылок в описании
# --------------------------------------------------------------------------


class SpecError(RuntimeError):
    """Описание карты разошлось с кодом — сборка обязана упасть громко."""


def resolve_trigger(node: dict, facts: CodeFacts) -> str:
    """Возвращает текст, которым запускается узел.

    Кнопки описываются ссылкой ``trigger_ref`` на поле класса BTN, поэтому
    подпись всегда берётся из кода. Команды и прочее — литералом.
    """
    ref = node.get("trigger_ref")
    if ref:
        if ref not in facts.buttons:
            raise SpecError(
                f"Узел «{node['id']}» ссылается на {ref}, но такой кнопки "
                f"в bot/texts.py больше нет. Обновите docs/scenario-map.json."
            )
        return facts.buttons[ref]
    text = node.get("trigger_text", "")
    if not text:
        raise SpecError(f"У узла «{node['id']}» не задан ни trigger_ref, ни trigger_text.")
    return text


# --------------------------------------------------------------------------
# Часть 3. Отрисовка HTML
# --------------------------------------------------------------------------

ROLE_LABELS = {
    "guest": "Гость",
    "user": "Участник",
    "organizer": "Организатор",
    "admin": "Админ",
    "superadmin": "Суперадмин",
    "owner": "Владелец",
    "banned": "Забаненный",
    "any": "Все",
}

ROLE_ORDER = ["guest", "user", "organizer", "admin", "superadmin", "owner", "banned"]

KIND_LABELS = {
    "command": ("⌨", "команда"),
    "reply_button": ("▭", "кнопка меню"),
    "inline_button": ("◻", "кнопка под сообщением"),
    "message": ("✎", "просто сообщение"),
    "group_event": ("👥", "событие в группе"),
    "auto": ("⚙", "само"),
}

WHERE_LABELS = {
    "dm": "в личке бота",
    "group": "в группе сообщества",
    "admin_chat": "в чате админов",
}


def esc(value: str) -> str:
    return html.escape(str(value), quote=True)


def _chips(items: list[str], css: str) -> str:
    return "".join(f'<span class="chip {css}">{esc(item)}</span>' for item in items)


def _node_html(node: dict, facts: CodeFacts, known_ids: set[str]) -> str:
    trigger = resolve_trigger(node, facts)
    icon, kind_label = KIND_LABELS.get(node["trigger_kind"], ("•", node["trigger_kind"]))
    roles = node.get("roles") or ["any"]
    role_attr = " ".join(roles)
    role_badges = "".join(
        f'<span class="role r-{esc(r)}">{esc(ROLE_LABELS.get(r, r))}</span>' for r in roles
    )

    module = node.get("perm_module") or ""
    module_html = ""
    if module:
        title = facts.modules.get(module, module)
        module_html = f'<span class="module">модуль прав: {esc(title)}</span>'

    next_html = ""
    nexts = node.get("next") or []
    if nexts:
        links = []
        for target in nexts:
            if target not in known_ids:
                raise SpecError(
                    f"Узел «{node['id']}» ссылается на несуществующий следующий шаг «{target}»."
                )
            links.append(f'<a class="next" href="#{esc(target)}">{esc(target)}</a>')
        next_html = f'<div class="row"><b>Дальше</b>{"".join(links)}</div>'

    db_html = ""
    reads = node.get("db_reads") or []
    writes = node.get("db_writes") or []
    if reads or writes:
        parts = []
        if reads:
            parts.append(f'<b>читает</b>{_chips(reads, "read")}')
        if writes:
            parts.append(f'<b>пишет</b>{_chips(writes, "write")}')
        db_html = f'<div class="row db">{"".join(parts)}</div>'

    notify_html = ""
    notifies = node.get("notifies") or []
    if notifies:
        notify_html = f'<div class="row"><b>Уведомляет</b>{_chips(notifies, "notify")}</div>'

    handler = node.get("handler", "")
    return f"""
    <article class="node" id="{esc(node['id'])}" data-roles="{esc(role_attr)}"
             data-search="{esc((trigger + ' ' + node.get('does', '') + ' ' + node.get('shows', '')).lower())}">
      <header>
        <span class="kind" title="{esc(kind_label)}">{icon}</span>
        <span class="trigger">{esc(trigger)}</span>
        <span class="where">{esc(WHERE_LABELS.get(node.get('where', ''), ''))}</span>
        {role_badges}{module_html}
      </header>
      <div class="row"><b>Делает</b><span>{esc(node.get('does', ''))}</span></div>
      <div class="row"><b>Человек видит</b><span>{esc(node.get('shows', ''))}</span></div>
      {next_html}{db_html}{notify_html}
      <footer><code>{esc(handler)}</code> · <span class="anchor">#{esc(node['id'])}</span></footer>
    </article>"""


def _registry_html(entries: list[dict], hint: str) -> str:
    """Раздел-реестр: редактируемые сценарии или блоки /content.

    Показывает, в какой именно момент человек видит каждое сообщение —
    иначе список из двух десятков ключей ни о чём не говорит.
    """
    rows = [f'<p class="legend">{esc(hint)}</p>']
    for entry in entries:
        links = "".join(
            f'<a class="next" href="#{esc(node_id)}">{esc(node_id)}</a>'
            for node_id in entry.get("nodes", [])
        )
        rows.append(
            f"""
    <article class="node" data-roles="any"
             data-search="{esc((entry['title'] + ' ' + entry['key']).lower())}">
      <header><span class="trigger">{esc(entry['title'])}</span>
      <span class="where">ключ: {esc(entry['key'])}</span></header>
      <div class="row"><b>Где это видно</b>{links or '<span class="where">—</span>'}</div>
    </article>"""
        )
    return "".join(rows)


def _table_html(table: dict) -> str:
    fields = "".join(f"<li>{esc(f)}</li>" for f in table.get("key_fields", []))
    links = "".join(f"<li>{esc(l)}</li>" for l in table.get("links", []))
    written = _chips(table.get("written_by", []), "write")
    read = _chips(table.get("read_by", []), "read")
    links_block = f"<div class='sub'><b>Связи</b><ul>{links}</ul></div>" if links else ""
    return f"""
    <article class="table" id="tbl-{esc(table['name'])}">
      <header><span class="trigger">{esc(table.get('title') or table['name'])}</span>
      <span class="where">таблица {esc(table['name'])}</span></header>
      <div class="row"><span>{esc(table.get('purpose', ''))}</span></div>
      <div class="sub"><b>Главные поля</b><ul>{fields}</ul></div>
      {links_block}
      <div class="row"><b>Сюда пишут</b>{written}</div>
      <div class="row"><b>Отсюда показывается</b>{read}</div>
    </article>"""


CSS = """
:root{--bg:#fbfbfd;--fg:#16181d;--muted:#6b7280;--line:#e3e5ea;--card:#fff;
--accent:#2d6cdf;--read:#0d7a5f;--write:#b0561a;--notify:#7038a8;}
@media (prefers-color-scheme:dark){:root{--bg:#14161a;--fg:#e8eaee;--muted:#9aa1ad;
--line:#2a2e36;--card:#1b1e24;--accent:#6fa0ff;--read:#4bd0a8;--write:#f0a35e;--notify:#c193f5;}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);
font:15px/1.55 -apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif}
.wrap{max-width:1180px;margin:0 auto;padding:24px 18px 80px}
h1{font-size:26px;margin:0 0 4px}
.meta{color:var(--muted);font-size:13px;margin-bottom:20px}
.controls{position:sticky;top:0;z-index:5;background:var(--bg);
padding:12px 0;border-bottom:1px solid var(--line);margin-bottom:20px}
.filters{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:8px}
button.f{border:1px solid var(--line);background:var(--card);color:var(--fg);
border-radius:999px;padding:5px 13px;cursor:pointer;font-size:13px}
button.f.on{background:var(--accent);border-color:var(--accent);color:#fff}
input.search{width:100%;padding:8px 12px;border:1px solid var(--line);
border-radius:8px;background:var(--card);color:var(--fg);font-size:14px}
h2{font-size:19px;margin:32px 0 12px;padding-bottom:6px;border-bottom:2px solid var(--line)}
.node,.table{background:var(--card);border:1px solid var(--line);border-radius:10px;
padding:12px 14px;margin-bottom:10px}
.node:target,.table:target{border-color:var(--accent);box-shadow:0 0 0 3px rgba(45,108,223,.18)}
.node header,.table header{display:flex;flex-wrap:wrap;align-items:center;gap:8px;margin-bottom:8px}
.kind{font-size:15px;color:var(--muted)}
.trigger{font-weight:650;font-size:15.5px}
.where{color:var(--muted);font-size:12.5px}
.role{font-size:11.5px;padding:2px 8px;border-radius:999px;border:1px solid var(--line);color:var(--muted)}
.r-owner{border-color:var(--notify);color:var(--notify)}
.r-superadmin{border-color:var(--accent);color:var(--accent)}
.r-admin{border-color:var(--write);color:var(--write)}
.r-guest{border-style:dashed}
.module{font-size:11.5px;color:var(--muted);border:1px dashed var(--line);border-radius:6px;padding:2px 8px}
.row{display:flex;flex-wrap:wrap;gap:8px;align-items:baseline;margin:4px 0;font-size:14px}
.row b{min-width:120px;color:var(--muted);font-weight:600;font-size:12.5px;text-transform:uppercase;letter-spacing:.03em}
.chip{font-size:12px;padding:1px 8px;border-radius:6px;border:1px solid var(--line)}
.chip.read{color:var(--read);border-color:var(--read)}
.chip.write{color:var(--write);border-color:var(--write)}
.chip.notify{color:var(--notify);border-color:var(--notify)}
a.next{font-size:12.5px;color:var(--accent);text-decoration:none;
border:1px solid var(--accent);border-radius:6px;padding:1px 8px}
a.next:hover{background:var(--accent);color:#fff}
footer{margin-top:8px;padding-top:6px;border-top:1px dashed var(--line);
color:var(--muted);font-size:11.5px;display:flex;gap:8px;justify-content:space-between}
code{font-family:ui-monospace,Consolas,monospace;font-size:11.5px}
.sub{margin:6px 0}
.sub b{color:var(--muted);font-size:12.5px;text-transform:uppercase;letter-spacing:.03em}
.sub ul{margin:4px 0 0;padding-left:20px}
.sub li{font-size:13.5px}
.stats{display:flex;flex-wrap:wrap;gap:10px;margin:12px 0 0}
.stat{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:8px 14px;font-size:13px}
.stat b{display:block;font-size:20px}
.hidden{display:none}
.legend{color:var(--muted);font-size:13px;margin:10px 0 0}
@media print{.controls{position:static}.node{break-inside:avoid}}
"""

JS = """
const filters=document.querySelectorAll('button.f');
const search=document.getElementById('q');
let role='all';
function apply(){
  const q=search.value.trim().toLowerCase();
  document.querySelectorAll('.node').forEach(n=>{
    const roles=(n.dataset.roles||'').split(' ');
    const okRole = role==='all' || roles.includes(role) || roles.includes('any');
    const okText = !q || (n.dataset.search||'').includes(q);
    n.classList.toggle('hidden', !(okRole&&okText));
  });
  document.querySelectorAll('section.area').forEach(s=>{
    const any=s.querySelector('.node:not(.hidden)');
    s.classList.toggle('hidden', !any);
  });
}
filters.forEach(b=>b.addEventListener('click',()=>{
  filters.forEach(x=>x.classList.remove('on'));
  b.classList.add('on'); role=b.dataset.role; apply();
}));
search.addEventListener('input',apply);
apply();
"""


def render_html(spec: dict, facts: CodeFacts) -> str:
    known_ids = {node["id"] for area in spec["areas"] for node in area["nodes"]}

    filter_buttons = ['<button class="f on" data-role="all">Все роли</button>']
    for role in ROLE_ORDER:
        filter_buttons.append(
            f'<button class="f" data-role="{esc(role)}">{esc(ROLE_LABELS[role])}</button>'
        )

    areas_html = []
    for area in spec["areas"]:
        nodes = "".join(_node_html(node, facts, known_ids) for node in area["nodes"])
        areas_html.append(
            f'<section class="area"><h2 id="area-{esc(area["key"])}">{esc(area["label"])}</h2>{nodes}</section>'
        )

    tables_html = "".join(_table_html(table) for table in spec.get("tables", []))

    node_count = len(known_ids)
    stats = [
        ("Точек входа", node_count),
        ("Команд в коде", len(facts.commands)),
        ("Кнопок в texts.py", len(facts.buttons)),
        ("Редактируемых сценариев", len(facts.scenarios)),
        ("Модулей прав", len(facts.modules)),
        ("Таблиц в базе", len(facts.db_tables)),
    ]
    stats_html = "".join(
        f'<div class="stat"><b>{value}</b>{esc(label)}</div>' for label, value in stats
    )

    built = datetime.now(timezone.utc).astimezone().strftime("%d.%m.%Y %H:%M")
    commit = _git_commit()

    return f"""<!doctype html>
<html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>TTC — карта сценариев</title><style>{CSS}</style></head>
<body><div class="wrap">
<h1>Карта сценариев бота TTC</h1>
<div class="meta">Собрана из кода {esc(built)} · коммит {esc(commit)} ·
пересобрать: двойной клик по <code>карта-сценариев.bat</code> в корне проекта</div>
<div class="stats">{stats_html}</div>
<p class="legend">Каждая карточка — одна точка входа: команда, кнопка меню, кнопка под сообщением
или сообщение внутри формы. «Дальше» — куда человек попадает следующим шагом, ссылка ведёт
к нужной карточке. Цветные метки: <span class="chip read">читает из базы</span>
<span class="chip write">пишет в базу</span> <span class="chip notify">кому уходит сообщение</span>.</p>
<div class="controls">
  <div class="filters">{"".join(filter_buttons)}</div>
  <input class="search" id="q" placeholder="Поиск по кнопкам и описаниям…">
</div>
{"".join(areas_html)}
<section><h2 id="area-scenarios">Сообщения, которые бот шлёт сам</h2>
{_registry_html(spec.get("scenarios", []), "Каждое из этих сообщений правится прямо в боте: «🛠 Админство» → «🧩 Сценарии». Ссылка справа ведёт к моменту, когда человек его получает.")}</section>
<section><h2 id="area-slots">Блоки, которые правятся командой /content</h2>
{_registry_html(spec.get("slots", []), "Это тексты и файлы разделов. Меняются без программиста, изменение видно людям сразу.")}</section>
<section class="area"><h2 id="area-db">Что лежит в базе и откуда берётся</h2>{tables_html}</section>
</div><script>{JS}</script></body></html>
"""


def _git_commit() -> str:
    try:
        out = subprocess.run(
            ["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return out.stdout.strip() or "—"
    except Exception:  # noqa: BLE001 — карта не должна падать из-за git
        return "—"


def main() -> int:
    spec = json.loads(SPEC_PATH.read_text(encoding="utf-8"))
    facts = collect_code_facts()
    OUT_PATH.write_text(render_html(spec, facts), encoding="utf-8")
    nodes = sum(len(area["nodes"]) for area in spec["areas"])
    print(f"Карта собрана: {OUT_PATH}")
    print(f"  точек входа: {nodes}, таблиц: {len(spec.get('tables', []))}")
    print(f"  из кода подтянуто: команд {len(facts.commands)}, кнопок {len(facts.buttons)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
