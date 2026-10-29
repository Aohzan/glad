"""Shared base of the PDF documents generated with fpdf2.

The DejaVu fonts cover the accents and the euro sign; ``BasePdf`` adds the
helpers every document uses (headings, notes, tables).
"""

from decimal import Decimal
from pathlib import Path
from typing import Any

from fpdf import FPDF
from fpdf.enums import TableBordersLayout
from fpdf.fonts import FontFace

FONT_DIR = Path(__file__).parent / "fonts"
FONT = "DejaVu"


def money(value: Any) -> str:
    """Format an amount as ``1 234,56 €`` with a narrow no-break space (empty for None)."""
    if value is None or value == "":
        return ""
    amount = Decimal(str(value)).quantize(Decimal("0.01"))
    text = f"{amount:,.2f}".replace(",", "\u202f").replace(".", ",")
    return f"{text} €"


class BasePdf(FPDF):
    """A4 portrait document with the DejaVu fonts and the common helpers."""

    def __init__(self) -> None:
        super().__init__(orientation="P", unit="mm", format="A4")
        self.add_font(FONT, "", FONT_DIR / "DejaVuSans.ttf")
        self.add_font(FONT, "B", FONT_DIR / "DejaVuSans-Bold.ttf")
        self.set_auto_page_break(auto=True, margin=18)
        self.alias_nb_pages()

    def heading(self, text: str) -> None:
        self.set_font(FONT, "B", 13)
        self.cell(0, 9, text, new_x="LMARGIN", new_y="NEXT")
        self.ln(1)

    def subheading(self, text: str) -> None:
        self.set_font(FONT, "B", 10)
        self.cell(0, 7, text, new_x="LMARGIN", new_y="NEXT")

    def note(self, text: str) -> None:
        self.set_font(FONT, "", 8)
        self.set_text_color(70)
        self.multi_cell(0, 4.2, text, new_x="LMARGIN", new_y="NEXT")
        self.set_text_color(0)
        self.ln(2)

    def paragraph(self, text: str, size: float = 9.5) -> None:
        """Body text wrapped to the page width."""
        self.set_font(FONT, "", size)
        self.multi_cell(0, size * 0.5, text, new_x="LMARGIN", new_y="NEXT")
        self.ln(1.5)

    def simple_table(
        self,
        headings: list[str],
        rows: list[list[Any]],
        col_widths: list[float],
        bold_rows: set[int] | None = None,
        text_columns: int = 1,
    ) -> None:
        """Draw a table: the first ``text_columns`` are left-aligned, the others right-aligned."""
        self.set_font(FONT, "", 8.5)
        bold = FontFace(emphasis="BOLD", fill_color=(235, 238, 243))
        align = ["LEFT"] * text_columns + ["RIGHT"] * (len(headings) - text_columns)
        with self.table(
            col_widths=col_widths,
            text_align=align,
            borders_layout=TableBordersLayout.MINIMAL,
            headings_style=FontFace(
                emphasis="BOLD", fill_color=(52, 104, 152), color=255
            ),
            line_height=5.5,
            padding=1,
        ) as table:
            head = table.row()
            for heading in headings:
                head.cell(heading)
            for index, values in enumerate(rows):
                style = bold if bold_rows and index in bold_rows else None
                row = table.row(style=style)
                for value in values:
                    row.cell("" if value is None else str(value))
        self.ln(4)

    def render(self) -> bytes:
        """The document as bytes."""
        return bytes(self.output())
