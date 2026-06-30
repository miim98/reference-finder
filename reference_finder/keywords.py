"""이미지 → 핵심 키워드 추출 (Claude vision, JSON-only 프롬프트).

요청대로 모델은 claude-sonnet-4-6 을 사용하고, 응답을 JSON 으로만 받도록
프롬프트를 구성한다. 모델이 가끔 코드펜스나 설명을 덧붙일 수 있으므로
응답을 방어적으로 파싱한다(코드펜스 제거 + 첫 '{' ~ 마지막 '}' 추출).
"""

from __future__ import annotations

import base64
import json
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # 타입 힌트용 — 실제 import 는 함수 안에서 (무료 모드는 anthropic 불필요)
    import anthropic

MODEL = "claude-sonnet-4-6"

# 허용 이미지 타입 (확장자/콘텐츠타입 → Anthropic media_type)
SUPPORTED_MEDIA_TYPES = {
    "image/png": "image/png",
    "image/jpeg": "image/jpeg",
    "image/jpg": "image/jpeg",
    "image/gif": "image/gif",
    "image/webp": "image/webp",
}


class KeywordError(Exception):
    """키워드 추출 단계에서 발생한 복구 가능한 오류."""


def _build_prompt(n: int) -> str:
    return (
        f"You are a visual reference assistant. Look at the image and extract exactly "
        f"{n} short search keywords that best describe its visual style, subject, mood, "
        f"and design characteristics. The keywords will be used to search design "
        f"reference sites like Pinterest and Behance.\n\n"
        f"Rules:\n"
        f"- Respond with JSON ONLY. No prose, no markdown, no code fences.\n"
        f'- Format: {{"keywords": ["keyword1", "keyword2", "keyword3"]}}\n'
        f"- Each keyword: 1-3 words, English, lowercase, search-friendly.\n"
        f"- Exactly {n} keywords."
    )


def _parse_keywords(text: str, n: int) -> list[str]:
    """모델 응답 문자열에서 keywords 리스트를 방어적으로 추출한다."""
    raw = text.strip()

    # 코드펜스 제거 (```json ... ``` 또는 ``` ... ```)
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", raw, re.DOTALL)
    if fence:
        raw = fence.group(1).strip()

    # 첫 '{' ~ 마지막 '}' 만 떼어 파싱 시도
    start, end = raw.find("{"), raw.rfind("}")
    candidate = raw[start : end + 1] if start != -1 and end != -1 else raw

    try:
        data = json.loads(candidate)
    except (json.JSONDecodeError, ValueError) as exc:
        raise KeywordError(f"키워드 JSON 파싱 실패: {exc}") from exc

    keywords = data.get("keywords") if isinstance(data, dict) else None
    if not isinstance(keywords, list) or not keywords:
        raise KeywordError("응답에 'keywords' 배열이 없습니다.")

    # 문자열만 남기고 정리/중복 제거
    cleaned: list[str] = []
    for kw in keywords:
        if isinstance(kw, str) and kw.strip():
            v = kw.strip()
            if v.lower() not in (c.lower() for c in cleaned):
                cleaned.append(v)

    if not cleaned:
        raise KeywordError("유효한 키워드가 없습니다.")

    return cleaned[:n]


def extract_keywords(
    image_bytes: bytes,
    media_type: str,
    *,
    n: int = 3,
    client: anthropic.Anthropic | None = None,
) -> list[str]:
    """이미지 바이트에서 키워드 n개를 추출한다.

    실패 시 KeywordError 를 던진다(호출부에서 잡아 사용자에게 메시지로 전달).
    """
    resolved_type = SUPPORTED_MEDIA_TYPES.get(media_type.lower())
    if resolved_type is None:
        raise KeywordError(
            f"지원하지 않는 이미지 타입입니다: {media_type} "
            f"(지원: PNG, JPEG, GIF, WebP)"
        )

    try:
        import anthropic  # 이미지 분석 시에만 필요 (무료 키워드 모드는 불필요)
    except ImportError as exc:
        raise KeywordError(
            "anthropic 패키지가 없습니다. 'pip install -r requirements.txt' 후 사용하세요."
        ) from exc

    client = client or anthropic.Anthropic()
    image_b64 = base64.standard_b64encode(image_bytes).decode("utf-8")

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=256,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": resolved_type,
                                "data": image_b64,
                            },
                        },
                        {"type": "text", "text": _build_prompt(n)},
                    ],
                }
            ],
        )
    except anthropic.APIError as exc:
        raise KeywordError(f"Claude API 호출 실패: {exc}") from exc

    text = next((b.text for b in response.content if b.type == "text"), "")
    if not text:
        raise KeywordError("Claude 응답이 비어 있습니다.")

    return _parse_keywords(text, n)
