"""Сборка PDF «TTC — описание проекта» — короткого документа для партнёра.

Исходник документа — этот файл: текст лежит рядом с разметкой и правится здесь.
Готовый PDF в git не хранится (см. `.gitignore`), собирается командой:

    .venv/Scripts/python docs/partner/overview_pdf.py

Нужен `reportlab`; в зависимости бота он не входит — к работе бота сборка
документа отношения не имеет.

Что в документ не идёт: показатели сообщества и коммерческая часть, устройство
сервера, а также любые секреты — адреса, номера чатов, токены.
"""

# Текст документа набран разбитыми по строкам литералами — иначе абзац
# превращается в нечитаемую строку на пол-экрана. Правило про склейку строк
# внутри списков здесь мешает, а не помогает.
# ruff: noqa: ISC004

from __future__ import annotations

import sys
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

OUT = Path(__file__).with_name("TTC — описание проекта.pdf")
FONTS = Path("C:/Windows/Fonts")

INK = colors.HexColor("#1A1A1A")
NAVY = colors.HexColor("#1B3A57")
GREY = colors.HexColor("#5A5A5A")
RULE = colors.HexColor("#C8D2DA")
TINT = colors.HexColor("#F1F5F8")

PAGE_W, PAGE_H = A4
MARGIN = 2.1 * cm
WIDTH = PAGE_W - 2 * MARGIN

S: dict[str, ParagraphStyle] = {}


def register_fonts() -> None:
    """Встроенные шрифты reportlab кириллицу не содержат — берём системные."""
    faces = {
        "Body": "calibri.ttf",
        "Body-Bold": "calibrib.ttf",
        "Body-Italic": "calibrii.ttf",
        "Mono": "consola.ttf",
    }
    for name, file in faces.items():
        path = FONTS / file
        if not path.exists():
            sys.exit(f"Не найден шрифт {path} — без него кириллица не отрисуется.")
        pdfmetrics.registerFont(TTFont(name, str(path)))
    pdfmetrics.registerFontFamily(
        "Body", normal="Body", bold="Body-Bold", italic="Body-Italic", boldItalic="Body-Bold"
    )


def build_styles() -> None:
    S["title"] = ParagraphStyle(
        "title", fontName="Body-Bold", fontSize=20, leading=25, textColor=NAVY
    )
    S["subtitle"] = ParagraphStyle(
        "subtitle", fontName="Body", fontSize=11, leading=15, textColor=GREY
    )
    S["h1"] = ParagraphStyle(
        "h1", fontName="Body-Bold", fontSize=13, leading=17, textColor=NAVY,
        spaceBefore=16, spaceAfter=6, keepWithNext=1,
    )
    S["p"] = ParagraphStyle(
        "p", fontName="Body", fontSize=10.3, leading=15, textColor=INK,
        spaceAfter=6, allowWidows=0, allowOrphans=0,
    )
    S["li"] = ParagraphStyle("li", parent=S["p"], leftIndent=13, bulletIndent=2, spaceAfter=4)
    S["cell"] = ParagraphStyle("cell", fontName="Body", fontSize=9.6, leading=13, textColor=INK)
    S["cell-b"] = ParagraphStyle("cell-b", parent=S["cell"], fontName="Body-Bold")
    S["mono"] = ParagraphStyle(
        "mono", fontName="Mono", fontSize=8.8, leading=13, textColor=colors.HexColor("#22333B")
    )


def p(text: str, style: str = "p"):
    return Paragraph(text, S[style])


def ul(items: list[str]):
    return [Paragraph(t, S["li"], bulletText="•") for t in items]


def h1(text: str):
    return Paragraph(text, S["h1"])


def table(rows: list[list[str]], widths: list[float]):
    data = [[Paragraph(c, S["cell-b"] if i == 0 else S["cell"]) for i, c in enumerate(r)]
            for r in rows]
    t = Table(data, colWidths=widths, hAlign="LEFT")
    t.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.white, TINT]),
                ("LINEABOVE", (0, 0), (-1, 0), 0.6, NAVY),
                ("LINEBELOW", (0, -1), (-1, -1), 0.6, NAVY),
            ]
        )
    )
    return t


def mono(lines: list[str]):
    text = "<br/>".join(line.replace(" ", "&nbsp;") for line in lines)
    return Table(
        [[Paragraph(text, S["mono"])]],
        colWidths=[WIDTH],
        style=TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), TINT),
                ("BOX", (0, 0), (-1, -1), 0.5, RULE),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ]
        ),
        hAlign="LEFT",
    )


class Doc(BaseDocTemplate):
    def __init__(self, path: str) -> None:
        super().__init__(
            path,
            pagesize=A4,
            title="TTC — описание проекта",
            author="Проект TTC",
            subject="Суть, логика работы и технологии проекта",
            leftMargin=MARGIN,
            rightMargin=MARGIN,
            topMargin=MARGIN,
            bottomMargin=1.8 * cm,
        )
        frame = Frame(MARGIN, 1.8 * cm, WIDTH, PAGE_H - MARGIN - 1.8 * cm, id="main")
        self.addPageTemplates([PageTemplate(id="body", frames=[frame], onPage=self.footer)])

    def footer(self, canvas, doc) -> None:
        canvas.saveState()
        canvas.setStrokeColor(RULE)
        canvas.setLineWidth(0.4)
        canvas.line(MARGIN, 1.25 * cm + 9, PAGE_W - MARGIN, 1.25 * cm + 9)
        canvas.setFont("Body", 8.4)
        canvas.setFillColor(GREY)
        canvas.drawString(MARGIN, 1.25 * cm, "TTC — описание проекта")
        canvas.drawRightString(PAGE_W - MARGIN, 1.25 * cm, str(doc.page))
        canvas.restoreState()


def story() -> list:
    rule = Table(
        [[""]],
        colWidths=[WIDTH],
        rowHeights=[2],
        style=TableStyle([("BACKGROUND", (0, 0), (-1, -1), NAVY)]),
        hAlign="LEFT",
    )
    s: list = [
        p("TTC — Telegram-экосистема студенческого сообщества", "title"),
        Spacer(1, 4),
        p("Суть проекта, логика работы, технологии", "subtitle"),
        Spacer(1, 8),
        rule,
        h1("Суть"),
        p(
            "Закрытое студенческое сообщество, которое целиком живёт в Telegram и управляется "
            "ботом. Бот — привратник и администратор: ведёт анкету вступления, отдаёт заявки "
            "админам на решение, выдаёт одноразовые приглашения в группу, держит порядок в "
            "темах, раздаёт роли и права, публикует афишу и голосования."
        ),
        p(
            "Попасть в группу иначе как по персональной ссылке от бота нельзя: ссылка живёт "
            "15 минут и работает на одно вступление. Для человека всё это выглядит как "
            "переписка с ботом. Внутри — обычное приложение с собственной базой: Telegram "
            "только доставляет сообщения, данные и правила живут на нашей стороне."
        ),
    ]

    s += [
        h1("Как это работает логически"),
        p("<b>Путь человека.</b>"),
        mono(
            [
                "Старт  →  анкета: имя, вуз, группа, дата рождения",
                "       →  карточка заявки админам",
                "       →  решение человека (или автоприём по правилам)",
                "       →  одноразовая ссылка в группу",
            ]
        ),
        Spacer(1, 8),
        p("<b>Путь любого действия внутри бота.</b>"),
        mono(
            [
                "Событие  →  кто это и какие у него права  →  не забанен ли",
                "         →  нужный обработчик  →  правило в сервисе",
                "         →  запись в базу  →  ответ человеку",
            ]
        ),
        Spacer(1, 8),
        p(
            "Код разделён на три слоя: <b>роутеры</b> понимают, что пришло, <b>сервисы</b> "
            "держат правила проекта, <b>репозитории</b> работают с базой. Благодаря этому "
            "правило живёт в одном месте и срабатывает одинаково, откуда бы действие ни "
            "пришло — из карточки в чате, из админской панели или из прямого редактирования "
            "базы."
        ),
        p(
            "Незаконченные анкеты хранятся в быстрой памяти: перезапуск не сбрасывает "
            "человека в начало формы. Кнопки несут в себе номер заявки, поэтому кнопка в "
            "карточке недельной давности работает так же, как свежая."
        ),
    ]

    s += [
        h1("Технологии"),
        p("Стек обычный для такого класса задач, без экзотики:"),
        table(
            [
                ["Python 3.12 + aiogram 3", "Язык и асинхронный фреймворк для Telegram-ботов"],
                [
                    "PostgreSQL 16 + pg_trgm",
                    "База как единственный источник правды; поиск, прощающий опечатки "
                    "(«политех» находит «Политехнический университет»)",
                ],
                ["SQLAlchemy 2 + asyncpg", "Описание таблиц и асинхронные запросы"],
                [
                    "Alembic",
                    "Версии структуры базы: при обновлении кода база подтягивается сама, "
                    "руками в неё лезть не нужно",
                ],
                ["Redis", "Шаги незаконченных форм"],
                ["Docker Compose", "Весь стек поднимается одной командой"],
                ["pytest, ruff", "Автотесты и статическая проверка кода"],
            ],
            [0.29 * WIDTH, 0.71 * WIDTH],
        ),
    ]

    s += [
        h1("Админская система"),
        p(
            "Сильная сторона проекта: сообществом управляют из самого бота, с телефона, без "
            "программиста."
        ),
        *ul(
            [
                "<b>Пять уровней ролей:</b> владелец → суперадмин → админ → организатор → "
                "участник (отдельно «кастом» и «забанен»). Роль организатора бот выдаёт и "
                "снимает сам — по тому, есть ли у человека активные мероприятия.",
                "<b>Шесть независимых модулей прав:</b> заявки на вступление, вузы, тексты "
                "бота, бан, мероприятия и голосования, репорты. Модули выдаются человеку "
                "лично или через именованную группу прав, итог — объединение. Так собирается "
                "«модератор, который банит, но не разбирает заявки».",
                "<b>Права проверяются дважды:</b> на входе («эта кнопка вообще для тебя?») и "
                "в самом правиле («а можешь ли ты это именно с ним?» — суперадмин банит "
                "админа, но не другого суперадмина).",
                "<b>Без разработчика меняются:</b> тексты и картинки бота, его "
                "сообщения-реакции, роли и права, записи в базе (прямой редактор с разбором "
                "связей перед удалением), рассылка объявлений участникам.",
                "<b>Всё действие админа — строка в журнале:</b> кто, кого, когда и на каком "
                "основании. Журнал только пополняется и никогда не правится, поэтому на "
                "вопрос «кто это сделал» всегда есть ответ.",
            ]
        ),
    ]

    s += [
        h1("Масштабирование"),
        p("Система рассчитана на рост сообщества и команды админов."),
        *ul(
            [
                "<b>Очередь заявок вместо чата.</b> Админ разбирает неразобранное прямо из "
                "базы: карточка в чате может устареть или не дойти, очередь от сообщений не "
                "зависит. Каждый видит только те виды заявок, которые открыты его правами.",
                "<b>Автоприём по правилам.</b> Заявки, в которых нечего решать, проходят "
                "сами — но всё равно показываются админам, с пометкой. Правила живут в коде, "
                "а не в наборе галочек, поэтому всегда понятно, по каким основаниям кого "
                "впустили.",
                "<b>Команда растёт без переделки кода.</b> Новый админ получает набор "
                "модулей или группу прав — и видит ровно свою часть работы.",
                "<b>Именные ссылки-приглашения.</b> Видно, кто сколько людей привёл: открыли "
                "бота, подали анкету, приняты. Счёт защищён от накрутки — считается человек, "
                "а не нажатие, он закрепляется за первой ссылкой, свой переход хозяину не "
                "засчитывается.",
                "<b>Наплыв не ломает процесс.</b> Ограничения Telegram учтены в коде: отказ "
                "по частоте не считается ошибкой — бот ждёт и повторяет, а заявка живёт в "
                "базе независимо от того, дошла ли карточка. На расчёте в тысячу регистраций "
                "разом узким местом оказывается сама платформа и скорость разбора, а не код "
                "и не нагрузка.",
            ]
        ),
    ]

    s += [
        h1("Как всё проверяется"),
        *ul(
            [
                "<b>478 автотестов</b>, прогон меньше минуты, живая база не нужна. Проверяются "
                "не только функции, но и неочевидные свойства: порядок обработчиков, правила "
                "удаления связанных записей, честность счётчика приглашений.",
                "<b>Карта сценариев — 318 точек входа:</b> каждая команда, кнопка и шаг формы "
                "с описанием, кому доступна, что делает и что человек увидит. Собирается "
                "прямо из кода, а отдельный тест сверяет её с кодом в обе стороны — "
                "появилась кнопка без описания или осталось описание несуществующей, сборка "
                "падает. Поэтому карта не может тихо устареть.",
                "<b>Выпуск по регламенту:</b> накопленные изменения выходят одним разом, с "
                "двумя статьями — участникам и админам, — после полного прогона тестов и "
                "проверки кода.",
                "<b>Сбои видны сразу:</b> техническая ошибка пишется в журнал и приходит "
                "владельцу карточкой в личные сообщения, а человек вместо молчания бота "
                "получает понятное объяснение и просьбу повторить действие.",
            ]
        ),
    ]
    return s


def build() -> None:
    register_fonts()
    build_styles()
    Doc(str(OUT)).build(story())
    print(f"Готово: {OUT}")


if __name__ == "__main__":
    build()
