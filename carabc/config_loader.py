from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .exceptions import ValidationError


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
