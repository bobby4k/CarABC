from __future__ import annotations

from typing import Protocol


class ImageProvider(Protocol):
    name: str

    def generate(self, prompt: str) -> bytes:
        ...
