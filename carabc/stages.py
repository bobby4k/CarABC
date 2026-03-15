from __future__ import annotations

from pathlib import Path
from typing import Any

from .exceptions import ValidationError


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
