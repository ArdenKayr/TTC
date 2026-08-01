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

# Стили визуальной схемы. Вынесены отдельно от стилей списка, чтобы правки
# схемы не задевали то, что уже работает.
GRAPH_CSS = """
:root{--k-command:#2d6cdf;--k-reply_button:#0d7a5f;--k-inline_button:#b0561a;
--k-message:#7038a8;--k-group_event:#c2185b;--k-auto:#8a8f99;}
@media (prefers-color-scheme:dark){:root{--k-command:#6fa0ff;--k-reply_button:#4bd0a8;
--k-inline_button:#f0a35e;--k-message:#c193f5;--k-group_event:#f47da8;--k-auto:#8a8f99;}}
.views{display:flex;gap:6px;align-items:center;margin-bottom:8px}
button.v{border:1px solid var(--line);background:var(--card);color:var(--fg);
border-radius:8px;padding:5px 15px;cursor:pointer;font-size:13.5px;font-weight:600}
button.v.on{background:var(--fg);border-color:var(--fg);color:var(--bg)}
.zoom{margin-left:auto;color:var(--muted);font-size:12.5px;display:flex;gap:4px;align-items:center}
.zoom button{width:26px;height:26px;border:1px solid var(--line);background:var(--card);
color:var(--fg);border-radius:6px;cursor:pointer;font-size:14px;line-height:1}
.glegend{display:flex;flex-wrap:wrap;gap:12px;margin:12px 0 16px;font-size:12.5px;color:var(--muted)}
.glegend i{display:inline-block;width:10px;height:10px;border-radius:3px;margin-right:5px;vertical-align:-1px}
.gpanel{margin:0 0 22px}
.gpanel h3{font-size:15px;margin:0 0 8px;display:flex;align-items:baseline;gap:8px}
.gpanel h3 span{font-weight:400;color:var(--muted);font-size:12.5px}
.gwrap{overflow:auto;max-height:78vh;border:1px solid var(--line);border-radius:10px;
background:var(--card);padding:4px}
.gn rect.box{fill:var(--card);stroke:var(--line);stroke-width:1.5}
.gn text.lbl{fill:var(--fg);font-size:12.5px;font-family:inherit}
.gn text.ico{font-size:12px;fill:var(--muted)}
.gn{cursor:pointer}
.gn:hover rect.box{stroke:var(--accent);stroke-width:2.5}
.gn.iso rect.box{stroke-dasharray:4 3}
.gn.dim{opacity:.18}
.ge{fill:none;stroke:var(--line);stroke-width:1.6}
.ge.on{stroke:var(--accent);stroke-width:2.4}
.ge.dim{opacity:.15}
.gtip{position:fixed;z-index:50;max-width:440px;pointer-events:none;
background:var(--card);border:1px solid var(--accent);border-radius:10px;
padding:12px 14px;box-shadow:0 10px 30px rgba(0,0,0,.22);font-size:14px}
.gtip .row b{min-width:104px}
.gempty{color:var(--muted);font-size:13.5px;padding:14px}
"""

# Отрисовка схемы. Раскладка считается в браузере, а не при сборке: так страница
# остаётся одним самодостаточным файлом, а смена роли перестраивает картинку под
# то, что эта роль реально видит, без пустых дыр от скрытых узлов.
GRAPH_JS = """
const NS='http://www.w3.org/2000/svg';
const NW=206,NH=46,GAPX=88,GAPY=18,PAD=16;
const ICONS={command:'⌨',reply_button:'▭',inline_button:'◻',
  message:'✎',group_event:'👥',auto:'⚙'};
const host=document.getElementById('graph-areas');
const tip=document.getElementById('gtip');
let zoom=1;

function el(name,attrs,parent){
  const e=document.createElementNS(NS,name);
  for(const k in attrs) e.setAttribute(k,attrs[k]);
  if(parent) parent.appendChild(e);
  return e;
}
function short(s,max){return s.length>max?s.slice(0,max-1)+'…':s;}
function seen(n,r){return r==='all'||n.r.indexOf(r)>=0||n.r.indexOf('any')>=0;}

/* Раскладывает область по слоям: слой узла — на каком шаге от начала цепочки
   человек до него добирается. Считается обходом в ширину, а не «правее всех
   предков»: в боте полно колец (меню → раздел → «Назад» → меню), и от них
   раскладка по предкам уезжает в бесконечность. Стрелка «Назад» при таком
   счёте честно рисуется стрелкой, идущей назад. */
function place(nodes){
  const alive=new Set(nodes.map(n=>n.id));
  const edges=[];
  nodes.forEach(n=>(n.n||[]).forEach(t=>{if(alive.has(t))edges.push([n.id,t]);}));
  const out=new Map(nodes.map(n=>[n.id,[]]));
  const parents=new Map(nodes.map(n=>[n.id,[]]));
  const deg=new Map(nodes.map(n=>[n.id,0]));
  edges.forEach(([a,b])=>{
    out.get(a).push(b);parents.get(b).push(a);
    deg.set(a,deg.get(a)+1);deg.set(b,deg.get(b)+1);
  });

  const layer=new Map();
  const queue=[];
  nodes.forEach(n=>{if(!parents.get(n.id).length){layer.set(n.id,0);queue.push(n.id);}});
  /* Вся область может оказаться замкнутым кольцом без единой точки входа —
     тогда началом считаем самый разветвлённый узел. */
  if(!queue.length&&nodes.length){
    let seed=nodes[0];
    nodes.forEach(n=>{if(out.get(n.id).length>out.get(seed.id).length)seed=n;});
    layer.set(seed.id,0);queue.push(seed.id);
  }
  for(let i=0;i<queue.length;i++){
    const from=queue[i];
    for(const to of out.get(from)){
      if(!layer.has(to)){layer.set(to,layer.get(from)+1);queue.push(to);}
    }
  }
  nodes.forEach(n=>{if(!layer.has(n.id))layer.set(n.id,0);});

  const rows=[];
  nodes.forEach(n=>{const L=layer.get(n.id);(rows[L]=rows[L]||[]).push(n);});
  const pos=new Map();
  rows.forEach((row,L)=>{
    if(!row)return;
    if(L===0){
      /* Одиночки — вниз колонки, чтобы не разрывать реальные цепочки. */
      row.sort((x,y)=>(deg.get(x.id)?0:1)-(deg.get(y.id)?0:1));
    }else{
      /* Узел встаёт напротив тех, кто на него ссылается: меньше пересечений. */
      const mid=n=>{
        const ps=parents.get(n.id).map(p=>pos.get(p)).filter(Boolean);
        return ps.length?ps.reduce((s,p)=>s+p.y,0)/ps.length:1e9;
      };
      row.sort((x,y)=>mid(x)-mid(y));
    }
    row.forEach((n,i)=>pos.set(n.id,{x:PAD+L*(NW+GAPX),y:PAD+i*(NH+GAPY)}));
  });
  const sizes=rows.filter(Boolean).map(r=>r.length);
  const wide=sizes.length?Math.max.apply(null,sizes):1;
  return {edges:edges,pos:pos,deg:deg,
          w:PAD*2+(rows.length-1)*(NW+GAPX)+NW,
          h:PAD*2+(wide-1)*(NH+GAPY)+NH};
}

function drawArea(area,role){
  const nodes=area.nodes.filter(n=>seen(n,role));
  if(!nodes.length)return null;
  const L=place(nodes);

  const box=document.createElement('figure');
  box.className='gpanel';
  const head=document.createElement('h3');
  head.innerHTML='<b></b><span></span>';
  head.querySelector('b').textContent=area.label;
  head.querySelector('span').textContent=nodes.length+' шт. · '+L.edges.length+' переходов';
  box.appendChild(head);

  const wrap=document.createElement('div');
  wrap.className='gwrap';
  const svg=el('svg',{viewBox:'0 0 '+L.w+' '+L.h,width:L.w*zoom,height:L.h*zoom});
  const mid=el('marker',{id:'arw-'+area.key,viewBox:'0 0 10 10',refX:9,refY:5,
    markerWidth:6,markerHeight:6,orient:'auto-start-reverse'},el('defs',{},svg));
  el('path',{d:'M0,0 L10,5 L0,10 z',fill:'currentColor'},mid);

  for(const [a,b] of L.edges){
    const p=L.pos.get(a),q=L.pos.get(b);
    const x1=p.x+NW,y1=p.y+NH/2,x2=q.x,y2=q.y+NH/2;
    const bend=Math.max(34,(x2-x1)/2);
    el('path',{class:'ge','data-a':a,'data-b':b,'marker-end':'url(#arw-'+area.key+')',
      d:'M'+x1+','+y1+' C'+(x1+bend)+','+y1+' '+(x2-bend)+','+y2+' '+x2+','+y2},svg);
  }

  nodes.forEach(n=>{
    const p=L.pos.get(n.id);
    const g=el('g',{class:'gn'+(L.deg.get(n.id)?'':' iso'),'data-id':n.id,
      transform:'translate('+p.x+','+p.y+')'},svg);
    el('rect',{class:'box',width:NW,height:NH,rx:9},g);
    el('rect',{width:4,height:NH-16,x:0,y:8,rx:2,fill:'var(--k-'+n.k+')'},g);
    const ico=el('text',{class:'ico',x:14,y:NH/2+4},g);
    ico.textContent=ICONS[n.k]||'•';
    const lbl=el('text',{class:'lbl',x:32,y:NH/2+4.5},g);
    lbl.textContent=short(n.t,24);

    g.addEventListener('mouseenter',()=>{
      const card=document.getElementById(n.id);
      if(card){tip.innerHTML=card.innerHTML;tip.classList.remove('hidden');}
      svg.querySelectorAll('.ge').forEach(e=>{
        const touch=e.dataset.a===n.id||e.dataset.b===n.id;
        e.classList.toggle('on',touch);e.classList.toggle('dim',!touch);
      });
    });
    g.addEventListener('mousemove',ev=>{
      const w=tip.offsetWidth,h=tip.offsetHeight;
      let x=ev.clientX+18,y=ev.clientY+16;
      if(x+w>innerWidth-10)x=ev.clientX-w-18;
      if(y+h>innerHeight-10)y=Math.max(10,innerHeight-h-10);
      tip.style.left=x+'px';tip.style.top=y+'px';
    });
    g.addEventListener('mouseleave',()=>{
      tip.classList.add('hidden');
      svg.querySelectorAll('.ge').forEach(e=>e.classList.remove('on','dim'));
    });
    g.addEventListener('click',()=>{showView('list');location.hash='#'+n.id;});
  });

  wrap.appendChild(svg);
  box.appendChild(wrap);
  return box;
}

function renderGraph(){
  host.innerHTML='';
  let drawn=0;
  GRAPH.areas.forEach(area=>{
    const panel=drawArea(area,role);
    if(panel){host.appendChild(panel);drawn++;}
  });
  if(!drawn){
    host.innerHTML='<p class="gempty">Для этой роли на карте нет ни одной точки входа.</p>';
  }
  markSearch();
}

/* Поиск не прячет узлы схемы, а гасит несовпавшие: цепочка остаётся видимой. */
function markSearch(){
  const q=search.value.trim().toLowerCase();
  document.querySelectorAll('.gn').forEach(g=>{
    if(!q){g.classList.remove('dim');return;}
    const card=document.getElementById(g.dataset.id);
    const hay=card?(card.dataset.search||''):'';
    g.classList.toggle('dim',hay.indexOf(q)<0);
  });
}

function setZoom(step){
  zoom=Math.min(1.6,Math.max(.45,Math.round((zoom+step)*100)/100));
  document.querySelectorAll('.gwrap svg').forEach(s=>{
    const vb=s.getAttribute('viewBox').split(' ');
    s.setAttribute('width',vb[2]*zoom);s.setAttribute('height',vb[3]*zoom);
  });
}
document.getElementById('zin').addEventListener('click',()=>setZoom(.15));
document.getElementById('zout').addEventListener('click',()=>setZoom(-.15));
"""

JS = """
const filters=document.querySelectorAll('button.f');
const views=document.querySelectorAll('button.v');
const search=document.getElementById('q');
let role='all';
let view='graph';

function showView(name){
  view=name;
  views.forEach(b=>b.classList.toggle('on',b.dataset.view===name));
  document.getElementById('graph-view').classList.toggle('hidden',name!=='graph');
  document.getElementById('list-view').classList.toggle('hidden',name!=='list');
  document.getElementById('zoombox').classList.toggle('hidden',name!=='graph');
  if(name==='graph')renderGraph();
}
views.forEach(b=>b.addEventListener('click',()=>showView(b.dataset.view)));

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
  b.classList.add('on'); role=b.dataset.role;
  apply();
  if(view==='graph')renderGraph();
}));
search.addEventListener('input',()=>{apply();if(view==='graph')markSearch();});

/* Ссылка вида map.html#reg_nick должна открывать карточку, а не пустой список. */
if(location.hash.length>1){showView('list');}else{showView('graph');}
apply();
"""


def _graph_payload(spec: dict, facts: CodeFacts) -> str:
    """Готовит данные для схемы: только то, чего нет в карточках списка.

    Подробности (что делает, что человек видит, что читает и пишет) схема
    подтягивает из уже отрисованной карточки по её id — чтобы одно и то же
    описание не лежало на странице дважды и не разъезжалось.
    """
    areas = [
        {
            "key": area["key"],
            "label": area["label"],
            "nodes": [
                {
                    "id": node["id"],
                    "t": resolve_trigger(node, facts),
                    "k": node["trigger_kind"],
                    "r": node.get("roles") or ["any"],
                    "n": node.get("next") or [],
                }
                for node in area["nodes"]
            ],
        }
        for area in spec["areas"]
    ]
    raw = json.dumps({"areas": areas}, ensure_ascii=False, separators=(",", ":"))
    # «</» внутри строки закрыло бы тег <script> раньше времени
    return raw.replace("</", "<\\/")


def _kind_legend() -> str:
    items = []
    for kind, (icon, label) in KIND_LABELS.items():
        items.append(
            f'<span><i style="background:var(--k-{esc(kind)})"></i>{icon} {esc(label)}</span>'
        )
    items.append('<span><i style="border:1px dashed var(--muted)"></i>без связей — отдельная точка</span>')
    return "".join(items)


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
<title>TTC — карта сценариев</title><style>{CSS}{GRAPH_CSS}</style></head>
<body><div class="wrap">
<h1>Карта сценариев бота TTC</h1>
<div class="meta">Собрана из кода {esc(built)} · коммит {esc(commit)} ·
пересобрать: двойной клик по <code>карта-сценариев.bat</code> в корне проекта</div>
<div class="stats">{stats_html}</div>
<div class="controls">
  <div class="views">
    <button class="v on" data-view="graph">Схема</button>
    <button class="v" data-view="list">Список</button>
    <span class="zoom" id="zoombox">масштаб
      <button id="zout" title="Мельче">−</button><button id="zin" title="Крупнее">+</button></span>
  </div>
  <div class="filters">{"".join(filter_buttons)}</div>
  <input class="search" id="q" placeholder="Поиск по кнопкам и описаниям…">
</div>

<div id="graph-view">
<p class="legend">Выберите роль — и схема покажет ровно то, что видит человек с этой ролью.
Каждый прямоугольник — точка входа, стрелка — куда человек попадает следующим шагом.
<b>Наведите на прямоугольник</b>, чтобы прочитать подробности, и нажмите на него,
чтобы открыть эту точку в списке. Схема разбита на области: переходов между областями нет,
каждая живёт своей цепочкой.</p>
<div class="glegend">{_kind_legend()}</div>
<div id="graph-areas"></div>
</div>

<div id="list-view" class="hidden">
<p class="legend">Каждая карточка — одна точка входа: команда, кнопка меню, кнопка под сообщением
или сообщение внутри формы. «Дальше» — куда человек попадает следующим шагом, ссылка ведёт
к нужной карточке. Цветные метки: <span class="chip read">читает из базы</span>
<span class="chip write">пишет в базу</span> <span class="chip notify">кому уходит сообщение</span>.</p>
{"".join(areas_html)}
<section><h2 id="area-scenarios">Сообщения, которые бот шлёт сам</h2>
{_registry_html(spec.get("scenarios", []), "Каждое из этих сообщений правится прямо в боте: «🛠 Админство» → «🧩 Сценарии». Ссылка справа ведёт к моменту, когда человек его получает.")}</section>
<section><h2 id="area-slots">Блоки, которые правятся командой /content</h2>
{_registry_html(spec.get("slots", []), "Это тексты и файлы разделов. Меняются без программиста, изменение видно людям сразу.")}</section>
<section class="area"><h2 id="area-db">Что лежит в базе и откуда берётся</h2>{tables_html}</section>
</div>
</div>
<div id="gtip" class="gtip hidden"></div>
<script>const GRAPH={_graph_payload(spec, facts)};</script>
<script>{GRAPH_JS}{JS}</script></body></html>
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
    try:
        page = render_html(spec, facts)
    except SpecError as exc:
        print("Карта НЕ собрана — описание разошлось с кодом.\n")
        print(f"  {exc}\n")
        print("Что делать: поправьте docs/scenario-map.json под то, что сейчас")
        print("в коде, и запустите сборку снова. Полную сверку показывает")
        print("команда:  .venv\\Scripts\\python -m pytest tests/test_scenario_map.py")
        return 1
    OUT_PATH.write_text(page, encoding="utf-8")
    nodes = sum(len(area["nodes"]) for area in spec["areas"])
    print(f"Карта собрана: {OUT_PATH}")
    print(f"  точек входа: {nodes}, таблиц: {len(spec.get('tables', []))}")
    print(f"  из кода подтянуто: команд {len(facts.commands)}, кнопок {len(facts.buttons)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
