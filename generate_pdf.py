from __future__ import annotations

import argparse
import base64
import os
import re
from dataclasses import dataclass
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Any

import requests
import yaml
from PIL import Image
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader, simpleSplit
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas


RULE_SAFETY_KEYWORDS = [
    "红绿灯",
    "安全带",
    "规则",
    "安全",
    "过马路",
    "斑马线",
    "停车",
    "让行",
    "慢行",
    "看灯",
]

REQUIRED_DAY_FIELDS = {
    "day",
    "stage",
    "theme",
    "theme_type",
    "image_style",
    "image_prompt",
    "cn_sentence",
    "cn_pinyin_marks",
    "en_sentence",
    "en_word_notes",
    "task",
    "image_path",
}

ALLOWED_THEME_TYPES = {"knowledge", "car_model", "brand"}


class ValidationError(Exception):
    pass


@dataclass
class ImageResult:
    day: int
    theme: str
    stage: str
    image_path: str
    image_status: str
    pdf_included: bool
    error: str = ""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="生成汽车学习卡片图片与 PDF")
    parser.add_argument("--config", default="config.yaml", help="配置文件路径")
    parser.add_argument(
        "--days",
        help="生成指定天数，支持 5、1-20、1,3,5-8 形式",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="强制覆盖已存在的图片",
    )
    return parser.parse_args()


def load_yaml(file_path: Path) -> dict[str, Any]:
    if not file_path.exists():
        raise ValidationError(f"文件不存在: {file_path}")
    try:
        data = yaml.safe_load(file_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ValidationError(f"YAML 解析失败: {file_path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValidationError(f"YAML 顶层结构必须是对象: {file_path}")
    return data


def parse_days_expr(expr: str | None, total_days: int) -> list[int]:
    if not expr:
        return list(range(1, total_days + 1))

    selected: set[int] = set()
    for chunk in expr.split(","):
        part = chunk.strip()
        if not part:
            continue
        if "-" in part:
            start_text, end_text = part.split("-", 1)
            if not start_text.isdigit() or not end_text.isdigit():
                raise ValidationError(f"无效的天数范围: {part}")
            start = int(start_text)
            end = int(end_text)
            if start > end:
                raise ValidationError(f"天数范围起点不能大于终点: {part}")
            for day in range(start, end + 1):
                selected.add(day)
        else:
            if not part.isdigit():
                raise ValidationError(f"无效的天数: {part}")
            selected.add(int(part))

    if not selected:
        raise ValidationError("--days 解析后为空，请检查参数格式")

    invalid = [day for day in selected if day < 1 or day > total_days]
    if invalid:
        raise ValidationError(f"天数超出有效范围 1-{total_days}: {sorted(invalid)}")
    return sorted(selected)


def get_stage_for_day(day: int, stages: list[dict[str, Any]]) -> dict[str, Any]:
    for stage in stages:
        day_start, day_end = stage["days"]
        if day_start <= day <= day_end:
            return stage
    raise ValidationError(f"第 {day} 天未匹配到任何阶段，请检查 config.yaml")


def load_hanzi_set(stage_config: dict[str, Any], root: Path) -> set[str]:
    characters: set[str] = set()
    for relative_path in stage_config.get("hanzi_files", []):
        file_path = root / relative_path
        if not file_path.exists():
            raise ValidationError(f"字库文件不存在: {relative_path}")
        content = file_path.read_text(encoding="utf-8")
        for char in content.split():
            if char:
                characters.add(char)
    for char in stage_config.get("extra_chars", []):
        if char:
            characters.add(char)
    if not characters:
        raise ValidationError(f"阶段字库为空: {stage_config.get('name', '未知阶段')}")
    return characters


def is_rule_or_safety_theme(item: dict[str, Any]) -> bool:
    text = " ".join(
        [
            str(item.get("theme", "")),
            str(item.get("cn_sentence", "")),
            str(item.get("task", "")),
            str(item.get("image_prompt", "")),
        ]
    )
    return any(keyword in text for keyword in RULE_SAFETY_KEYWORDS)


def validate_mark_list(value: Any, label: str, day: int) -> None:
    if not isinstance(value, list) or not value:
        raise ValidationError(f"第 {day} 天的 `{label}` 必须是非空列表")
    for entry in value:
        if not isinstance(entry, dict):
            raise ValidationError(f"第 {day} 天的 `{label}` 列表元素必须是对象")


def validate_themes(
    themes_data: dict[str, Any],
    config: dict[str, Any],
    selected_days: list[int],
    root: Path,
) -> list[dict[str, Any]]:
    if "days" not in themes_data or not isinstance(themes_data["days"], list):
        raise ValidationError("`output/themes.yaml` 顶层必须包含 `days` 列表")

    items = themes_data["days"]
    by_day: dict[int, dict[str, Any]] = {}
    seen_themes: set[str] = set()
    brand_names = config.get("rules", {}).get("brand_names", [])
    stages = config.get("stages", [])

    for item in items:
        if not isinstance(item, dict):
            raise ValidationError("`days` 中的每个元素都必须是对象")
        missing = REQUIRED_DAY_FIELDS - set(item.keys())
        if missing:
            raise ValidationError(f"存在缺失字段: {sorted(missing)}，对应记录: {item}")

        day = item["day"]
        if not isinstance(day, int):
            raise ValidationError(f"`day` 必须是整数: {item}")
        if day in by_day:
            raise ValidationError(f"存在重复 day: {day}")
        if item["theme"] in seen_themes:
            raise ValidationError(f"存在重复主题: {item['theme']}")

        theme_type = item["theme_type"]
        if theme_type not in ALLOWED_THEME_TYPES:
            raise ValidationError(f"第 {day} 天的 `theme_type` 非法: {theme_type}")

        validate_mark_list(item["cn_pinyin_marks"], "cn_pinyin_marks", day)
        validate_mark_list(item["en_word_notes"], "en_word_notes", day)

        expected_stage = get_stage_for_day(day, stages)
        if item["stage"] != expected_stage["name"]:
            raise ValidationError(
                f"第 {day} 天的阶段不匹配，期望 `{expected_stage['name']}`，实际 `{item['stage']}`"
            )

        expected_image_path = f"{config['paths']['image_dir']}/day{day:03d}/image.jpg"
        if item["image_path"] != expected_image_path:
            raise ValidationError(
                f"第 {day} 天的 image_path 不符合规则，期望 `{expected_image_path}`，实际 `{item['image_path']}`"
            )

        style = str(item["image_style"])
        if is_rule_or_safety_theme(item):
            if "简约卡通" not in style:
                raise ValidationError(f"第 {day} 天属于规则/安全主题，应使用简约卡通风格")
        elif theme_type in {"brand", "car_model"}:
            if "写实" not in style and "实车" not in style:
                raise ValidationError(f"第 {day} 天属于品牌或车型主题，应使用写实风/实车风")
        elif "简约卡通" not in style:
            raise ValidationError(f"第 {day} 天的知识主题应使用简约卡通风格")

        combined_text = " ".join(
            [
                str(item["theme"]),
                str(item["cn_sentence"]),
                str(item["en_sentence"]),
                str(item["task"]),
            ]
        )
        if theme_type != "brand":
            for brand_name in brand_names:
                if brand_name in combined_text:
                    raise ValidationError(
                        f"第 {day} 天不是品牌主题，但出现品牌名 `{brand_name}`"
                    )

        # 尽早发现阶段字库缺失问题
        load_hanzi_set(expected_stage, root)

        by_day[day] = item
        seen_themes.add(item["theme"])

    if selected_days == list(range(1, config["rules"]["total_days"] + 1)):
        expected_days = set(range(1, config["rules"]["total_days"] + 1))
        actual_days = set(by_day)
        missing_days = sorted(expected_days - actual_days)
        if missing_days:
            raise ValidationError(f"主题数据缺少天数: {missing_days[:10]}")

    missing_selected = [day for day in selected_days if day not in by_day]
    if missing_selected:
        raise ValidationError(f"所选天数缺少数据: {missing_selected}")

    return [by_day[day] for day in selected_days]


def ensure_parent(file_path: Path) -> None:
    file_path.parent.mkdir(parents=True, exist_ok=True)


def read_image_bytes_from_response(data: dict[str, Any]) -> bytes:
    output = data.get("output", {})
    results = output.get("results") or []
    if results:
        first = results[0]
        if isinstance(first, dict):
            if first.get("url"):
                response = requests.get(first["url"], timeout=60)
                response.raise_for_status()
                return response.content
            if first.get("b64_image"):
                return base64.b64decode(first["b64_image"])

    if output.get("image_url"):
        response = requests.get(output["image_url"], timeout=60)
        response.raise_for_status()
        return response.content

    if output.get("image_base64"):
        return base64.b64decode(output["image_base64"])

    raise ValidationError(f"无法从图片接口响应中解析图片数据，响应字段: {list(data.keys())}")


def request_image(prompt: str, config: dict[str, Any]) -> bytes:
    image_model = config["image_model"]
    api_key = os.getenv(image_model["api_key_env"])
    if not api_key:
        raise ValidationError(
            f"缺少图片接口 API Key，请设置环境变量 `{image_model['api_key_env']}`"
        )

    payload = {
        "model": image_model["model_name"],
        "input": {"prompt": prompt},
        "parameters": {
            "size": image_model.get("size", "512*512"),
            "n": image_model.get("n", 1),
        },
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    response = requests.post(
        image_model["base_url"],
        headers=headers,
        json=payload,
        timeout=image_model.get("timeout_seconds", 60),
    )
    response.raise_for_status()
    return read_image_bytes_from_response(response.json())


def save_image(image_bytes: bytes, image_path: Path) -> None:
    ensure_parent(image_path)
    with Image.open(BytesIO(image_bytes)) as img:
        img.convert("RGB").save(image_path, format="JPEG", quality=95)


def process_image(item: dict[str, Any], config: dict[str, Any], root: Path, force: bool) -> ImageResult:
    image_path = root / item["image_path"]
    existed_before = image_path.exists()
    if image_path.exists() and not force:
        return ImageResult(
            day=item["day"],
            theme=item["theme"],
            stage=item["stage"],
            image_path=item["image_path"],
            image_status="skipped_existing",
            pdf_included=True,
        )

    try:
        image_bytes = request_image(item["image_prompt"], config)
        save_image(image_bytes, image_path)
        return ImageResult(
            day=item["day"],
            theme=item["theme"],
            stage=item["stage"],
            image_path=item["image_path"],
            image_status="regenerated" if force and existed_before else "generated",
            pdf_included=True,
        )
    except Exception as exc:  # noqa: BLE001
        return ImageResult(
            day=item["day"],
            theme=item["theme"],
            stage=item["stage"],
            image_path=item["image_path"],
            image_status="failed",
            pdf_included=config["pdf"].get("allow_missing_image", True),
            error=str(exc),
        )


def load_existing_log(log_file: Path) -> dict[int, dict[str, Any]]:
    if not log_file.exists():
        return {}

    entries: dict[int, dict[str, Any]] = {}
    for line in log_file.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        match = re.search(
            r"day=(\d+)\s*\|\s*theme=(.*?)\s*\|\s*stage=(.*?)\s*\|\s*image=(.*?)\s*\|\s*status=(.*?)\s*\|\s*pdf=(.*?)\s*\|\s*error=(.*)$",
            line,
        )
        if not match:
            continue
        day = int(match.group(1))
        entries[day] = {
            "day": day,
            "theme": match.group(2),
            "stage": match.group(3),
            "image_path": match.group(4),
            "image_status": match.group(5),
            "pdf_included": match.group(6) == "yes",
            "error": match.group(7),
            "generated_at": line.split(" | ", 1)[0],
        }
    return entries


def write_log(log_file: Path, results: list[ImageResult]) -> None:
    ensure_parent(log_file)
    existing = load_existing_log(log_file)
    timestamp = datetime.now().isoformat(timespec="seconds")
    for result in results:
        existing[result.day] = {
            "day": result.day,
            "theme": result.theme,
            "stage": result.stage,
            "image_path": result.image_path,
            "image_status": result.image_status,
            "pdf_included": result.pdf_included,
            "error": result.error,
            "generated_at": timestamp,
        }
    lines = []
    for key in sorted(existing):
        item = existing[key]
        lines.append(
            " | ".join(
                [
                    item["generated_at"],
                    f"day={item['day']}",
                    f"theme={item['theme']}",
                    f"stage={item['stage']}",
                    f"image={item['image_path']}",
                    f"status={item['image_status']}",
                    f"pdf={'yes' if item['pdf_included'] else 'no'}",
                    f"error={item['error']}",
                ]
            )
        )
    log_file.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


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


def format_pinyin_marks(marks: list[dict[str, Any]]) -> str:
    return "  ".join(f"{item['word']}({numbered_pinyin_to_tone_marks(item['pinyin'])})" for item in marks)


def format_word_notes(notes: list[dict[str, Any]]) -> str:
    return "  ".join(f"{item['word']}={item['note']}" for item in notes)


def convert_syllable_tone(syllable: str) -> str:
    if not syllable or syllable[-1] not in "12345":
        return syllable

    tone = int(syllable[-1])
    base = syllable[:-1].replace("u:", "v").replace("ü", "v")
    if tone == 5:
        return base.replace("v", "u:")

    tone_map = {
        "a": ["a", "ā", "á", "ǎ", "à"],
        "e": ["e", "ē", "é", "ě", "è"],
        "i": ["i", "ī", "í", "ǐ", "ì"],
        "o": ["o", "ō", "ó", "ǒ", "ò"],
        "u": ["u", "ū", "ú", "ǔ", "ù"],
        "v": ["ü", "ǖ", "ǘ", "ǚ", "ǜ"],
    }

    tone_index = None
    for vowel in "aeo":
        idx = base.find(vowel)
        if idx != -1:
            tone_index = idx
            break

    if tone_index is None and "iu" in base:
        tone_index = base.find("u")
    if tone_index is None and "ui" in base:
        tone_index = base.find("i")
    if tone_index is None:
        for index in range(len(base) - 1, -1, -1):
            if base[index] in tone_map:
                tone_index = index
                break

    if tone_index is None:
        return base.replace("v", "u:")

    vowel = base[tone_index]
    marked = tone_map[vowel][tone]
    return (base[:tone_index] + marked + base[tone_index + 1 :]).replace("v", "ü")


def numbered_pinyin_to_tone_marks(pinyin_text: str) -> str:
    return " ".join(convert_syllable_tone(part) for part in pinyin_text.split())


def draw_wrapped_text(
    pdf: canvas.Canvas,
    text: str,
    x: float,
    y: float,
    width: float,
    font_name: str,
    font_size: int,
    line_height: float,
    color: colors.Color = colors.black,
) -> float:
    pdf.setFillColor(color)
    pdf.setFont(font_name, font_size)
    lines = simpleSplit(text, font_name, font_size, width)
    for line in lines:
        pdf.drawString(x, y, line)
        y -= line_height
    return y


def draw_centered_wrapped_text(
    pdf: canvas.Canvas,
    text: str,
    x: float,
    y: float,
    width: float,
    font_name: str,
    font_size: float,
    line_height: float,
    color: colors.Color = colors.black,
) -> float:
    pdf.setFillColor(color)
    pdf.setFont(font_name, font_size)
    lines = simpleSplit(text, font_name, font_size, width)
    for line in lines:
        pdf.drawCentredString(x + width / 2, y, line)
        y -= line_height
    return y


def measure_text_height(text: str, width: float, font_name: str, font_size: float, line_height: float) -> float:
    return len(simpleSplit(text, font_name, font_size, width)) * line_height


def draw_english_with_underlines(
    pdf: canvas.Canvas,
    text: str,
    notes: list[dict[str, Any]],
    x: float,
    y: float,
    width: float,
    font_name: str,
    font_size: float,
    line_height: float,
    color: colors.Color,
) -> float:
    pdf.setFillColor(color)
    pdf.setStrokeColor(color)
    pdf.setFont(font_name, font_size)
    lines = simpleSplit(text, font_name, font_size, width)
    keywords = {
        part.lower()
        for note in notes
        for part in str(note.get("word", "")).replace("-", " ").split()
        if part
    }

    for line in lines:
        cursor_x = x
        tokens = re.split(r"(\s+)", line)
        for token in tokens:
            if not token:
                continue
            token_width = pdf.stringWidth(token, font_name, font_size)
            if token.isspace():
                cursor_x += token_width
                continue
            pdf.drawString(cursor_x, y, token)
            normalized = token.strip(".,!?;:'\"()").lower()
            if normalized in keywords:
                underline_y = y - 2
                pdf.setLineWidth(0.9)
                pdf.line(cursor_x, underline_y, cursor_x + token_width, underline_y)
            cursor_x += token_width
        y -= line_height
    return y


def draw_card(
    pdf: canvas.Canvas,
    item: dict[str, Any],
    root: Path,
    x: float,
    y: float,
    width: float,
    height: float,
    cn_font: str,
    en_font: str,
) -> None:
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
        draw_x = image_x + (image_width - draw_width) / 2
        draw_y = image_y + (image_height - draw_height) / 2
        pdf.drawImage(image_reader, draw_x, draw_y, draw_width, draw_height, preserveAspectRatio=True)
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

    cn_height = measure_text_height(cn_sentence, text_width, cn_font, cn_font_size, 28)
    pinyin_height = measure_text_height(pinyin_text, text_width, cn_font, pinyin_font_size, 20)
    en_height = measure_text_height(en_sentence, text_width, en_font, en_font_size, 24)
    notes_height = measure_text_height(notes_text, text_width, cn_font, notes_font_size, 20)
    task_height = measure_text_height(task_text, text_width, cn_font, 14, 19)

    gap_after_cn = 10
    gap_after_pinyin = 20
    gap_after_en = 8
    gap_after_notes = 20

    block_height = (
        cn_height
        + gap_after_cn
        + pinyin_height
        + gap_after_pinyin
        + en_height
        + gap_after_en
        + notes_height
        + gap_after_notes
        + task_height
    )

    current_y = y + padding + (body_height + block_height) / 2

    current_y = draw_wrapped_text(
        pdf,
        cn_sentence,
        text_x,
        current_y,
        text_width,
        cn_font,
        cn_font_size,
        28,
        colors.HexColor("#111111"),
    )
    current_y -= gap_after_cn
    current_y = draw_centered_wrapped_text(
        pdf,
        pinyin_text,
        text_x,
        current_y,
        text_width,
        cn_font,
        pinyin_font_size,
        20,
        colors.HexColor("#A05A00"),
    )
    current_y -= gap_after_pinyin
    current_y = draw_english_with_underlines(
        pdf,
        en_sentence,
        item["en_word_notes"],
        text_x,
        current_y,
        text_width,
        en_font,
        en_font_size,
        24,
        colors.HexColor("#0B4F8A"),
    )
    current_y -= gap_after_en
    current_y = draw_centered_wrapped_text(
        pdf,
        notes_text,
        text_x,
        current_y,
        text_width,
        cn_font,
        notes_font_size,
        20,
        colors.HexColor("#005FCC"),
    )
    current_y -= gap_after_notes
    draw_wrapped_text(
        pdf,
        task_text,
        text_x,
        current_y,
        text_width,
        cn_font,
        14,
        19,
        colors.HexColor("#245C3A"),
    )


def draw_cut_guides(pdf: canvas.Canvas, page_width: float, page_height: float, margin: float, gap: float) -> None:
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


def render_pdf(items: list[dict[str, Any]], config: dict[str, Any], root: Path) -> Path:
    pdf_file = root / config["paths"]["pdf_file"]
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
        draw_cut_guides(pdf, page_width, page_height, margin, gap)
        top_y = page_height - margin - card_height
        draw_card(pdf, page_items[0], root, margin, top_y, card_width, card_height, cn_font, en_font)
        if len(page_items) > 1:
            bottom_y = margin
            draw_card(pdf, page_items[1], root, margin, bottom_y, card_width, card_height, cn_font, en_font)
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


def main() -> None:
    args = parse_args()
    root = Path(__file__).resolve().parent
    config_path = root / args.config
    config = load_yaml(config_path)
    total_days = config["rules"]["total_days"]
    selected_days = parse_days_expr(args.days, total_days)

    themes_path = root / config["paths"]["themes_file"]
    themes_data = load_yaml(themes_path)
    items = validate_themes(themes_data, config, selected_days, root)

    results: list[ImageResult] = []
    for item in items:
        results.append(process_image(item, config, root, args.force))

    log_file = root / config["paths"]["log_file"]
    write_log(log_file, results)

    pdf_file = render_pdf(items, config, root)
    print_summary(items, results, pdf_file)


if __name__ == "__main__":
    try:
        main()
    except ValidationError as exc:
        raise SystemExit(f"错误: {exc}")
