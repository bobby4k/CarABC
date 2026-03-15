from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader, simpleSplit
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from .models import ImageResult
from .utils import build_days_suffix, ensure_parent, format_pinyin_marks, format_word_notes


def register_fonts(config: dict[str, Any], root: Path) -> tuple[str, str]:
    font_path = root / config["paths"]["font_path"]
    try:
        if font_path.exists():
            pdfmetrics.registerFont(TTFont("CardCN", str(font_path)))
            return "CardCN", "Helvetica-Bold"
        pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
        return "STSong-Light", "Helvetica-Bold"
    except Exception:  # noqa: BLE001
        pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
        return "STSong-Light", "Helvetica-Bold"


def draw_wrapped_text(pdf: canvas.Canvas, text: str, x: float, y: float, width: float, font_name: str, font_size: float, line_height: float, color: colors.Color = colors.black) -> float:
    pdf.setFillColor(color)
    pdf.setFont(font_name, font_size)
    for line in simpleSplit(text, font_name, font_size, width):
        pdf.drawString(x, y, line)
        y -= line_height
    return y


def draw_centered_wrapped_text(pdf: canvas.Canvas, text: str, x: float, y: float, width: float, font_name: str, font_size: float, line_height: float, color: colors.Color = colors.black) -> float:
    pdf.setFillColor(color)
    pdf.setFont(font_name, font_size)
    for line in simpleSplit(text, font_name, font_size, width):
        pdf.drawCentredString(x + width / 2, y, line)
        y -= line_height
    return y


def measure_text_height(text: str, width: float, font_name: str, font_size: float, line_height: float) -> float:
    return len(simpleSplit(text, font_name, font_size, width)) * line_height


def draw_english_with_underlines(pdf: canvas.Canvas, text: str, notes: list[dict[str, Any]], x: float, y: float, width: float, font_name: str, font_size: float, line_height: float, color: colors.Color) -> float:
    pdf.setFillColor(color)
    pdf.setStrokeColor(color)
    pdf.setFont(font_name, font_size)
    keywords = {part.lower() for note in notes for part in str(note.get("word", "")).replace("-", " ").split() if part}
    for line in simpleSplit(text, font_name, font_size, width):
        cursor_x = x
        for token in re.split(r"(\s+)", line):
            if not token:
                continue
            token_width = pdf.stringWidth(token, font_name, font_size)
            if token.isspace():
                cursor_x += token_width
                continue
            pdf.drawString(cursor_x, y, token)
            if token.strip(".,!?;:'\"()").lower() in keywords:
                pdf.setLineWidth(0.9)
                pdf.line(cursor_x, y - 2, cursor_x + token_width, y - 2)
            cursor_x += token_width
        y -= line_height
    return y


def draw_card(pdf: canvas.Canvas, item: dict[str, Any], root: Path, x: float, y: float, width: float, height: float, cn_font: str, en_font: str) -> None:
    padding = 22
    header_height = 34
    column_gap = 18
    text_width = width * 0.42
    image_width = width - padding * 2 - text_width - column_gap
    body_height = height - header_height - padding * 2
    image_height = body_height

    pdf.setStrokeColor(colors.HexColor("#D9D9D9"))
    pdf.setLineWidth(0.8)
    pdf.setFillColor(colors.white)
    pdf.roundRect(x, y, width, height, 10, stroke=1, fill=1)

    pdf.setFillColor(colors.HexColor("#333333"))
    pdf.setFont(cn_font, 15)
    pdf.drawString(x + padding, y + height - 24, f"Day {item['day']:03d} | {item['stage']} | {item['theme']}")

    text_x = x + padding
    image_x = x + width - padding - image_width
    image_y = y + padding
    image_path = root / item["image_path"]

    pdf.setStrokeColor(colors.HexColor("#D9D9D9"))
    pdf.setFillColor(colors.white)
    pdf.roundRect(image_x, image_y, image_width, image_height, 12, stroke=1, fill=1)
    if image_path.exists():
        image_reader = ImageReader(str(image_path))
        img_width, img_height = image_reader.getSize()
        img_ratio = img_width / img_height
        box_ratio = image_width / image_height
        if img_ratio > box_ratio:
            draw_width = image_width
            draw_height = draw_width / img_ratio
        else:
            draw_height = image_height
            draw_width = draw_height * img_ratio
        pdf.drawImage(image_reader, image_x + (image_width - draw_width) / 2, image_y + (image_height - draw_height) / 2, draw_width, draw_height, preserveAspectRatio=True)
    else:
        pdf.setFillColor(colors.HexColor("#F3F3F3"))
        pdf.roundRect(image_x + 6, image_y + 6, image_width - 12, image_height - 12, 10, stroke=0, fill=1)
        pdf.setFillColor(colors.HexColor("#888888"))
        pdf.setFont(cn_font, 16)
        pdf.drawCentredString(image_x + image_width / 2, image_y + image_height / 2 + 6, "图片暂缺")
        pdf.setFont(cn_font, 11)
        pdf.drawCentredString(image_x + image_width / 2, image_y + image_height / 2 - 12, "可重试生成或使用占位图")

    cn_sentence = item["cn_sentence"]
    pinyin_text = format_pinyin_marks(item["cn_pinyin_marks"])
    en_sentence = item["en_sentence"]
    notes_text = format_word_notes(item["en_word_notes"])
    task_text = f"互动任务：{item['task']}"

    cn_font_size = 22
    pinyin_font_size = 15
    en_font_size = 22.5
    notes_font_size = 15

    block_height = (
        measure_text_height(cn_sentence, text_width, cn_font, cn_font_size, 28)
        + 10
        + measure_text_height(pinyin_text, text_width, cn_font, pinyin_font_size, 20)
        + 20
        + measure_text_height(en_sentence, text_width, en_font, en_font_size, 24)
        + 8
        + measure_text_height(notes_text, text_width, cn_font, notes_font_size, 20)
        + 20
        + measure_text_height(task_text, text_width, cn_font, 14, 19)
    )

    current_y = y + padding + (body_height + block_height) / 2
    current_y = draw_wrapped_text(pdf, cn_sentence, text_x, current_y, text_width, cn_font, cn_font_size, 28, colors.HexColor("#111111"))
    current_y -= 10
    current_y = draw_centered_wrapped_text(pdf, pinyin_text, text_x, current_y, text_width, cn_font, pinyin_font_size, 20, colors.HexColor("#A05A00"))
    current_y -= 20
    current_y = draw_english_with_underlines(pdf, en_sentence, item["en_word_notes"], text_x, current_y, text_width, en_font, en_font_size, 24, colors.HexColor("#0B4F8A"))
    current_y -= 8
    current_y = draw_centered_wrapped_text(pdf, notes_text, text_x, current_y, text_width, cn_font, notes_font_size, 20, colors.HexColor("#005FCC"))
    current_y -= 20
    draw_wrapped_text(pdf, task_text, text_x, current_y, text_width, cn_font, 14, 19, colors.HexColor("#245C3A"))


def draw_cut_guides(pdf: canvas.Canvas, page_width: float, page_height: float, margin: float) -> None:
    middle_y = page_height / 2
    pdf.saveState()
    pdf.setStrokeColor(colors.HexColor("#BBBBBB"))
    pdf.setDash(3, 3)
    pdf.setLineWidth(0.8)
    pdf.line(margin / 2, middle_y, page_width - margin / 2, middle_y)
    pdf.setDash()
    mark = 10
    for x in (margin, page_width - margin):
        pdf.line(x, page_height - margin + 2, x, page_height - margin + 2 + mark)
        pdf.line(x, margin - 2, x, margin - 2 - mark)
    pdf.line(margin - 2 - mark, middle_y, margin - 2, middle_y)
    pdf.line(page_width - margin + 2, middle_y, page_width - margin + 2 + mark, middle_y)
    pdf.restoreState()


def render_pdf(items: list[dict[str, Any]], config: dict[str, Any], root: Path, selected_days: list[int]) -> Path:
    pdf_base_file = root / config["paths"]["pdf_file"]
    pdf_file = pdf_base_file.with_name(f"{pdf_base_file.stem}_day{build_days_suffix(selected_days)}{pdf_base_file.suffix}")
    ensure_parent(pdf_file)
    cn_font, en_font = register_fonts(config, root)
    page_width, page_height = A4
    margin = 18
    gap = 16
    card_width = page_width - margin * 2
    card_height = (page_height - margin * 2 - gap) / 2
    pdf = canvas.Canvas(str(pdf_file), pagesize=A4)
    pdf.setTitle("Car Learning Cards")
    for index in range(0, len(items), 2):
        page_items = items[index : index + 2]
        draw_cut_guides(pdf, page_width, page_height, margin)
        top_y = page_height - margin - card_height
        draw_card(pdf, page_items[0], root, margin, top_y, card_width, card_height, cn_font, en_font)
        if len(page_items) > 1:
            draw_card(pdf, page_items[1], root, margin, margin, card_width, card_height, cn_font, en_font)
        pdf.showPage()
    pdf.save()
    return pdf_file


def print_summary(items: list[dict[str, Any]], results: list[ImageResult], pdf_file: Path) -> None:
    generated = sum(result.image_status == "generated" for result in results)
    regenerated = sum(result.image_status == "regenerated" for result in results)
    skipped = sum(result.image_status == "skipped_existing" for result in results)
    failed = sum(result.image_status == "failed" for result in results)
    print(f"已处理天数: {items[0]['day']}-{items[-1]['day']}，共 {len(items)} 天")
    print(f"图片生成: 新生成 {generated}，覆盖 {regenerated}，跳过 {skipped}，失败 {failed}")
    print(f"PDF 输出: {pdf_file}")
