"""PDF Report Generator for LWdataBot.

Generates professional contractor verification reports in Ukrainian.
Uses fpdf2 with DejaVu Sans for full Cyrillic support.

Installation:
    pip install fpdf2
    # Ubuntu/Debian: sudo apt install fonts-dejavu-core
    # macOS: brew install --cask font-dejavu
    # Or place DejaVuSans.ttf + DejaVuSans-Bold.ttf into src/services/fonts/
"""

from __future__ import annotations

import asyncio
import re as _re
from datetime import datetime
from pathlib import Path

from fpdf import FPDF


# ── Color palette (black + gold + white/gray) ────────────────────────────────

_BLACK = (22, 22, 22)
_DARK = (50, 50, 50)
_LIGHT_BG = (245, 245, 242)
_GREEN = (30, 130, 50)
_RED = (195, 40, 40)
_BLUE = (40, 100, 180)
_ORANGE = (210, 120, 20)
_TEXT = (40, 40, 40)
_GRAY = (130, 130, 130)
_WHITE = (255, 255, 255)
_LINE = (200, 200, 195)
_GOLD = (207, 171, 59)

# Card background tints (very light versions for factor cards)
_CARD_GRAY_BG = (242, 242, 240)
_CARD_ORANGE_BG = (255, 243, 224)
_CARD_RED_BG = (255, 232, 230)

# ── Assets ────────────────────────────────────────────────────────────────────

_ASSETS_DIR = Path(__file__).parent / "assets"
_LOGO_PATH = _ASSETS_DIR / "logo.jpg"

# ── Rendering configuration ───────────────────────────────────────────────────
#
# All section / field mapping is declarative.  To support a new API response
# structure, add keys here — no renderer code changes needed.
# ─────────────────────────────────────────────────────────────────────────────

# Ukrainian labels for known JSON keys  (key → display label)
_LABELS: dict[str, str] = {
    # identity
    "pib": "ПІБ",
    "fullName": "ПІБ",
    "shortName": "Скорочена назва",
    "name": "Назва",
    "code": "ІПН / ЄДРПОУ",
    "edrpou": "ЄДРПОУ",
    "birthDate": "Дата народження",
    "sex": "Стать",
    "status": "Статус",
    "director": "Керівник",
    "registrationDate": "Дата реєстрації",
    "registrationNumber": "Номер реєстрації",
    "correctINN": "ІПН валідний",
    # contacts
    "email": "Email",
    "phones": "Телефон",
    "phone": "Телефон",
    "fax": "Факс",
    "location": "Адреса",
    "primaryActivity": "Основна діяльність",
    # company
    "shortName": "Скорочена назва",
    "capital": "Статутний капітал",
    "ceoName": "Керівник",
    "role": "Посада",
    "restriction": "Обмеження",
    "amountPercent": "Частка, %",
    "amount": "Сума, грн",
    "management": "Орган управління",
    "fullNameEn": "Назва (англ.)",
    "lastTime": "Останнє оновлення",
    # beneficiaries extra
    "beneficiaryName": "Бенефіціар (ПІБ)",
    "interest": "Частка контролю, %",
    "city": "Місто",
    # financial extra
    "expenses": "Витрати",
    "nonCurrentAssets": "Необоротні активи",
    "currentAssets": "Оборотні активи",
    "liability": "Зобов'язання",
    "balance": "Баланс",
    "buhgalter": "Бухгалтер",
    "sector": "Сектор",
    # licenses
    "energyLicenses": "Енергетичні ліцензії",
    # financial
    "year": "Рік",
    "revenue": "Дохід",
    "profit": "Прибуток",
    "assets": "Активи",
    "equity": "Капітал",
    "employees": "Працівників",
    # tax / factors
    "group": "Група",
    "rate": "Ставка",
    "dateStart": "Дата початку",
    "text": "Опис",
    "type": "Тип",
    # registry items
    "count": "Записів",
    # activities
    "isPrimary": "Основний",
    # registrations
    "description": "Опис",
    "startDate": "Дата",
    "startNum": "Номер",
    # passport
    "number": "Номер",
    "passport": "Номер паспорта",
    "stolen": "Викрадений",
    "invalid": "Недійсний",
    "propertyStruct": "Структура власності",
    "_treasury_role": "Казначейство (роль)",
    "_treasury_total_payee": "Отримано з бюджету",
    "_treasury_total_payer": "Сплачено до бюджету",
    "_treasury_total_txn": "Транзакцій всього",
    "_persons_total": "Пов'язані особи",
    "_fin_period": "Звітний період (Clarity)",
    "_fin_accountant": "Бухгалтер (Clarity)",
    "_fin_personnel": "Працівників (Clarity)",
    "_fin_report_date": "Дата подання звіту",
    "prevRegistrationEndTerm": "Попередня реєстрація",
    "foundingDocumentType": "Установчий документ",
    "executivePower": "Орган управління",
    "objectName": "Об'єкт",
    "authorisedCapital": "Стат. капітал (зареєстр.)",
    "primaryActivityKind": "Вид діяльності",
}

# Section titles for known container / list keys
_SECTION_TITLES: dict[str, str] = {
    "registry": "Реєстраційні дані",
    "activities": "Види діяльності (КВЕД)",
    "registrations": "Реєстрації",
    "factors": "Фактори та сигнали ризику",
    "items": "Перевірка по реєстрах",
    "heads": "Керівництво",
    "beneficiaries": "Бенефіціарні власники",
    "financialStatement": "Фінансова звітність",
    "assignees": "Правонаступники",
    "predecessors": "Правопопередники",
    "licenses": "Ліцензії",
    "treasury_by_year": "Платежі Казначейства (по роках)",
    "bank_accounts": "Банківські рахунки (Казначейство)",
    "clarity_finances": "Фінансова звітність (Clarity, деталі)",
    "clarity_licenses": "Ліцензії (Clarity)",
    "clarity_persons": "Пов'язані особи (Clarity)",
    "clarity_used_vehicles": "Автотранспорт у користуванні (Clarity)",
    "clarity_owned_vehicles": "Автотранспорт у власності (Clarity)",
}

# Ordered groups — scalar fields rendered under these section titles
_FIELD_GROUPS: list[tuple[str, list[str]]] = [
    ("Загальна інформація", [
        "fullName", "name", "shortName", "fullNameEn",
        "code", "edrpou",
        "correctINN", "birthDate", "sex",
        "status", "registrationDate", "registrationNumber",
        "director", "ceoName", "capital", "management",
    ]),
    ("Контактні дані", [
        "email", "phones", "phone", "fax",
        "location", "primaryActivity",
    ]),
    ("Казначейство (зведення)", [
        "_treasury_role", "_treasury_total_payee",
        "_treasury_total_payer", "_treasury_total_txn",
    ]),
    ("Clarity: додаткові дані", [
        "_persons_total",
        "_fin_period", "_fin_accountant", "_fin_personnel", "_fin_report_date",
    ]),
]

# Fields that receive status coloring (green / red)
_STATUS_FIELDS = frozenset({"status", "correctINN", "stolen", "invalid"})

# Fields to hide from output
_SKIP_FIELDS = frozenset({
    "address", "statusService", "formattedPhones", "state",
    "lastDate", "lastTime", "objectName", "innHash", "country",
    "registration", "authorisedCapital", "link",
    "icon", "indicator", "factorGroup", "databaseDate",
    "pdvCode",
    # OLF / technical
    "olfCode", "olfName", "olfSubtype", "includeOlf",
    "foundingDocumentType", "primaryActivityKind",
    "executivePower", "forDevelopers",
    "person",
})

# Positive-status keywords (lowercase)
_POS = frozenset({"active", "зареєстровано", "так"})

# Value translation maps
_SEX_UA: dict[str, str] = {"male": "Чоловіча", "female": "Жіноча"}

_REGISTRY_UA: dict[str, str] = {
    "fop": "ФОП",
    "drorm": "Нерухомість (ДРОРМ)",
    "realty": "Нерухомість (ДРРП)",
    "penalty": "Штрафи",
    "bankruptcy": "Банкрутство",
    "sanction": "Санкції",
    "rnboSanction": "Санкції РНБО",
}

# Registries where count>0 is NEGATIVE (risk)
_NEGATIVE_REGISTRIES = frozenset({"penalty", "bankruptcy", "sanction", "rnboSanction"})
# Registries where count is just informational (not good/bad)
_INFO_REGISTRIES = frozenset({"fop", "drorm", "realty"})

_REG_TYPE_UA: dict[str, str] = {
    "statistic": "Статистика",
    "taxoffice": "Податкова",
    "singletax": "Єдиний внесок",
}

# Known table layouts: key → {hdrs, cols, widths, scol}
_TABLE_CFG: dict[str, dict] = {
    "activities": dict(
        hdrs=["Код", "Назва", "Основний"],
        cols=["code", "name", "isPrimary"],
        widths=[20, 135, 25],
        scol=2,
    ),
    "registrations": dict(
        hdrs=["Орган", "Тип", "Дата", "Номер"],
        cols=["name", "_desc", "startDate", "startNum"],
        widths=[75, 40, 25, 40],
        scol=None,
    ),
    "items": dict(
        hdrs=["Реєстр", "Статус", "Записів"],
        cols=["_type_ua", "_status_display", "count"],
        widths=[60, 70, 50],
        scol=1,
    ),
    # factors — rendered as cards, NOT a table (see _render_factors)
    "heads": dict(
        hdrs=["ПІБ", "Посада", "Обмеження"],
        cols=["name", "role", "restriction"],
        widths=[65, 60, 55],
        scol=None,
    ),
    "beneficiaries": dict(
        hdrs=["Назва / Бенефіціар", "Роль", "%", "Сума, грн", "Країна"],
        cols=["_benef_name", "role", "amountPercent", "_amount_fmt", "country"],
        widths=[60, 45, 15, 35, 25],
        scol=None,
    ),
    "financialStatement": dict(
        hdrs=["Рік", "Дохід", "Витрати", "Прибуток", "Баланс", "Прац."],
        cols=["year", "_revenue_fmt", "_expenses_fmt", "_profit_fmt", "_balance_fmt", "employees"],
        widths=[20, 33, 33, 33, 33, 28],
        scol=None,
    ),
    "assignees": dict(
        hdrs=["ЄДРПОУ", "Назва"],
        cols=["code", "name"],
        widths=[30, 150],
        scol=None,
    ),
    "predecessors": dict(
        hdrs=["ЄДРПОУ", "Назва"],
        cols=["code", "name"],
        widths=[30, 150],
        scol=None,
    ),
    "treasury_by_year": dict(
        hdrs=["Рік", "Отримано, грн", "К-сть", "Сплачено, грн", "К-сть"],
        cols=["year", "_payee_fmt", "payee_count", "_payer_fmt", "payer_count"],
        widths=[20, 50, 25, 50, 25],
        scol=None,
    ),
    "bank_accounts": dict(
        hdrs=["Рахунок", "МФО", "Оновлено"],
        cols=["account", "mfo", "updated"],
        widths=[80, 40, 60],
        scol=None,
    ),
    "clarity_finances": dict(
        hdrs=["Форма", "Код", "Стаття", "Значення"],
        cols=["form", "code", "title", "_value_fmt"],
        widths=[45, 25, 75, 35],
        scol=None,
    ),
    "clarity_licenses": dict(
        hdrs=["Реєстр", "Діяльність", "Орган", "Початок", "Закінчення"],
        cols=["registry", "activity", "authority", "_date_start_fmt", "_date_end_fmt"],
        widths=[40, 50, 40, 25, 25],
        scol=None,
    ),
    "clarity_persons": dict(
        hdrs=["ПІБ", "Тип", "Актуальний", "Джерело"],
        cols=["name", "type", "actual", "source"],
        widths=[55, 40, 25, 60],
        scol=2,
    ),
    "clarity_used_vehicles": dict(
        hdrs=["Тип", "Модель", "Номер", "Рік", "Статус"],
        cols=["type", "model", "num", "year", "status"],
        widths=[30, 55, 35, 20, 40],
        scol=4,
    ),
    "clarity_owned_vehicles": dict(
        hdrs=["Марка", "Модель", "Рік", "Тип", "Колір", "Паливо"],
        cols=["brand", "model", "year", "kind", "color", "fuel"],
        widths=[30, 40, 20, 30, 25, 35],
        scol=None,
    ),
}


# ── Font discovery ────────────────────────────────────────────────────────────

_FONT_DIRS = [
    Path(__file__).parent / "fonts",
    Path("/usr/share/fonts/truetype/dejavu"),
    Path("/usr/share/fonts/TTF"),
    Path.home() / ".fonts",
    Path.home() / "Library" / "Fonts",
]


def _font_dir() -> Path:
    for d in _FONT_DIRS:
        if (d / "DejaVuSans.ttf").is_file():
            return d
    raise FileNotFoundError(
        "DejaVuSans.ttf not found. Install DejaVu fonts:\n"
        "  Ubuntu/Debian : sudo apt install fonts-dejavu-core\n"
        "  macOS         : brew install --cask font-dejavu\n"
        "  Manual        : place DejaVuSans.ttf & DejaVuSans-Bold.ttf into\n"
        f"                  {Path(__file__).parent / 'fonts'}"
    )


# ── PDF class ─────────────────────────────────────────────────────────────────

class _ReportPDF(FPDF):
    """Corporate-styled PDF for contractor verification reports."""

    def __init__(self) -> None:
        super().__init__("P", "mm", "A4")
        self._ts = datetime.now().strftime("%d.%m.%Y %H:%M")
        self._sec = 0

        fd = _font_dir()
        self.add_font("DV", "", str(fd / "DejaVuSans.ttf"))
        self.add_font("DV", "B", str(fd / "DejaVuSans-Bold.ttf"))

        self.set_auto_page_break(True, 20)
        self.set_margins(15, 15, 15)
        self.add_page()

    @property
    def pw(self) -> float:
        """Printable width (page minus margins)."""
        return self.w - self.l_margin - self.r_margin

    # ── page footer ───────────────────────────────────────────────────────

    def footer(self) -> None:
        self.set_y(-15)
        self.set_draw_color(*_GOLD)
        self.set_line_width(0.3)
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
        self.set_y(-12.5)
        self.set_font("DV", "B", 7)
        self.set_text_color(*_BLACK)
        self.cell(
            self.pw / 2, 4,
            f"LWdataBot  \u2022  {self._ts}",
            align="L",
        )
        self.set_font("DV", "", 7)
        self.set_text_color(*_GRAY)
        self.cell(
            self.pw / 2, 4,
            f"\u0421\u0442\u043e\u0440\u0456\u043d\u043a\u0430 {self.page_no()}/{{nb}}",
            align="R",
        )

    # ── banner at top of first page ──────────────────────────────────────

    def banner(self, title: str, code: str) -> None:
        banner_h = 42

        # solid black background
        self.set_fill_color(*_BLACK)
        self.rect(0, 0, self.w, banner_h, "F")

        # gold accent line at bottom
        self.set_fill_color(*_GOLD)
        self.rect(0, banner_h, self.w, 0.6, "F")

        # ── logo (square, blends with black bg) ──
        logo_size = 28
        logo_x = self.l_margin + 3
        logo_y = (banner_h - logo_size) / 2
        if _LOGO_PATH.is_file():
            self.image(
                str(_LOGO_PATH), logo_x, logo_y,
                logo_size, logo_size,
            )

        # ── text block ──
        text_x = logo_x + logo_size + 10
        text_w = self.w - text_x - self.r_margin

        # brand name
        self.set_xy(text_x, logo_y + 1)
        self.set_font("DV", "B", 9)
        self.set_text_color(*_GOLD)
        self.cell(text_w, 5, "LWdataBot", align="L")

        # main title
        self.set_xy(text_x, logo_y + 8)
        self.set_font("DV", "B", 14)
        self.set_text_color(*_WHITE)
        self.cell(text_w, 8, title, align="L")

        # subtitle: IPN + date
        self.set_xy(text_x, logo_y + 19)
        self.set_font("DV", "", 8.5)
        self.set_text_color(150, 150, 150)
        self.cell(
            text_w, 6,
            f"\u0406\u041f\u041d / \u0404\u0414\u0420\u041f\u041e\u0423: {code}"
            f"    \u2022    {self._ts}",
            align="L",
        )

        self.set_y(banner_h + 4)
        self.set_text_color(*_TEXT)

    # ── numbered section header ───────────────────────────────────────────

    def section(self, title: str) -> None:
        self._sec += 1
        if self.get_y() > self.h - 35:
            self.add_page()
        self.ln(3)
        self.set_fill_color(*_BLACK)
        self.set_font("DV", "B", 10)
        self.set_text_color(*_WHITE)
        self.cell(
            self.pw, 8, f"  {self._sec}. {title}",
            fill=True, new_x="LMARGIN", new_y="NEXT",
        )
        self.ln(3)
        self.set_text_color(*_TEXT)

    # ── key-value row ─────────────────────────────────────────────────────

    def kv(self, label: str, value: str, color: str | None = None) -> None:
        lw = 55
        self.set_font("DV", "B", 9)
        # Expand label width if text doesn't fit
        label_w = self.get_string_width(label) + 4
        if label_w > lw:
            lw = min(label_w, self.pw * 0.5)
        self.set_text_color(*_GRAY)
        self.cell(lw, 6, label)
        self.set_font("DV", "", 9)
        if color == "g":
            self.set_text_color(*_GREEN)
        elif color == "r":
            self.set_text_color(*_RED)
        else:
            self.set_text_color(*_TEXT)
        self.multi_cell(self.pw - lw, 6, value, new_x="LMARGIN", new_y="NEXT")
        self.set_text_color(*_TEXT)

    # ── table with header + alternating rows ──────────────────────────────

    def add_table(
        self,
        hdrs: list[str],
        rows: list[list[str]],
        widths: list[float] | None = None,
        scol: int | None = None,
    ) -> None:
        n = len(hdrs)
        ws = widths or [self.pw / n] * n
        lh = 5.0
        pad = 1.5

        def _rh(cells: list[str]) -> float:
            mx = 1
            self.set_font("DV", "", 8)
            for i, t in enumerate(cells):
                avail = ws[i] - 3
                if avail <= 0:
                    continue
                sw = self.get_string_width(t) + 2
                lines = max(1, int(sw / avail) + (1 if sw % avail > 0 else 0))
                mx = max(mx, lines)
            return mx * lh + pad * 2

        def _draw(cells: list[str], hdr: bool, alt: bool) -> None:
            y0 = self.get_y()
            rh = _rh(cells)
            if y0 + rh > self.h - 22:
                self.add_page()
                y0 = self.get_y()

            # background
            if hdr:
                self.set_fill_color(*_DARK)
            elif alt:
                self.set_fill_color(*_LIGHT_BG)
            else:
                self.set_fill_color(*_WHITE)
            self.rect(self.l_margin, y0, self.pw, rh, "F")

            # cell text
            for i, t in enumerate(cells):
                x = self.l_margin + sum(ws[:i])
                self.set_xy(x, y0 + pad)
                if hdr:
                    self.set_font("DV", "B", 8)
                    self.set_text_color(*_WHITE)
                else:
                    self.set_font("DV", "", 8)
                    self._status_color(t, i, scol)
                self.multi_cell(ws[i], lh, f" {t}", align="L")

            self.set_y(y0 + rh)

        _draw(hdrs, True, False)
        for idx, r in enumerate(rows):
            _draw(r, False, idx % 2 == 0)
        self.ln(3)
        self.set_text_color(*_TEXT)

    def _status_color(self, txt: str, col: int, scol: int | None) -> None:
        if scol is not None and col == scol:
            lo = txt.lower()
            # Explicit positive markers
            if any(k in lo for k in ("\u2713", "чисто", "активн", "так")):
                self.set_text_color(*_GREEN)
                return
            # Explicit negative markers (only with ✗ prefix)
            if any(k in lo for k in ("\u2717", "недійсн", "викрад")):
                self.set_text_color(*_RED)
                return
            # Informational "Знайдено" without ✗ → blue (neutral)
            if "знайдено" in lo and "\u2717" not in txt:
                self.set_text_color(*_BLUE)
                return
            # FOP status "зареєстровано" without ✓ prefix → blue
            if "зареєстр" in lo:
                self.set_text_color(*_BLUE)
                return
        self.set_text_color(*_TEXT)

    # ── factor risk card ─────────────────────────────────────────────────

    def _measure_text_h(self, text: str, width: float, lh: float) -> float:
        """Calculate height of text rendered via multi_cell using dry_run."""
        if not text:
            return lh
        result = self.multi_cell(width, lh, text, dry_run=True, output="LINES")
        return max(1, len(result)) * lh

    def factor_card(
        self,
        title: str,
        lines: list[str],
        severity: str = "info",
    ) -> None:
        """Render a colored card block for a risk factor.

        severity: 'info' (gray), 'warning' (orange), 'danger' (red)
        """
        accent = {"info": _GRAY, "warning": _ORANGE, "danger": _RED}[severity]
        bg = {"info": _CARD_GRAY_BG, "warning": _CARD_ORANGE_BG, "danger": _CARD_RED_BG}[severity]
        bar_w = 3.0
        pad_x = 5.0
        pad_y = 3.0
        lh = 5.0
        content_w = self.pw - bar_w - pad_x * 2

        # pre-calculate height (properly account for \n in text)
        self.set_font("DV", "B", 8.5)
        title_h = self._measure_text_h(title, content_w, lh)

        self.set_font("DV", "", 8)
        body_h = 0.0
        for ln in lines:
            body_h += self._measure_text_h(ln, content_w, lh)

        card_h = pad_y + title_h + 1.5 + body_h + pad_y
        page_avail = self.h - 22

        # If card is taller than a full page, cap it and let it flow
        max_card = page_avail - 15
        if card_h > max_card:
            card_h = max_card

        # page break check
        if self.get_y() + card_h + 3 > page_avail:
            self.add_page()

        y0 = self.get_y()
        x0 = self.l_margin

        # background fill
        self.set_fill_color(*bg)
        self.rect(x0, y0, self.pw, card_h, "F")

        # left accent bar
        self.set_fill_color(*accent)
        self.rect(x0, y0, bar_w, card_h, "F")

        # title
        tx = x0 + bar_w + pad_x
        self.set_xy(tx, y0 + pad_y)
        self.set_font("DV", "B", 8.5)
        self.set_text_color(*_BLACK)
        self.multi_cell(content_w, lh, title, new_x="LMARGIN", new_y="NEXT")

        # body lines
        cy = self.get_y() + 1.0
        self.set_font("DV", "", 8)
        self.set_text_color(*_DARK)
        for ln in lines:
            # Page break within card if needed
            if cy + lh > page_avail:
                self.add_page()
                cy = self.get_y()
                # Draw background continuation on new page
                self.set_fill_color(*bg)
                remain_h = min(body_h, max_card)
                self.rect(self.l_margin, cy, self.pw, remain_h, "F")
                self.set_fill_color(*accent)
                self.rect(self.l_margin, cy, bar_w, remain_h, "F")
            self.set_xy(tx, cy)
            self.multi_cell(content_w, lh, ln, new_x="LMARGIN", new_y="NEXT")
            cy = self.get_y()

        self.set_y(cy + pad_y + 2.5)
        self.set_text_color(*_TEXT)

    def history_card(
        self,
        title: str,
        blocks: list[list[str]],
    ) -> None:
        """Render history factor as a card with alternating-bg date blocks.

        blocks: list of date-blocks; each block is a list of text lines
                (first line = date header, rest = change details).
        """
        accent = _GRAY
        bar_w = 3.0
        pad_x = 5.0
        pad_y = 3.0
        lh = 5.0
        content_w = self.pw - bar_w - pad_x * 2
        bg_even = _CARD_GRAY_BG          # (242, 242, 240)
        bg_odd = (250, 250, 248)          # slightly lighter

        # --- Title section ---
        self.set_font("DV", "B", 8.5)
        title_h = self._measure_text_h(title, content_w, lh)
        title_block_h = pad_y + title_h + pad_y

        page_avail = self.h - 22
        if self.get_y() + title_block_h + 30 > page_avail:
            self.add_page()

        y0 = self.get_y()
        x0 = self.l_margin
        tx = x0 + bar_w + pad_x

        # title bg
        self.set_fill_color(*_CARD_GRAY_BG)
        self.rect(x0, y0, self.pw, title_block_h, "F")
        self.set_fill_color(*accent)
        self.rect(x0, y0, bar_w, title_block_h, "F")

        self.set_xy(tx, y0 + pad_y)
        self.set_text_color(*_BLACK)
        self.multi_cell(content_w, lh, title, new_x="LMARGIN", new_y="NEXT")
        cy = y0 + title_block_h

        # --- Date blocks with alternating backgrounds ---
        self.set_font("DV", "", 8)
        for idx, block_lines in enumerate(blocks):
            bg = bg_even if idx % 2 == 0 else bg_odd

            # Measure block height
            self.set_font("DV", "B", 8)
            date_h = self._measure_text_h(block_lines[0], content_w, lh) if block_lines else 0
            self.set_font("DV", "", 8)
            body_h = sum(self._measure_text_h(ln, content_w, lh) for ln in block_lines[1:])
            block_h = pad_y * 0.5 + date_h + body_h + pad_y * 0.5

            # Page break if needed
            if cy + block_h + 3 > page_avail:
                self.add_page()
                cy = self.get_y()

            # Block background
            self.set_fill_color(*bg)
            self.rect(x0 + bar_w, cy, self.pw - bar_w, block_h, "F")
            # Continue accent bar
            self.set_fill_color(*accent)
            self.rect(x0, cy, bar_w, block_h, "F")

            by = cy + pad_y * 0.5

            # Date header (bold)
            if block_lines:
                self.set_font("DV", "B", 8)
                self.set_text_color(*_BLACK)
                self.set_xy(tx, by)
                self.multi_cell(content_w, lh, block_lines[0], new_x="LMARGIN", new_y="NEXT")
                by = self.get_y()

            # Change details
            self.set_font("DV", "", 8)
            self.set_text_color(*_DARK)
            for ln in block_lines[1:]:
                if by + lh > page_avail:
                    self.add_page()
                    by = self.get_y()
                self.set_xy(tx, by)
                self.multi_cell(content_w, lh, ln, new_x="LMARGIN", new_y="NEXT")
                by = self.get_y()

            cy = by + pad_y * 0.5

        self.set_y(cy + 2.5)
        self.set_text_color(*_TEXT)

    # ── thin separator line ───────────────────────────────────────────────

    def separator(self) -> None:
        self.ln(2)
        self.set_draw_color(*_LINE)
        y = self.get_y()
        self.line(self.l_margin + 10, y, self.w - self.r_margin - 10, y)
        self.ln(4)


# ── Value helpers ─────────────────────────────────────────────────────────────


def _humanize(key: str) -> str:
    """Convert camelCase / snake_case key to a readable label."""
    s = _re.sub(r"([a-z])([A-Z])", r"\1 \2", key)
    return s.replace("_", " ").capitalize()


def _fmt(key: str, value: object) -> str:
    """Format a single value for display."""
    if value is None or value == "":
        return "\u2014"
    if isinstance(value, bool):
        return "Так" if value else "Ні"
    if isinstance(value, list):
        return ", ".join(str(v) for v in value) if value else "\u2014"
    if key == "sex":
        return _SEX_UA.get(str(value), str(value))
    if key == "rate":
        return f"{value}%"
    if key == "capital":
        try:
            return f"{int(value):,} грн".replace(",", " ")
        except (ValueError, TypeError):
            pass
    return str(value) if str(value) else "\u2014"


def _color(key: str, value: object) -> str | None:
    """Return 'g' / 'r' / None for status-colored fields."""
    if key not in _STATUS_FIELDS:
        return None
    if isinstance(value, bool):
        return "g" if value else "r"
    lo = str(value).lower()
    if lo in _POS or any(k in lo for k in ("\u2713", "чисто", "активн")):
        return "g"
    if any(k in lo for k in ("\u2717", "знайдено", "недійсн", "викрад")):
        return "r"
    return None


def _prefix(c: str | None, text: str) -> str:
    """Prepend ✓ / ✗ based on status color."""
    if c == "g":
        return f"\u2713 {text}"
    if c == "r":
        return f"\u2717 {text}"
    return text


# ── Data extraction ──────────────────────────────────────────────────────────


def _extract(data: dict) -> tuple[dict, dict]:
    """Split a response dict into scalar fields and list-of-dict fields.

    The ``registry`` wrapper (common in FOP responses) is flattened
    so that its child scalars and lists appear at the top level.
    """
    scalars: dict = {}
    tables: dict = {}

    def _walk(d: dict) -> None:
        for k, v in d.items():
            if k in _SKIP_FIELDS:
                continue
            if isinstance(v, dict):
                if k in ("registry", "data"):
                    _walk(v)
                    continue
                if k == "licenses":
                    # Flatten licenses into scalar key-value pairs
                    _LIC_FIELDS = {
                        "fullName": "Назва", "activities": "Діяльність",
                        "type": "Тип", "number": "Номер", "status": "Статус",
                    }
                    for lk, lv in v.items():
                        if isinstance(lv, dict):
                            parts = [f"{_LIC_FIELDS.get(sk, sk)}: {sv}"
                                     for sk, sv in lv.items() if sv]
                            if parts:
                                scalars[f"_license_{lk}"] = "; ".join(parts)
                        elif lv:
                            scalars[f"_license_{lk}"] = str(lv)
                elif k == "propertyStruct":
                    _PS_UA = {
                        "structSigned": "Підписано",
                        "structFalse": "Недостовірні відомості",
                        "structOpaque": "Непрозора структура",
                        "structExcluded": "Виключено з реєстру",
                    }
                    parts = []
                    for pk, pv in v.items():
                        if pk in _PS_UA and pv is True:
                            parts.append(_PS_UA[pk])
                    signer = ""
                    last = (v.get("lastNameSign") or "").strip()
                    first = (v.get("firstMiddleNameSign") or "").strip()
                    if last or first:
                        signer = f"{last} {first}".strip()
                    dt = v.get("dateStruct", "")
                    if parts or signer:
                        info = ", ".join(parts) if parts else "—"
                        if signer:
                            info += f" ({signer}"
                            if dt:
                                info += f", {dt}"
                            info += ")"
                        elif dt:
                            info += f" (від {dt})"
                        scalars["propertyStruct"] = info
                    elif any(pv is False for pk, pv in v.items() if pk in _PS_UA):
                        scalars["propertyStruct"] = "Не підписано"
                # else: skip nested objects (e.g. address)
            elif isinstance(v, list) and v and isinstance(v[0], dict):
                tables[k] = v
            elif isinstance(v, list):
                scalars[k] = v
            else:
                scalars[k] = v

    _walk(data)
    return scalars, tables


def _merge(*datasets: dict) -> tuple[dict, dict]:
    """Merge multiple API response dicts; first value wins per key."""
    all_scalars: dict = {}
    all_tables: dict = {}
    for ds in datasets:
        sc, tb = _extract(ds)
        for k, v in sc.items():
            all_scalars.setdefault(k, v)
        for k, v in tb.items():
            all_tables.setdefault(k, v)
    return all_scalars, all_tables


# ── Rendering ────────────────────────────────────────────────────────────────


def _render_scalars(pdf: _ReportPDF, scalars: dict) -> None:
    """Render scalar fields grouped by _FIELD_GROUPS, then leftovers."""
    used: set[str] = set()

    for title, keys in _FIELD_GROUPS:
        pairs = [(k, scalars[k]) for k in keys if k in scalars
                 if scalars[k] != "" and scalars[k] is not None]
        if not pairs:
            continue
        pdf.section(title)
        for k, v in pairs:
            label = _LABELS.get(k, _humanize(k))
            c = _color(k, v)
            pdf.kv(f"{label}:", _prefix(c, _fmt(k, v)), c)
            used.add(k)

    rest = [(k, v) for k, v in scalars.items()
            if k not in used and v != "" and v is not None]
    if rest:
        pdf.section("Додаткова інформація")
        for k, v in rest:
            # License keys have _license_ prefix — use value as-is (already formatted)
            if k.startswith("_license_"):
                pdf.kv("Ліцензія:", str(v))
                continue
            label = _LABELS.get(k, _humanize(k))
            c = _color(k, v)
            pdf.kv(f"{label}:", _prefix(c, _fmt(k, v)), c)


def _render_tables(pdf: _ReportPDF, tables: dict) -> None:
    """Render all list-of-dict fields as titled tables."""
    for key, items in tables.items():
        if not items:
            continue
        # Factors get special card-based rendering
        if key == "factors":
            _render_factors(pdf, items)
            continue
        title = _SECTION_TITLES.get(key, _LABELS.get(key, _humanize(key)))
        pdf.section(title)
        cfg = _TABLE_CFG.get(key)
        if cfg:
            _table_known(pdf, items, cfg)
        else:
            _table_auto(pdf, items)


def _table_known(
    pdf: _ReportPDF,
    items: list[dict],
    cfg: dict,
) -> None:
    """Render a table using a predefined column layout."""
    rows: list[list[str]] = []
    for it in items:
        rows.append([_cell(col, it) for col in cfg["cols"]])
    pdf.add_table(cfg["hdrs"], rows, widths=cfg["widths"], scol=cfg.get("scol"))


def _table_auto(pdf: _ReportPDF, items: list[dict]) -> None:
    """Auto-detect columns and render a table from unknown data."""
    col_keys: list[str] = []
    for it in items:
        for k in it:
            if k not in col_keys and k not in _SKIP_FIELDS:
                col_keys.append(k)
    if not col_keys:
        return
    hdrs = [_LABELS.get(k, _humanize(k)) for k in col_keys]
    n = len(col_keys)
    widths = [pdf.pw / n] * n
    rows = [[_fmt(k, it.get(k, "\u2014")) for k in col_keys] for it in items]
    pdf.add_table(hdrs, rows, widths=widths)


# ── Factor card rendering ─────────────────────────────────────────────────

# Factor type → Ukrainian card title
_FACTOR_TITLES: dict[str, str] = {
    "system": "Система оподаткування",
    "singletax": "Єдиний податок",
    "vat": "ПДВ",
    "courtDecision": "Судовий реєстр",
    "courtCompany": "Судові процеси",
    "sanction": "Санкції",
    "taxDebt": "Податковий борг",
    "debt": "Податковий борг",
    "penalty": "Виконавчі провадження",
    "wanted": "Розшук",
    "history": "Історія змін",
    "declarantOwner": "Декларант-власник",
    "system": "Система оподаткування",
    # person-specific
    "ceo": "Керівник юридичної особи",
    "beneficiaries": "Бенефіціар юридичної особи",
    "founders": "Засновник юридичної особи",
    "fop": "ФОП",
    "session": "Судові засідання",
    "courtStatus": "Судові справи",
    "lawyer": "Адвокатська діяльність",
}

# Factor group → fallback title
_FACTOR_GROUP_TITLES: dict[str, str] = {
    "tax": "Податки",
    "court": "Суди",
    "sanction": "Санкції",
    "edr": "ЄДР",
}

# Fields to skip when building card detail lines
_FACTOR_SKIP = frozenset({
    "factorGroup", "icon", "indicator", "type", "text",
    "link", "items", "databaseDate",
})

# Factor field labels
_FACTOR_LABELS: dict[str, str] = {
    "status": "Статус",
    "number": "Номер/ідентифікатор",
    "specificText": "Деталі",
    "dateStart": "Дата початку",
    "dateCancellation": "Дата анулювання",
    "reasonCancellation": "Причина",
    "agencyCancellation": "Підстава",
    "count": "Кількість рішень",
    "sanctionList": "Список",
    "sanctionReason": "Підстава",
    "startDate": "Діє з",
    "endDate": "Діє до",
    "termless": "Безстрокові",
    "duration": "Термін (днів)",
    "fullName": "ПІБ",
    # person: wanted
    "birthDate": "Дата народження",
    "lostDate": "Дата розшуку",
    "articleCrim": "Стаття",
    "lostPlace": "Місце розшуку",
    "ovd": "Орган",
    "sex": "Стать",
    # person: lawyer
    "certnum": "Номер свідоцтва",
    "certat": "Дата видачі",
    "racalc": "Рада адвокатів",
    "certcalc": "Орган видачі",
    "generalSystem": "Загальна система",
    "group": "Група",
    "rate": "Ставка",
    "name": "Назва",
    "liveCount": "Активних справ",
    # debt
    "total": "Загальна сума, грн",
    "local": "Місцеві податки, грн",
    "government": "Державні, грн",
}

# Ukrainian translations for raw API English values
_VALUE_UA: dict[str, str] = {
    # statuses
    "apply": "Діє",
    "active": "Активний",
    "cancellation": "Анульовано",
    "cancelled": "Скасовано",
    "closed": "Закрито",
    "suspended": "Призупинено",
    "expired": "Закінчився",
    "registered": "Зареєстровано",
    "terminated": "Припинено",
    # indicators
    "positive": "Позитивний",
    "negative": "Негативний",
    "warning": "Попередження",
    # boolean-like
    "true": "Так",
    "false": "Ні",
    # court types
    "arbitrage": "Господарські",
    "civil": "Цивільні",
    "criminal": "Кримінальні",
    "admin": "Адміністративні",
    # factor types
    "system": "Система",
    "singletax": "Єдиний податок",
    "vat": "ПДВ",
    "courtDecision": "Судове рішення",
    "courtCompany": "Судові процеси",
    "sanction": "Санкції",
    "taxDebt": "Податковий борг",
}


def _ua(value: object) -> str:
    """Translate a raw API value to Ukrainian if a mapping exists."""
    s = str(value)
    return _VALUE_UA.get(s, _VALUE_UA.get(s.lower(), s))


def _factor_severity(factor: dict) -> str:
    """Determine card severity from factor data."""
    ind = factor.get("indicator", "")
    fg = factor.get("factorGroup", "")
    ftype = factor.get("type", "")
    status = str(factor.get("status", "")).lower()

    # Sanctions are always danger
    if fg == "sanction" or ftype == "sanction":
        return "danger"
    # Critical (wanted)
    if ind == "critical":
        return "danger"
    # Explicit negative
    if ind == "negative" or status in ("cancellation", "cancelled"):
        return "danger"
    # Warnings (courts, etc.)
    if ind == "warning":
        return "warning"
    # Everything else is informational
    return "info"


def _factor_title(factor: dict) -> str:
    """Build card title from factor data."""
    ftype = factor.get("type", "")
    fg = factor.get("factorGroup", "")
    base = _FACTOR_TITLES.get(ftype, _FACTOR_GROUP_TITLES.get(fg, ftype or fg))
    text = factor.get("text", "")
    if text and text != base:
        return f"{base}: {text}"
    return base


def _factor_lines(factor: dict) -> list[str]:
    """Extract all detail lines for a factor card."""
    lines: list[str] = []

    # Special: generalSystem flag
    if factor.get("generalSystem"):
        lines.append("Система оподаткування: загальна")
        return lines

    # Special: singletax details
    if factor.get("type") == "singletax":
        parts = []
        if factor.get("group"):
            parts.append(f"Група: {factor['group']}")
        if factor.get("rate"):
            parts.append(f"Ставка: {factor['rate']}%")
        if factor.get("dateStart"):
            parts.append(f"з {factor['dateStart']}")
        if parts:
            lines.append(", ".join(parts))
        return lines

    # Special: history (EDR changes) — items have date+changes structure
    if factor.get("type") == "history":
        _FIELD_UA = {
            "authorised_capital": "Статутний капітал",
            "founder_capital": "Частка засновника",
            "beneficiary": "Бенефіціарний власник",
            "beneficiary_address": "Адреса бенефіціара",
            "location": "Адреса",
            "ceo_name": "Керівник",
            "name": "Назва",
            "status": "Статус",
            "activity": "Вид діяльності",
        }
        def _short(val: str, limit: int = 50) -> str:
            """Shorten a value, try formatting as number."""
            if not val:
                return ""
            try:
                n = int(val)
                return f"{n:,}".replace(",", " ") + " грн"
            except (ValueError, TypeError):
                pass
            if len(val) > limit:
                return val[:limit] + "…"
            return val

        # Return empty lines — history is rendered via _render_history()
        return lines

    # ── Person-specific factor types ──────────────────────────────────────

    # EDR roles: ceo, beneficiaries, founders — show company info
    if factor.get("type") in ("ceo", "beneficiaries", "founders"):
        company = factor.get("fullName", "")
        code = factor.get("code", "")
        status = factor.get("companyStatus", "")
        activities = factor.get("activities", "")
        if company:
            line = company
            if code:
                line += f" (ЄДРПОУ: {code})"
            lines.append(line)
        if status:
            lines.append(f"Статус: {_ua(status)}")
        if activities:
            lines.append(f"Діяльність: {activities}")
        return lines

    # FOP — private entrepreneur
    if factor.get("type") == "fop":
        name = factor.get("fullName", "")
        location = factor.get("location", "")
        activities = factor.get("activities", "")
        status = factor.get("status", "")
        if name:
            lines.append(name)
        if status:
            lines.append(f"Статус: {_ua(status)}")
        if activities:
            lines.append(f"Діяльність: {activities}")
        if location:
            loc = location[:70] + "…" if len(location) > 70 else location
            lines.append(f"Адреса: {loc}")
        return lines

    # Lawyer
    if factor.get("type") == "lawyer":
        for k in ("fullName", "certnum", "certat", "racalc", "certcalc", "region"):
            v = factor.get(k)
            if not v:
                continue
            label = _FACTOR_LABELS.get(k)
            if not label:
                continue
            # Clean datetime
            if isinstance(v, str) and "T" in v:
                v = v.split("T")[0]
            lines.append(f"{label}: {v}")
        return lines

    # Wanted — critical risk
    if factor.get("type") == "wanted":
        for k in ("fullName", "birthDate", "sex", "articleCrim", "lostDate", "lostPlace", "ovd"):
            v = factor.get(k)
            if not v:
                continue
            label = _FACTOR_LABELS.get(k)
            if not label:
                continue
            if k == "sex":
                v = "Чоловік" if v == "male" else "Жінка" if v == "female" else v
            lines.append(f"{label}: {v}")
        return lines

    # Court sessions (person) — show summary + top N
    if factor.get("type") == "session":
        count = factor.get("count", len(factor.get("items", [])))
        if count:
            lines.append(f"Всього засідань: {count}")
        sub_items = factor.get("items", [])
        shown = min(len(sub_items), 10)
        for si in sub_items[:shown]:
            num = si.get("number", "")
            date = si.get("date", "")
            forma = si.get("forma", "")
            judge = si.get("judge", "")
            parts = []
            if num:
                parts.append(f"№ {num}")
            if date:
                parts.append(date)
            if forma:
                parts.append(forma)
            header = " | ".join(parts) if parts else "—"
            if judge:
                header += f"\n  Суддя: {judge}"
            lines.append(header)
        if len(sub_items) > shown:
            lines.append(f"… та ще {len(sub_items) - shown} засідань")
        return lines

    # Court case statuses (person) — show summary + top N
    if factor.get("type") == "courtStatus":
        count = factor.get("count", len(factor.get("items", [])))
        if count:
            lines.append(f"Всього справ: {count}")
        sub_items = factor.get("items", [])
        shown = min(len(sub_items), 10)
        for si in sub_items[:shown]:
            case_num = si.get("caseNumber", "")
            court = si.get("courtName", "")
            stage = si.get("stageName", "")
            date = si.get("registrationDate", "")
            desc = si.get("description", "")
            parts = []
            if case_num:
                parts.append(f"№ {case_num}")
            if date:
                parts.append(date)
            if desc:
                short_desc = desc[:50] + "…" if len(desc) > 50 else desc
                parts.append(short_desc)
            header = " | ".join(parts) if parts else "—"
            if court:
                header += f"\n  Суд: {court}"
            if stage:
                header += f"\n  Стадія: {stage}"
            lines.append(header)
        if len(sub_items) > shown:
            lines.append(f"… та ще {len(sub_items) - shown} справ")
        return lines

    # declarantOwner — public official owns company
    if factor.get("type") == "declarantOwner":
        sub_items = factor.get("items", [])
        for si in sub_items:
            pib = si.get("pib", "")
            years = si.get("years", [])
            if pib:
                yr_str = ", ".join(str(y) for y in sorted(years)) if years else ""
                line = pib
                if yr_str:
                    line += f" ({yr_str})"
                lines.append(line)
        return lines

    # Special: penalty (enforcement proceedings) — rich item structure
    if factor.get("type") == "penalty":
        sub_items = factor.get("items", [])
        for idx, si in enumerate(sub_items):
            num = si.get("number", "")
            date = si.get("vpBeginDate", "")
            court = si.get("courtName", "")
            creditor = si.get("creditorName", "")
            org = si.get("orgName", "")
            executor = si.get("empFullFio", "")
            header = f"Провадження {idx + 1}"
            if num:
                header += f"  (№ {num})"
            if date:
                header += f"  від {date}"
            parts = [header]
            if creditor:
                parts.append(f"  Стягувач: {creditor}")
            if court:
                parts.append(f"  Суд: {court}")
            if org:
                short_org = org[:55] + "…" if len(org) > 55 else org
                parts.append(f"  Орган ДВС: {short_org}")
            if executor:
                parts.append(f"  Виконавець: {executor}")
            lines.append("\n".join(parts))
        return lines

    # Special: sanction — show details from factor fields
    if factor.get("type") == "sanction":
        for k in ("sanctionList", "sanctionReason", "startDate", "endDate", "termless", "duration"):
            v = factor.get(k)
            if v is None or v == "" or v == []:
                continue
            label = _FACTOR_LABELS.get(k)
            if not label:
                continue
            if isinstance(v, bool):
                v = "Так" if v else "Ні"
            else:
                v = _ua(v)
            lines.append(f"{label}: {v}")
        return lines

    # Special: court with sub-items
    sub_items = factor.get("items", [])
    if sub_items and isinstance(sub_items, list):
        for si in sub_items:
            si_text = si.get("text", si.get("type", ""))
            si_count = si.get("count", 0)
            si_live = si.get("liveCount")
            detail = f"\u2022 {si_text}: {si_count}"
            if si_live is not None:
                detail += f" (активних: {si_live})"
            lines.append(detail)

    # Render remaining fields
    for k, v in factor.items():
        if k in _FACTOR_SKIP:
            continue
        if v is None or v == "" or v == []:
            continue
        label = _FACTOR_LABELS.get(k)
        if not label:
            continue
        if isinstance(v, bool):
            v = "Так" if v else "Ні"
        else:
            v = _ua(v)
        lines.append(f"{label}: {v}")

    return lines


def _render_history(pdf: _ReportPDF, factor: dict) -> None:
    """Render history factor with alternating-bg date blocks."""
    _FIELD_UA = {
        "authorised_capital": "Статутний капітал",
        "founder_capital": "Частка засновника",
        "beneficiary": "Бенефіціарний власник",
        "beneficiary_address": "Адреса бенефіціара",
        "location": "Адреса",
        "ceo_name": "Керівник",
        "name": "Назва",
        "status": "Статус",
        "activity": "Вид діяльності",
    }

    def _short(val: str, limit: int = 200) -> str:
        if not val:
            return ""
        try:
            n = int(val)
            return f"{n:,}".replace(",", " ") + " грн"
        except (ValueError, TypeError):
            pass
        if len(val) > limit:
            return val[:limit] + "\u2026"
        return val

    title = _factor_title(factor)
    blocks: list[list[str]] = []

    for si in factor.get("items", []):
        date = si.get("date", "")
        changes = si.get("changes", [])
        if not changes:
            continue
        block: list[str] = [date]  # first line = date header
        for ch in changes:
            field_raw = ch.get("field", "")
            ch_text = ch.get("text") or _FIELD_UA.get(field_raw, field_raw)
            old_val = ch.get("oldValue", "")
            new_val = ch.get("newValue", "")
            if new_val and old_val:
                block.append(
                    f"\u25b8 {ch_text}\n"
                    f"    {_short(old_val)}  \u2192  {_short(new_val)}"
                )
            elif new_val:
                block.append(f"\u25b8 {ch_text}: {_short(new_val)}")
            elif old_val:
                block.append(f"\u25b8 {ch_text}: {_short(old_val)}")
            else:
                block.append(f"\u25b8 {ch_text}")
        blocks.append(block)

    pdf.history_card(title, blocks)


def _render_factors(pdf: _ReportPDF, factors: list[dict]) -> None:
    """Render factors as color-coded risk cards."""
    pdf.section("Фактори та сигнали ризику")

    # Disclaimer
    pdf.set_font("DV", "", 7.5)
    pdf.set_text_color(*_GRAY)
    pdf.multi_cell(
        pdf.pw, 4,
        "Нижче перелічено індикатори, які джерело позначає як важливі. "
        "Це не юридична кваліфікація і не висновок про правомірність дій компанії.",
        new_x="LMARGIN", new_y="NEXT",
    )
    pdf.ln(3)
    pdf.set_text_color(*_TEXT)

    # Sort: danger first, then warning, then info
    _sev_order = {"danger": 0, "warning": 1, "info": 2}
    sorted_factors = sorted(factors, key=lambda f: _sev_order.get(_factor_severity(f), 9))

    # Check which important checks are present
    factor_types = {f.get("type", "") for f in factors}
    factor_groups = {f.get("factorGroup", "") for f in factors}

    for factor in sorted_factors:
        # History rendered with dedicated alternating-bg card
        if factor.get("type") == "history":
            _render_history(pdf, factor)
            continue
        severity = _factor_severity(factor)
        title = _factor_title(factor)
        lines = _factor_lines(factor)
        pdf.factor_card(title, lines, severity)

    # Detect person report (has person-specific factor types)
    _PERSON_TYPES = {"ceo", "beneficiaries", "founders", "fop", "session", "courtStatus", "lawyer"}
    is_person = bool(factor_types & _PERSON_TYPES)

    # Explicit "not found" cards for important checks that are absent
    _ABSENT_CHECKS = [
        ("sanction", "sanction", "Санкції",
         "Особу не знайдено в санкційних списках" if is_person else "Компанія не знайдена в санкційних списках"),
        ("penalty", "court", "Виконавчі провадження", "Виконавчих проваджень не знайдено"),
    ]
    if is_person:
        _ABSENT_CHECKS.append(
            ("wanted", "risk", "Розшук", "В розшуку не перебуває")
        )
    for ftype, fgroup, title, msg in _ABSENT_CHECKS:
        if ftype not in factor_types and (fgroup is None or fgroup not in factor_groups or ftype != fgroup):
            pdf.factor_card(f"\u2713 {title}", [msg], "info")


def _cell(col: str, item: dict) -> str:
    """Produce a cell value for a known-table column (incl. virtual cols)."""
    if col == "_desc":
        return str(
            item.get("description")
            or _REG_TYPE_UA.get(item.get("type", ""), item.get("type", ""))
        )
    if col == "_type_ua":
        raw = item.get("type", "")
        return _REGISTRY_UA.get(raw, _REG_TYPE_UA.get(raw, raw))
    if col == "_status_display":
        return _item_status(item)
    if col == "_benef_name":
        bn = item.get("beneficiaryName", "")
        name = item.get("name", "")
        if bn and bn != name:
            return f"{name}\n({bn})"
        return name or "\u2014"
    if col in ("_revenue_fmt", "_profit_fmt", "_assets_fmt", "_amount_fmt",
               "_expenses_fmt", "_balance_fmt", "_liability_fmt",
               "_nonCurrentAssets_fmt", "_currentAssets_fmt"):
        raw_key = col.replace("_fmt", "").lstrip("_")
        v = item.get(raw_key, 0)
        try:
            return f"{int(v):,}".replace(",", " ")
        except (ValueError, TypeError):
            return str(v) if v else "\u2014"
    if col in ("_payee_fmt", "_payer_fmt"):
        raw_key = col.replace("_fmt", "").lstrip("_") + "_amount"
        v = item.get(raw_key, 0)
        try:
            fv = float(v)
            if fv == 0:
                return "\u2014"
            return f"{fv:,.2f}".replace(",", " ")
        except (ValueError, TypeError):
            return str(v) if v else "\u2014"
    if col == "_value_fmt":
        v = item.get("value", 0)
        try:
            return f"{int(v):,}".replace(",", " ")
        except (ValueError, TypeError):
            return str(v) if v else "\u2014"
    if col in ("_date_start_fmt", "_date_end_fmt"):
        raw_key = "date_start" if "start" in col else "date_end"
        v = item.get(raw_key, "")
        if not v:
            return "\u2014"
        try:
            from datetime import datetime as _dt
            ts = int(v)
            return _dt.fromtimestamp(ts).strftime("%d.%m.%Y")
        except (ValueError, TypeError, OSError):
            return str(v)
    if col == "_factor_status":
        s = str(item.get("status", "\u2014"))
        return ("\u2713 " + s.capitalize()) if s.lower() in _POS else s
    if col == "isPrimary":
        return "\u2713 Так" if item.get(col) else "Ні"
    if col == "rate":
        v = item.get(col, "\u2014")
        return f"{v}%" if v != "\u2014" else "\u2014"
    return str(item.get(col, "\u2014"))


def _item_status(item: dict) -> str:
    """Build display string for a registry-check item."""
    cnt = item.get("count", 0)
    itype = item.get("type", "")
    s = item.get("status")
    
    if itype == "fop" and s:
        # FOP: show registration status (informational)
        return s.capitalize()
    
    if itype in _INFO_REGISTRIES:
        # Informational: property, etc. — not good/bad, just info
        return f"Знайдено ({cnt})" if cnt > 0 else "Не знайдено"
    
    # Negative registries: clean is good, found is bad
    return "\u2713 Чисто" if cnt == 0 else f"\u2717 Знайдено ({cnt})"


# ── PDF build ────────────────────────────────────────────────────────────────


def _build(
    datasets: tuple[dict, ...],
    title: str = "ЗВІТ ПЕРЕВІРКИ КОНТРАГЕНТА",
    code: str | None = None,
) -> bytes:
    """Synchronous PDF generation — called via asyncio.to_thread."""
    pdf = _ReportPDF()
    pdf.alias_nb_pages()

    scalars, tables = _merge(*datasets)

    if code is None:
        code = str(scalars.get("code", "\u2014"))

    pdf.banner(title, code)
    _render_scalars(pdf, scalars)
    _render_tables(pdf, tables)

    return bytes(pdf.output())


# ── Public interface ─────────────────────────────────────────────────────────


async def generate_report_pdf(
    *datasets: dict,
    title: str = "ЗВІТ ПЕРЕВІРКИ КОНТРАГЕНТА",
    code: str | None = None,
) -> bytes:
    """
    Генерує PDF-звіт із довільної кількості відповідей API.

    Кожен *dataset* — це dict (відповідь одного API-ендпоінту).
    Секції та поля визначаються автоматично зі структури JSON.
    Відомі поля отримують українські підписи; невідомі —
    автоматичну генерацію з назви ключа.

    Args:
        *datasets: один або кілька dict з даними API.
        title: заголовок звіту (банер).
        code: ІПН / ЄДРПОУ для банера (auto-detected якщо None).

    Returns:
        bytes — готовий PDF.
    """
    return await asyncio.to_thread(
        _build, datasets, title, code,
    )


async def generate_contractor_pdf(
    fop_data: dict | None = None,
    person_inn_data: dict | None = None,
    company_data: dict | None = None,
    passport_data: dict | None = None,
) -> bytes:
    """
    Зворотно-сумісний інтерфейс.
    Приймає окремі dict для кожного типу API-відповіді
    та делегує у :func:`generate_report_pdf`.
    """
    datasets = [d for d in (fop_data, person_inn_data, company_data, passport_data) if d]
    return await generate_report_pdf(*datasets)
