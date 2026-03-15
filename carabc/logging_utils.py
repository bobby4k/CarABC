from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

from .models import ImageResult
from .utils import ensure_parent


def load_existing_log(log_file: Path) -> dict[int, dict[str, object]]:
    if not log_file.exists():
        return {}

    entries: dict[int, dict[str, object]] = {}
    for line in log_file.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        match = re.search(
            r"day=(\d+)\s*\|\s*theme=(.*?)\s*\|\s*stage=(.*?)\s*\|\s*image=(.*?)\s*\|\s*status=(.*?)\s*\|\s*model=(.*?)\s*\|\s*attempts=(.*?)\s*\|\s*quota_before=(.*?)\s*\|\s*quota_after=(.*?)\s*\|\s*pdf=(.*?)\s*\|\s*error=(.*)$",
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
            "model_used": match.group(6),
            "model_attempts": match.group(7),
            "quota_before": match.group(8),
            "quota_after": match.group(9),
            "pdf_included": match.group(10) == "yes",
            "error": match.group(11),
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
            "model_used": result.model_used,
            "model_attempts": ",".join(result.model_attempts or []),
            "quota_before": result.quota_before,
            "quota_after": result.quota_after,
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
                    str(item["generated_at"]),
                    f"day={item['day']}",
                    f"theme={item['theme']}",
                    f"stage={item['stage']}",
                    f"image={item['image_path']}",
                    f"status={item['image_status']}",
                    f"model={item['model_used']}",
                    f"attempts={item['model_attempts']}",
                    f"quota_before={item['quota_before']}",
                    f"quota_after={item['quota_after']}",
                    f"pdf={'yes' if item['pdf_included'] else 'no'}",
                    f"error={item['error']}",
                ]
            )
        )
    log_file.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def save_model_state(state_file: Path, model_state: dict[str, int] | None) -> None:
    if model_state is None:
        return
    ensure_parent(state_file)
    state_file.write_text(json.dumps(model_state, ensure_ascii=False, indent=2), encoding="utf-8")


def load_model_state(state_file: Path, image_models: list[dict[str, object]]) -> dict[str, int] | None:
    if not state_file.exists():
        return None
    data = json.loads(state_file.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"模型额度状态文件顶层必须是对象: {state_file}")
    expected_names = [str(model["name"]) for model in image_models]
    state: dict[str, int] = {}
    for name in expected_names:
        if name not in data:
            raise ValueError(f"模型额度状态缺少字段: {name}")
        value = data[name]
        if not isinstance(value, int) or value < 0:
            raise ValueError(f"模型额度必须是大于等于 0 的整数: {name}")
        state[name] = value
    return state
