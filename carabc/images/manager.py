from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image

from carabc.exceptions import ValidationError
from carabc.logging_utils import save_model_state
from carabc.models import ImageResult
from carabc.utils import ensure_parent
from .providers import build_provider


def save_image(image_bytes: bytes, image_path: Path) -> None:
    ensure_parent(image_path)
    with Image.open(BytesIO(image_bytes)) as img:
        img.convert("RGB").save(image_path, format="JPEG", quality=95)


def request_image_with_fallback(
    prompt: str,
    config: dict[str, Any],
    model_state: dict[str, int] | None,
    state_file: Path,
) -> tuple[bytes, str, list[str], str, str]:
    image_models = config.get("image_models", [])
    if not image_models:
        raise ValidationError("config.yaml 中未配置 image_models")

    attempts: list[str] = []
    errors: list[str] = []
    for image_model in image_models:
        model_name = image_model["name"]
        attempts.append(model_name)
        quota_before = "unlimited"
        quota_after = "unlimited"
        if model_state is not None:
            remaining = model_state[model_name]
            quota_before = str(remaining)
            if remaining <= 0:
                errors.append(f"{model_name}: quota exhausted")
                continue

        try:
            image_bytes = build_provider(image_model).generate(prompt)
            if model_state is not None:
                model_state[model_name] -= 1
                quota_after = str(model_state[model_name])
                save_model_state(state_file, model_state)
            return image_bytes, model_name, attempts, quota_before, quota_after
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{model_name}: {exc}")
    raise ValidationError("; ".join(errors) if errors else "所有图片模型均不可用")


def process_image(
    item: dict[str, Any],
    config: dict[str, Any],
    root: Path,
    force: bool,
    model_state: dict[str, int] | None,
    state_file: Path,
) -> ImageResult:
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
            model_attempts=[],
        )

    try:
        image_bytes, model_used, attempts, quota_before, quota_after = request_image_with_fallback(
            item["image_prompt"],
            config,
            model_state,
            state_file,
        )
        save_image(image_bytes, image_path)
        return ImageResult(
            day=item["day"],
            theme=item["theme"],
            stage=item["stage"],
            image_path=item["image_path"],
            image_status="regenerated" if force and existed_before else "generated",
            pdf_included=True,
            model_used=model_used,
            model_attempts=attempts,
            quota_before=quota_before,
            quota_after=quota_after,
        )
    except Exception as exc:  # noqa: BLE001
        return ImageResult(
            day=item["day"],
            theme=item["theme"],
            stage=item["stage"],
            image_path=item["image_path"],
            image_status="failed",
            pdf_included=config["pdf"].get("allow_missing_image", True),
            model_attempts=[model["name"] for model in config.get("image_models", [])],
            error=str(exc),
        )
