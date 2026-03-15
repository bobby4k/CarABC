from __future__ import annotations

from pathlib import Path

from .exceptions import ValidationError


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


def ensure_parent(file_path: Path) -> None:
    file_path.parent.mkdir(parents=True, exist_ok=True)


def build_days_suffix(selected_days: list[int]) -> str:
    if not selected_days:
        raise ValidationError("未选择任何天数，无法生成 PDF 文件名")

    ranges: list[tuple[int, int]] = []
    start = selected_days[0]
    end = selected_days[0]
    for day in selected_days[1:]:
        if day == end + 1:
            end = day
        else:
            ranges.append((start, end))
            start = end = day
    ranges.append((start, end))

    parts = []
    for start, end in ranges:
        parts.append(str(start) if start == end else f"{start}-{end}")
    return ",".join(parts)


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


def format_pinyin_marks(marks: list[dict[str, str]]) -> str:
    return "  ".join(f"{item['word']}({numbered_pinyin_to_tone_marks(item['pinyin'])})" for item in marks)


def format_word_notes(notes: list[dict[str, str]]) -> str:
    return "  ".join(f"{item['word']}={item['note']}" for item in notes)
