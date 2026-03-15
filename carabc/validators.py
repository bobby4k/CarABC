from __future__ import annotations

from pathlib import Path
from typing import Any

from .exceptions import ValidationError
from .stages import get_stage_for_day, load_hanzi_set


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

    by_day: dict[int, dict[str, Any]] = {}
    seen_themes: set[str] = set()
    brand_names = config.get("rules", {}).get("brand_names", [])
    stages = config.get("stages", [])

    for item in themes_data["days"]:
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
        if item["theme_type"] not in ALLOWED_THEME_TYPES:
            raise ValidationError(f"第 {day} 天的 `theme_type` 非法: {item['theme_type']}")

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
            if "吉卜力" not in style:
                raise ValidationError(f"第 {day} 天属于规则/安全主题，应使用吉卜力风格")
        elif item["theme_type"] in {"brand", "car_model"}:
            if "写实" not in style and "实车" not in style:
                raise ValidationError(f"第 {day} 天属于品牌或车型主题，应使用写实风/实车风")
        elif "吉卜力" not in style:
            raise ValidationError(f"第 {day} 天的知识主题应使用吉卜力风格")

        combined_text = " ".join(
            [str(item["theme"]), str(item["cn_sentence"]), str(item["en_sentence"]), str(item["task"])]
        )
        if item["theme_type"] != "brand":
            for brand_name in brand_names:
                if brand_name in combined_text:
                    raise ValidationError(f"第 {day} 天不是品牌主题，但出现品牌名 `{brand_name}`")

        load_hanzi_set(expected_stage, root)
        by_day[day] = item
        seen_themes.add(item["theme"])

    missing_selected = [day for day in selected_days if day not in by_day]
    if missing_selected:
        raise ValidationError(f"所选天数缺少数据: {missing_selected}")
    return [by_day[day] for day in selected_days]
