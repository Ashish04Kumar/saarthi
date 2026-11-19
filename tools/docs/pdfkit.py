"""Small helpers on top of ReportLab for Saarthi's PDF docs."""

from __future__ import annotations

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Image,
    KeepTogether,
    ListFlowable,
    ListItem,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs"

INK = colors.HexColor("#1B2440")
SUB = colors.HexColor("#5B6684")
ACCENT = colors.HexColor("#3E6FE0")
SOFT = colors.HexColor("#EEF2FB")
LINE = colors.HexColor("#C9D3EA")


def _font_dir() -> Path | None:
    for d in ("/usr/share/fonts/truetype/dejavu", "/usr/share/fonts/dejavu", "/Library/Fonts", "C:/Windows/Fonts"):
        if (Path(d) / "DejaVuSans.ttf").exists():
            return Path(d)
    return None


def register_fonts() -> tuple[str, str, str]:
    d = _font_dir()
    if d is None:  # fall back to the PDF base fonts (no ✓ glyphs)
        return "Helvetica", "Helvetica-Bold", "Courier"
    pdfmetrics.registerFont(TTFont("DV", str(d / "DejaVuSans.ttf")))
    pdfmetrics.registerFont(TTFont("DV-B", str(d / "DejaVuSans-Bold.ttf")))
    mono = d / "DejaVuSansMono.ttf"
    if mono.exists():
        pdfmetrics.registerFont(TTFont("DV-M", str(mono)))
    pdfmetrics.registerFontFamily("DV", normal="DV", bold="DV-B", italic="DV", boldItalic="DV-B")
    return "DV", "DV-B", "DV-M" if mono.exists() else "Courier"


BODY, BOLD, MONO = register_fonts()

S = {
    "title": ParagraphStyle("title", fontName=BOLD, fontSize=26, leading=31, textColor=INK, spaceAfter=6),
    "subtitle": ParagraphStyle("subtitle", fontName=BODY, fontSize=12.5, leading=17, textColor=SUB, spaceAfter=14),
    "h1": ParagraphStyle("h1", fontName=BOLD, fontSize=17, leading=22, textColor=ACCENT, spaceBefore=12,
                         spaceAfter=6, keepWithNext=1),
    "h2": ParagraphStyle("h2", fontName=BOLD, fontSize=12.5, leading=16, textColor=INK, spaceBefore=8, spaceAfter=3,
                         keepWithNext=1),
    "body": ParagraphStyle("body", fontName=BODY, fontSize=9.6, leading=14, textColor=INK, alignment=TA_LEFT,
                           spaceAfter=5),
    "small": ParagraphStyle("small", fontName=BODY, fontSize=8.4, leading=11.5, textColor=SUB),
    "cell": ParagraphStyle("cell", fontName=BODY, fontSize=8.6, leading=11.6, textColor=INK),
    "cellb": ParagraphStyle("cellb", fontName=BOLD, fontSize=8.6, leading=11.6, textColor=colors.white),
    "code": ParagraphStyle("code", fontName=MONO, fontSize=8.6, leading=11.6, textColor=INK,
                           backColor=SOFT, borderPadding=(5, 6, 5, 6), spaceBefore=3, spaceAfter=8,
                           leftIndent=4, rightIndent=4),
    "note": ParagraphStyle("note", fontName=BODY, fontSize=9.2, leading=13, textColor=INK,
                           backColor=colors.HexColor("#FFF6DA"), borderPadding=(6, 7, 6, 7), spaceBefore=4,
                           spaceAfter=9, leftIndent=4, rightIndent=4),
}


def P(text: str, style: str = "body") -> Paragraph:
    return Paragraph(text, S[style])


def code(text: str) -> Paragraph:
    esc = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br/>")
    return Paragraph(esc, S["code"])


def bullets(items: list[str]) -> ListFlowable:
    return ListFlowable(
        [ListItem(P(t), leftIndent=12, value="•") for t in items],
        bulletType="bullet", start="•", leftIndent=12, bulletFontName=BODY, bulletColor=ACCENT,
    )


def table(rows: list[list[str]], widths: list[float], header: bool = True) -> Table:
    data = []
    for i, row in enumerate(rows):
        style = "cellb" if header and i == 0 else "cell"
        data.append([Paragraph(c, S[style]) for c in row])
    t = Table(data, colWidths=[w * mm for w in widths], repeatRows=1 if header else 0)
    cmds = [
        ("GRID", (0, 0), (-1, -1), 0.4, LINE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]
    if header:
        cmds.append(("BACKGROUND", (0, 0), (-1, 0), ACCENT))
    for r in range(1 if header else 0, len(rows)):
        if r % 2 == 0:
            cmds.append(("BACKGROUND", (0, r), (-1, r), SOFT))
    t.setStyle(TableStyle(cmds))
    return t


def image(name: str, width_mm: float, caption: str | None = None):
    path = DOCS / name
    if not path.exists():
        return Spacer(1, 1)
    from reportlab.lib.utils import ImageReader

    iw, ih = ImageReader(str(path)).getSize()
    w = width_mm * mm
    img = Image(str(path), width=w, height=w * ih / iw)
    parts = [img]
    if caption:
        parts.append(P(caption, "small"))
    parts.append(Spacer(1, 6))
    return KeepTogether(parts)


def build(path: Path, title: str, story: list) -> None:
    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont(BODY, 7.8)
        canvas.setFillColor(SUB)
        canvas.drawString(18 * mm, 10 * mm, f"Saarthi · {title}")
        canvas.drawRightString(A4[0] - 18 * mm, 10 * mm, f"Page {doc.page}")
        canvas.setStrokeColor(LINE)
        canvas.line(18 * mm, 13 * mm, A4[0] - 18 * mm, 13 * mm)
        canvas.restoreState()

    doc = SimpleDocTemplate(str(path), pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm,
                            bottomMargin=18 * mm, title=f"Saarthi – {title}", author="Saarthi contributors")
    doc.build(story, onFirstPage=footer, onLaterPages=footer)


__all__ = ["P", "code", "bullets", "table", "image", "build", "PageBreak", "Spacer", "DOCS", "S"]
