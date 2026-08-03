"""Markdown -> страница, с которой текст переносится в Telegraph.

Общая часть для всех статей проекта: инструкции участника и страниц обновления.
Раньше жила внутри build_user_guide.py; когда статей стало несколько, правила
разметки переехали сюда, чтобы не расходиться между копиями.

Почему вообще нужна страница-посредник. Telegraph не понимает Markdown:
вставленный в него текст с «решётками» и «звёздочками» останется текстом с
решётками и звёздочками, а таблицы пропадут совсем. Зато он отлично принимает
**оформленный текст, скопированный из браузера** — заголовки, списки и жирный
переносятся как оформление. Поэтому исходник остаётся один (Markdown, его
удобно править и дифать), а для переноса собирается веб-страница.

Разметка намеренно бедная: Telegraph оставляет только теги из своего списка,
всё остальное молча выбрасывает. Здесь используются только те, что он точно
принимает: h3, h4, p, b, i, code, a, ul, ol, li, blockquote, hr.
"""

from __future__ import annotations

import html
import re

_ITEM = re.compile(r"^(\s*)(?:[-*]|(\d+)\.)\s+(.*)$")


class TelegraphError(Exception):
    """Понятная ошибка вместо трассировки — файл читает не программист."""


def inline(text: str) -> str:
    """Разметка внутри строки: жирный, код, ссылки."""
    out = html.escape(text, quote=False)
    out = re.sub(r"`([^`]+)`", r"<code>\1</code>", out)
    out = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", out)
    out = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", r'<a href="\2">\1</a>', out)
    return out


def _paragraph(lines: list[str]) -> str:
    return " ".join(line.strip() for line in lines)


def _take_list(lines: list[str], start: int) -> tuple[list[str], bool, int]:
    """Собирает список целиком.

    Строка с продолжением (с отступом, но без своего маркера) прилипает к
    предыдущему пункту — в исходнике длинные пункты перенесены по ширине.
    Пустая строка заканчивает список.
    """
    items: list[str] = []
    numbered = bool(_ITEM.match(lines[start]).group(2))
    i = start
    while i < len(lines) and lines[i].strip():
        match = _ITEM.match(lines[i])
        if match:
            items.append(match.group(3).strip())
        elif items and lines[i].startswith((" ", "\t")):
            items[-1] += " " + lines[i].strip()
        else:
            break
        i += 1
    return items, numbered, i


def convert(body: str, source_name: str) -> str:
    """Markdown статьи -> HTML из тегов, которые понимает Telegraph.

    `source_name` подставляется в текст ошибки, чтобы человек понял, какой файл
    открывать: статей несколько, а конвертер один.
    """
    lines = body.splitlines()
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if not stripped:
            i += 1
            continue

        # Границы частей и прочие комментарии в статью не идут.
        if stripped.startswith("<!--"):
            while i < len(lines) and "-->" not in lines[i]:
                i += 1
            i += 1
            continue

        if set(stripped) == {"-"} and len(stripped) >= 3:
            out.append("<hr>")
            i += 1
            continue

        if stripped.startswith("#"):
            level = len(stripped) - len(stripped.lstrip("#"))
            text = stripped[level:].strip()
            # Telegraph знает всего два уровня заголовков: h3 и h4.
            out.append(f"<h4>{inline(text)}</h4>" if level >= 3 else f"<h3>{inline(text)}</h3>")
            i += 1
            continue

        if stripped.startswith(">"):
            quote: list[str] = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                quote.append(lines[i].strip().lstrip(">").strip())
                i += 1
            out.append(f"<blockquote>{inline(_paragraph(quote))}</blockquote>")
            continue

        if _ITEM.match(line):
            items, numbered, i = _take_list(lines, i)
            tag = "ol" if numbered else "ul"
            cells = "".join(f"<li>{inline(item)}</li>" for item in items)
            out.append(f"<{tag}>{cells}</{tag}>")
            continue

        if "|" in stripped and stripped.startswith("|"):
            raise TelegraphError(
                f"В {source_name} осталась таблица (строка {i + 1}):\n  {stripped}\n"
                "Telegraph таблицы не поддерживает — они пропадут при вставке. "
                "Перепишите её списком."
            )

        block: list[str] = []
        while i < len(lines) and lines[i].strip() and not lines[i].strip().startswith((">", "#")):
            if _ITEM.match(lines[i]) and block:
                break
            block.append(lines[i])
            i += 1
        out.append(f"<p>{inline(_paragraph(block))}</p>")

    return "\n".join(out)


_PAGE = """<!doctype html>
<meta charset="utf-8">
<title>{title} — текст для статьи</title>
<style>
  body {{ margin: 0; background: #f4f4f6; color: #1a1a1a;
         font: 17px/1.65 Georgia, "Times New Roman", serif; }}
  .bar {{ position: sticky; top: 0; z-index: 2; background: #24303f; color: #fff;
         padding: 14px 20px; font: 14px/1.5 -apple-system, "Segoe UI", sans-serif;
         user-select: none; -webkit-user-select: none; }}
  .bar b {{ color: #ffd479; }}
  .bar button {{ font: inherit; font-weight: 600; cursor: pointer; margin-top: 8px;
         background: #ffd479; color: #24303f; border: 0; border-radius: 6px;
         padding: 8px 16px; }}
  .bar button:active {{ transform: translateY(1px); }}
  .bar .ok {{ margin-left: 10px; color: #9be89b; }}
  main {{ max-width: 720px; margin: 28px auto 80px; padding: 36px 44px;
         background: #fff; border-radius: 10px; box-shadow: 0 1px 4px rgba(0,0,0,.12); }}
  h3 {{ font-size: 26px; margin: 34px 0 12px; line-height: 1.25; }}
  h4 {{ font-size: 20px; margin: 26px 0 10px; }}
  main > h3:first-child, main > p:first-child {{ margin-top: 0; }}
  p, li {{ margin: 12px 0; }}
  ul, ol {{ padding-left: 26px; }}
  blockquote {{ margin: 16px 0; padding: 2px 0 2px 18px; border-left: 3px solid #d8d8de;
         color: #444; font-style: italic; }}
  code {{ font: 15px/1.4 Consolas, monospace; background: #f0f0f3;
         padding: 1px 5px; border-radius: 4px; }}
  hr {{ border: 0; border-top: 1px solid #e2e2e8; margin: 30px 0; }}
</style>
<div class="bar">
  Это <b>не статья</b>, а текст для переноса в неё. Нажмите кнопку (или Ctrl+A, Ctrl+C
  внутри белого поля) и вставьте в telegra.ph — оформление перенесётся.
  Заголовок статьи там впишите отдельно: <b>{title}</b>.{extra}
  <br><button id="copy">Скопировать текст статьи</button><span class="ok" id="ok"></span>
</div>
<main id="article">
{article}
</main>
<script>
document.getElementById('copy').onclick = function () {{
  var range = document.createRange();
  range.selectNodeContents(document.getElementById('article'));
  var sel = window.getSelection();
  sel.removeAllRanges();
  sel.addRange(range);
  var ok = document.execCommand('copy');
  document.getElementById('ok').textContent = ok
    ? 'Скопировано — вставляйте в telegra.ph'
    : 'Не вышло: выделите текст вручную и скопируйте';
}};
</script>
"""


def page(title: str, article: str, extra: str = "") -> str:
    """Готовая страница: шапка с кнопкой «скопировать» и сам текст статьи."""
    return _PAGE.format(title=html.escape(title, quote=False), article=article, extra=extra)
