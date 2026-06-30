"""이미지 → 핵심 키워드 추출 (Google Gemini vision, 무료 API).

이미지를 Gemini 에 보내 핵심 키워드 N개를 JSON 으로만 받는다.
무료 한도 안에서 카드 없이 사용 가능. (REST 직접 호출 → 추가 의존성 없음)

응답이 JSON 으로 오도록 responseMimeType 을 지정하고, 그래도 모델이 코드펜스나
설명을 붙일 수 있으니 방어적으로 파싱한다.
"""

from __future__ import annotations

import base64
import json
import os
import re

import requests

# 무료 vision 모델 (필요하면 GEMINI_MODEL 환경변수로 교체)
MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

# 허용 이미지 타입 (콘텐츠타입 → Gemini mime_type)
SUPPORTED_MEDIA_TYPES = {
    "image/png": "image/png",
    "image/jpeg": "image/jpeg",
    "image/jpg": "image/jpeg",
    "image/webp": "image/webp",
    "image/gif": "image/gif",
}


class KeywordError(Exception):
    """키워드 추출 단계에서 발생한 복구 가능한 오류."""


def _build_prompt(n: int) -> str:
    return (
        f"Look at this image and extract exactly {n} short search keywords that best "
        f"describe its visual style, subject, mood, color, and design characteristics. "
        f"The keywords will be used to search design reference sites like Pinterest and "
        f"Behance.\n"
        f"Rules:\n"
        f'- Respond with JSON only: {{"keywords": ["k1", "k2", ...]}}\n'
        f"- Each keyword: 1-3 words, English, lowercase, search-friendly.\n"
        f"- Exactly {n} keywords."
    )


def _parse_keywords(text: str, n: int) -> list[str]:
    """모델 응답 문자열에서 keywords 리스트를 방어적으로 추출한다."""
    raw = (text or "").strip()

    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", raw, re.DOTALL)
    if fence:
        raw = fence.group(1).strip()

    start, end = raw.find("{"), raw.rfind("}")
    candidate = raw[start : end + 1] if start != -1 and end != -1 else raw

    try:
        data = json.loads(candidate)
    except (json.JSONDecodeError, ValueError) as exc:
        raise KeywordError(f"키워드 JSON 파싱 실패: {exc}") from exc

    keywords = data.get("keywords") if isinstance(data, dict) else None
    if not isinstance(keywords, list) or not keywords:
        raise KeywordError("응답에 'keywords' 배열이 없습니다.")

    cleaned: list[str] = []
    for kw in keywords:
        if isinstance(kw, str) and kw.strip():
            v = kw.strip()
            if v.lower() not in (c.lower() for c in cleaned):
                cleaned.append(v)

    if not cleaned:
        raise KeywordError("유효한 키워드가 없습니다.")

    return cleaned[:n]


def extract_keywords(image_bytes: bytes, media_type: str, *, n: int = 5) -> list[str]:
    """이미지 바이트에서 키워드 n개를 추출한다 (Gemini).

    실패 시 KeywordError 를 던진다(호출부에서 잡아 사용자에게 메시지로 전달).
    """
    resolved_type = SUPPORTED_MEDIA_TYPES.get(media_type.lower())
    if resolved_type is None:
        raise KeywordError(
            f"지원하지 않는 이미지 타입입니다: {media_type} (지원: PNG, JPEG, WebP, GIF)"
        )

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise KeywordError("GEMINI_API_KEY 가 설정되지 않았습니다. Render 환경변수를 확인하세요.")

    image_b64 = base64.standard_b64encode(image_bytes).decode("utf-8")
    body = {
        "contents": [
            {
                "parts": [
                    {"inline_data": {"mime_type": resolved_type, "data": image_b64}},
                    {"text": _build_prompt(n)},
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": 256,
            "responseMimeType": "application/json",
        },
    }

    try:
        resp = requests.post(
            ENDPOINT.format(model=MODEL),
            params={"key": api_key},
            json=body,
            timeout=30,
        )
    except requests.RequestException as exc:
        raise KeywordError(f"Gemini 호출 실패: {exc}") from exc

    if resp.status_code != 200:
        detail = ""
        try:
            detail = resp.json().get("error", {}).get("message", "")
        except ValueError:
            detail = resp.text[:200]
        raise KeywordError(f"Gemini 오류({resp.status_code}): {detail}")

    try:
        data = resp.json()
        text = data["candidates"][0]["content"]["parts"][0]["text"]
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise KeywordError("Gemini 응답을 해석하지 못했습니다(차단 또는 빈 응답).") from exc

    return _parse_keywords(text, n)
