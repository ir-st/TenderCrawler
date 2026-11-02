"""HTTP 响应解析工具。"""

from __future__ import annotations

import json

import requests


def response_text(resp: requests.Response) -> str:
    """获取响应文本，兼容 UTF-8 BOM。"""
    if not resp.encoding or resp.encoding.lower() in ("iso-8859-1", "ascii"):
        resp.encoding = resp.apparent_encoding or "utf-8"
    text = resp.text
    if text.startswith("\ufeff"):
        text = text[1:]
    return text.strip()


def _check_redirect_method_downgrade(resp: requests.Response, *, source: str) -> None:
    """检测 POST 被 301/302 重定向降级为 GET 的情况（常见于 http→https 跳转）。

    requests 跟随 301/302 时会把 POST 改为 GET，请求体随之丢失，
    服务端通常返回 success:false 的空壳响应，报错原因极难定位。
    """
    if resp.request.method != "GET":
        return
    for hop in resp.history:
        if hop.request.method == "POST" and hop.status_code in (301, 302, 303):
            raise RuntimeError(
                f"{source} 将 {hop.request.method} {hop.url} 以 {hop.status_code} "
                f"重定向到 {resp.url}，且请求被降级为 GET、参数丢失。"
                "请改用 https:// 地址直接请求，避免经过重定向。"
            )


def parse_json_response(resp: requests.Response, *, source: str = "平台") -> dict:
    """
    将 HTTP 响应解析为 JSON 对象。
    若返回 HTML / 空内容 / 非 JSON，抛出带说明的 RuntimeError。
    """
    _check_redirect_method_downgrade(resp, source=source)
    text = response_text(resp)
    if not text:
        raise RuntimeError(
            f"{source} 返回空内容（HTTP {resp.status_code}），"
            "请稍后重试或检查网络。"
        )
    lower = text.lower()
    if lower.startswith("<!doctype") or lower.startswith("<html") or "<html" in lower[:200]:
        if "频繁" in text or "访问过于频繁" in text:
            raise RuntimeError(
                f"{source} 提示访问过于频繁，请增大请求间隔后重试。"
            )
        raise RuntimeError(
            f"{source} 返回了网页而非数据（HTTP {resp.status_code}），"
            "可能被限流或拦截，请稍后重试。"
        )
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        preview = text[:200].replace("\n", " ")
        raise RuntimeError(
            f"{source} 响应不是合法 JSON：{exc}；内容开头：{preview!r}"
        ) from exc
    if not isinstance(data, dict):
        raise RuntimeError(f"{source} 响应格式异常（期望 JSON 对象）。")
    return data
