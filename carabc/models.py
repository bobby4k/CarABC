from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ImageResult:
    day: int
    theme: str
    stage: str
    image_path: str
    image_status: str
    pdf_included: bool
    model_used: str = ""
    model_attempts: list[str] | None = None
    quota_before: str = ""
    quota_after: str = ""
    error: str = ""
