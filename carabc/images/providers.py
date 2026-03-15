from __future__ import annotations

import base64
import os
import time
from datetime import datetime
from typing import Any

import requests

from carabc.exceptions import ValidationError
from .base import ImageProvider


def _read_image_bytes_from_standard_response(data: dict[str, Any]) -> bytes:
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


class BailianQwenMultimodalProvider:
    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.name = str(config["name"])

    def generate(self, prompt: str) -> bytes:
        api_key = os.getenv(self.config["api_key_env"])
        if not api_key:
            raise ValidationError(f"缺少图片接口 API Key，请设置环境变量 `{self.config['api_key_env']}`")
        payload = {
            "model": self.config["model_name"],
            "input": {"messages": [{"role": "user", "content": [{"text": prompt}]}]},
            "parameters": {"size": self.config.get("size", "1024*1024")},
        }
        response = requests.post(
            self.config["base_url"],
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=payload,
            timeout=self.config.get("timeout_seconds", 180),
        )
        if not response.ok:
            detail = response.text.strip().replace("\n", " ")
            raise ValidationError(f"{response.status_code} {response.reason} for {self.name}: {detail[:300]}")
        choices = response.json().get("output", {}).get("choices", [])
        if not choices:
            raise ValidationError(f"千问文生图同步接口未返回 choices: {response.text}")
        content = choices[0].get("message", {}).get("content", [])
        for item in content:
            if isinstance(item, dict) and item.get("image"):
                image_response = requests.get(item["image"], timeout=120)
                image_response.raise_for_status()
                return image_response.content
        raise ValidationError(f"千问文生图同步接口未返回图片地址: {response.text}")


class BailianAsyncText2ImageProvider:
    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.name = str(config["name"])

    def generate(self, prompt: str) -> bytes:
        task_id = self._create_async_task(prompt)
        task_result = self._poll_async_task(task_id)
        return _read_image_bytes_from_standard_response(task_result)

    def _create_async_task(self, prompt: str) -> str:
        api_key = os.getenv(self.config["api_key_env"])
        if not api_key:
            raise ValidationError(f"缺少图片接口 API Key，请设置环境变量 `{self.config['api_key_env']}`")
        payload = {
            "model": self.config["model_name"],
            "input": {"prompt": prompt},
            "parameters": {"size": self.config.get("size", "1024*1024"), "n": self.config.get("n", 1)},
        }
        response = requests.post(
            self.config["base_url"],
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "X-DashScope-Async": "enable",
            },
            json=payload,
            timeout=self.config.get("timeout_seconds", 180),
        )
        if not response.ok:
            detail = response.text.strip().replace("\n", " ")
            raise ValidationError(f"{response.status_code} {response.reason} for {self.name}: {detail[:300]}")
        task_id = response.json().get("output", {}).get("task_id")
        if not task_id:
            raise ValidationError(f"异步图片接口未返回 task_id: {response.text}")
        return task_id

    def _poll_async_task(self, task_id: str) -> dict[str, Any]:
        api_key = os.getenv(self.config["api_key_env"])
        task_url = f"https://dashscope.aliyuncs.com/api/v1/tasks/{task_id}"
        start_time = datetime.now().timestamp()
        while True:
            response = requests.get(task_url, headers={"Authorization": f"Bearer {api_key}"}, timeout=60)
            if not response.ok:
                detail = response.text.strip().replace("\n", " ")
                raise ValidationError(f"查询任务失败 {response.status_code} {response.reason} for {self.name}: {detail[:300]}")
            data = response.json()
            status = data.get("output", {}).get("task_status")
            if status == "SUCCEEDED":
                return data
            if status in {"FAILED", "CANCELED", "UNKNOWN"}:
                output = data.get("output", {})
                raise ValidationError(f"异步任务失败 {self.name}: {output.get('code', '')} {output.get('message', '')}".strip())
            if datetime.now().timestamp() - start_time > self.config.get("timeout_seconds", 180):
                raise ValidationError(f"异步任务等待超时: {self.name} task_id={task_id}")
            time.sleep(3)


class GenericHttpProvider:
    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.name = str(config["name"])

    def generate(self, prompt: str) -> bytes:
        api_key = os.getenv(self.config["api_key_env"])
        if not api_key:
            raise ValidationError(f"缺少图片接口 API Key，请设置环境变量 `{self.config['api_key_env']}`")
        payload = {
            "model": self.config["model_name"],
            "input": {"prompt": prompt},
            "parameters": {"size": self.config.get("size", "512*512"), "n": self.config.get("n", 1)},
        }
        response = requests.post(
            self.config["base_url"],
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=payload,
            timeout=self.config.get("timeout_seconds", 60),
        )
        if not response.ok:
            detail = response.text.strip().replace("\n", " ")
            raise ValidationError(f"{response.status_code} {response.reason} for {self.name}: {detail[:300]}")
        return _read_image_bytes_from_standard_response(response.json())


class OpenAICompatibleImagesProvider:
    """兼容 OpenAI Images API 风格的平台示例。

    适用于如下接口风格：
    - POST {base_url}/images/generations
    - Authorization: Bearer <api_key>
    - 响应字段位于 data[0].url 或 data[0].b64_json

    配置示例：
      - name: demo-openai-images
        provider: custom
        api_mode: openai_images
        model_name: gpt-image-1
        api_key_env: OPENAI_API_KEY
        base_url: https://api.openai.com/v1
        size: 1024x1024
        timeout_seconds: 180
    """

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.name = str(config["name"])

    def generate(self, prompt: str) -> bytes:
        api_key = os.getenv(self.config["api_key_env"])
        if not api_key:
            raise ValidationError(f"缺少图片接口 API Key，请设置环境变量 `{self.config['api_key_env']}`")

        base_url = str(self.config["base_url"]).rstrip("/")
        url = f"{base_url}/images/generations"
        payload = {
            "model": self.config["model_name"],
            "prompt": prompt,
            "size": self.config.get("size", "1024x1024"),
        }
        if self.config.get("n"):
            payload["n"] = self.config["n"]

        response = requests.post(
            url,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=payload,
            timeout=self.config.get("timeout_seconds", 180),
        )
        if not response.ok:
            detail = response.text.strip().replace("\n", " ")
            raise ValidationError(f"{response.status_code} {response.reason} for {self.name}: {detail[:300]}")

        data = response.json().get("data", [])
        if not data or not isinstance(data[0], dict):
            raise ValidationError(f"OpenAI 兼容图片接口未返回 data: {response.text}")

        first = data[0]
        if first.get("url"):
            image_response = requests.get(first["url"], timeout=120)
            image_response.raise_for_status()
            return image_response.content
        if first.get("b64_json"):
            return base64.b64decode(first["b64_json"])
        raise ValidationError(f"OpenAI 兼容图片接口未返回图片地址或 b64_json: {response.text}")


def build_provider(config: dict[str, Any]) -> ImageProvider:
    api_mode = config.get("api_mode", "generic_http")
    if api_mode == "qwen_multimodal_sync":
        return BailianQwenMultimodalProvider(config)
    if api_mode == "dashscope_async_text2image":
        return BailianAsyncText2ImageProvider(config)
    if api_mode == "openai_images":
        return OpenAICompatibleImagesProvider(config)
    return GenericHttpProvider(config)
