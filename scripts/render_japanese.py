"""Render a bilingual (English + Japanese) lesson PDF next to its English original.

Reads build/extracted/englishpod_XXXX.json (English, from extract_lessons.py) and
build/translated/englishpod_XXXX.ja.json (Japanese), and writes
pdf/<range>/japanesepod_XXXX.pdf.
"""
import io
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pymupdf
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate,
    CondPageBreak,
    Frame,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

import fetch_fonts

ROOT = Path(__file__).resolve().parent.parent
EXTRACTED = ROOT / "build" / "extracted"
TRANSLATED = ROOT / "build" / "translated"

PAGE_W, PAGE_H = A4
MARGIN = 22 * mm
CONTENT_W = PAGE_W - 2 * MARGIN
HEADER_H = 26 * mm
FOOTER_H = 14 * mm

INK = colors.HexColor("#1a1a1a")
JA_INK = colors.HexColor("#1c3f5e")
MUTED = colors.HexColor("#6b7280")
RULE = colors.HexColor("#d4d4d8")
BAND = colors.HexColor("#f4f6f8")

REGULAR, BOLD = "NotoSansJP", "NotoSansJP-Bold"


def register_fonts():
    font_dir = fetch_fonts.ensure()
    pdfmetrics.registerFont(TTFont(REGULAR, font_dir / "NotoSansJP-Regular.ttf"))
    pdfmetrics.registerFont(TTFont(BOLD, font_dir / "NotoSansJP-Bold.ttf"))
    pdfmetrics.registerFontFamily(REGULAR, normal=REGULAR, bold=BOLD)


def styles():
    def style(name, size, leading, color=INK, **kw):
        return ParagraphStyle(
            name,
            fontName=REGULAR,
            alignment=TA_LEFT,
            fontSize=size,
            leading=leading,
            textColor=color,
            **kw,
        )

    return {
        "title": style("title", 15, 21, spaceAfter=2),
        "subtitle": style("subtitle", 10, 14, MUTED),
        "heading": style("heading", 12, 16, spaceBefore=12, spaceAfter=6),
        "speaker": style("speaker", 9.5, 13, MUTED),
        "en": style("en", 10.5, 15),
        "ja": style("ja", 10, 15.5, JA_INK),
        "term": style("term", 10.5, 14.5),
        "pos": style("pos", 9.5, 13.5, MUTED),
        "def": style("def", 10, 14.5, JA_INK),
    }


def escape(text):
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def logo_image(source_pdf):
    """Reuse the banner from the top of the English original, at its original aspect."""
    doc = pymupdf.open(ROOT / source_pdf)
    page = doc[0]
    images = page.get_images(full=True)
    if not images:
        doc.close()
        return None
    xref = images[0][0]
    pix = pymupdf.Pixmap(doc, xref)
    if pix.n - pix.alpha > 3:
        pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
    data = pix.tobytes("png")
    bbox = page.get_image_bbox(images[0])
    doc.close()
    width = min(CONTENT_W, bbox.width)
    return io.BytesIO(data), width, width * bbox.height / bbox.width


class LessonDoc(BaseDocTemplate):
    def __init__(self, path, logo, footer):
        super().__init__(
            str(path),
            pagesize=A4,
            leftMargin=MARGIN,
            rightMargin=MARGIN,
            topMargin=MARGIN + HEADER_H,
            bottomMargin=MARGIN + FOOTER_H,
        )
        self.logo, self.footer = logo, footer
        frame = Frame(
            self.leftMargin, self.bottomMargin, CONTENT_W, self.height, id="body", showBoundary=0
        )
        self.addPageTemplates(PageTemplate(id="lesson", frames=[frame], onPage=self.decorate))

    def decorate(self, canvas, _doc):
        canvas.saveState()
        if self.logo:
            stream, width, height = self.logo
            stream.seek(0)
            canvas.drawImage(
                ImageReader(stream),
                MARGIN,
                PAGE_H - MARGIN - height,
                width=width,
                height=height,
                mask="auto",
            )
        canvas.setStrokeColor(RULE)
        canvas.setLineWidth(0.5)
        canvas.line(MARGIN, MARGIN + FOOTER_H - 4, PAGE_W - MARGIN, MARGIN + FOOTER_H - 4)
        canvas.setFont(REGULAR, 8)
        canvas.setFillColor(MUTED)
        canvas.drawString(MARGIN, MARGIN + 4, self.footer)
        canvas.drawRightString(PAGE_W - MARGIN, MARGIN + 4, f"— {canvas.getPageNumber()} —")
        canvas.restoreState()


def dialogue_table(turns, st):
    # A few lessons are unlabelled verse or narration; they get a single column, because
    # a zero-width speaker column makes the table collapse.
    labelled = any(t["speaker"] for t in turns)
    rows = []
    for turn in turns:
        body = [Paragraph(escape(turn["text"]), st["en"])]
        if turn.get("ja"):
            body += [Spacer(1, 2), Paragraph(escape(turn["ja"]), st["ja"])]
        rows.append([Paragraph(escape(turn["speaker"]), st["speaker"]), body] if labelled else [body])

    style = [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("LEFTPADDING", (0, 0), (0, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("LINEBELOW", (0, 0), (-1, -2), 0.4, RULE),
    ]
    if labelled:
        widest = max(pdfmetrics.stringWidth(t["speaker"], REGULAR, 9.5) for t in turns)
        label_w = min(88, max(26, widest + 8))
        widths = [label_w, CONTENT_W - label_w]
        style.append(("LEFTPADDING", (1, 0), (1, -1), 4))
    else:
        widths = [CONTENT_W]

    table = Table(rows, colWidths=widths, hAlign="LEFT")
    table.setStyle(TableStyle(style))
    return table


def vocab_table(entries, st):
    rows = [
        [
            Paragraph(f"<b>{escape(e['term'])}</b>", st["term"]),
            Paragraph(escape(e["pos"]), st["pos"]),
            Paragraph(escape(e["definition"]), st["def"]),
        ]
        for e in entries
    ]
    widths = [CONTENT_W * 0.28, CONTENT_W * 0.19, CONTENT_W * 0.53]
    table = Table(rows, colWidths=widths, hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("LEFTPADDING", (0, 0), (0, -1), 0),
                ("RIGHTPADDING", (-1, 0), (-1, -1), 0),
                ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.white, BAND]),
                ("LINEBELOW", (0, 0), (-1, -2), 0.4, RULE),
            ]
        )
    )
    return table


def check(lesson, japanese):
    """The two files are zipped positionally, so a length mismatch would silently
    attach the wrong translation to a line."""
    for key in ("dialogue", "key_vocabulary", "supplementary_vocabulary"):
        if len(lesson[key]) != len(japanese.get(key, [])):
            raise ValueError(
                f"{lesson['id']}: {key} has {len(lesson[key])} English entries "
                f"but {len(japanese.get(key, []))} Japanese"
            )
    if not japanese.get("title"):
        raise ValueError(f"{lesson['id']}: missing Japanese title")


def build(lesson, japanese, out_path):
    check(lesson, japanese)
    st = styles()
    turns = [dict(t, ja=ja) for t, ja in zip(lesson["dialogue"], japanese["dialogue"])]

    def merge(key):
        return [
            {"term": e["term"], "pos": j["pos"], "definition": j["definition"]}
            for e, j in zip(lesson[key], japanese[key])
        ]

    story = [
        Paragraph(f"<b>{escape(japanese['title'])}</b>", st["title"]),
        Paragraph(escape(lesson["title"]), st["subtitle"]),
        Spacer(1, 12),
    ]
    def section(heading, table):
        # A heading cannot use keepWithNext here: its table is usually taller than a page,
        # so the implied KeepTogether would fail and push the whole section down.
        return [CondPageBreak(96), Paragraph(f"<b>{escape(heading)}</b>", st["heading"]), table]

    if turns:
        story += section("ダイアログ / Dialogue", dialogue_table(turns, st))
    for key, heading in (
        ("key_vocabulary", "重要語彙 / Key Vocabulary"),
        ("supplementary_vocabulary", "補足語彙 / Supplementary Vocabulary"),
    ):
        entries = merge(key)
        if entries:
            story += section(heading, vocab_table(entries, st))

    footer = f"{lesson['title']}  ·  日本語版 / Japanese edition  ·  © Praxis Language Ltd."
    LessonDoc(out_path, logo_image(lesson["source"]), footer).build(story)


def main(ids=None):
    register_fonts()
    targets = sorted(EXTRACTED.glob("englishpod_*.json"))
    if ids:
        targets = [p for p in targets if p.stem.split("_")[1] in set(ids)]
    written, skipped = 0, []
    for path in targets:
        ja_path = TRANSLATED / f"{path.stem}.ja.json"
        if not ja_path.exists():
            skipped.append(path.stem)
            continue
        lesson = json.loads(path.read_text(encoding="utf-8"))
        japanese = json.loads(ja_path.read_text(encoding="utf-8"))
        out = ROOT / Path(lesson["source"]).parent / f"japanesepod_{lesson['id']}.pdf"
        build(lesson, japanese, out)
        written += 1
    print(f"rendered {written} PDFs")
    if skipped:
        print(f"missing translations: {len(skipped)}", file=sys.stderr)


if __name__ == "__main__":
    main(sys.argv[1:] or None)
