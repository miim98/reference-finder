"""이미지 → 핵심 키워드 추출 (Groq vision, 무료 API).

Groq 는 Google 과 무관한 무료 추론 API 로, 간단한 Bearer 키 1개로 쓴다.
Llama vision 모델에 이미지를 보내 핵심 키워드 N개를 JSON 으로 받는다.
(OpenAI 호환 chat/completions 형식)

모델이 코드펜스나 설명을 붙일 수 있어 응답을 방어적으로 파싱한다.
"""

from __future__ import annotations

import base64
import json
import os
import re

import requests

# 무료 vision 모델 (필요하면 GROQ_MODEL 환경변수로 교체)
MODEL = os.getenv("GROQ_MODEL", "meta-llama/llama-4-scout-17b-16e-instruct")
ENDPOINT = "https://api.groq.com/openai/v1/chat/completions"

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
        f"You are a visual design director. Analyze this image as a DESIGN REFERENCE and "
        f"produce exactly {n} short search keywords a designer would type into Pinterest or "
        f"Behance to find work in the SAME STYLE made with the SAME TECHNIQUES.\n\n"
        f"Prioritize these two categories (most of the {n} keywords should come from here):\n"
        f"1) STYLE — named aesthetics / design movements / genres. "
        f"(e.g. swiss design, brutalist, y2k, bauhaus, memphis, art deco, vaporwave, "
        f"editorial design, maximalist, retro futurism, acid graphics, minimalism)\n"
        f"2) TECHNIQUE / MEDIUM — how it was made or rendered. "
        f"(e.g. risograph, halftone, collage, photo manipulation, 3d render, isometric, "
        f"gradient mesh, cut-out paper, line art, glitch, double exposure, film grain, "
        f"screen print, vector illustration, hand-drawn)\n\n"
        f"Rules:\n"
        f"- Favor concrete STYLE names and TECHNIQUE/medium terms. Avoid vague adjectives "
        f"(cold, nice, beautiful) and avoid plain color-only words.\n"
        f"- Each: 1-3 words, English, lowercase, works as a search query.\n"
        f"- No duplicates.\n"
        f'- Respond with JSON only: {{"keywords": ["k1", "k2", ...]}} — no markdown, no extra text.\n'
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
    """이미지 바이트에서 키워드 n개를 추출한다 (Groq).

    실패 시 KeywordError 를 던진다(호출부에서 잡아 사용자에게 메시지로 전달).
    """
    resolved_type = SUPPORTED_MEDIA_TYPES.get(media_type.lower())
    if resolved_type is None:
        raise KeywordError(
            f"지원하지 않는 이미지 타입입니다: {media_type} (지원: PNG, JPEG, WebP, GIF)"
        )

    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise KeywordError("GROQ_API_KEY 가 설정되지 않았습니다. Render 환경변수를 확인하세요.")

    image_b64 = base64.standard_b64encode(image_bytes).decode("utf-8")
    data_url = f"data:{resolved_type};base64,{image_b64}"

    body = {
        "model": MODEL,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": _build_prompt(n)},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            }
        ],
        "temperature": 0.4,
        "max_tokens": 300,
    }

    try:
        resp = requests.post(
            ENDPOINT,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=body,
            timeout=30,
        )
    except requests.RequestException as exc:
        raise KeywordError(f"Groq 호출 실패: {exc}") from exc

    if resp.status_code != 200:
        detail = ""
        try:
            detail = resp.json().get("error", {}).get("message", "")
        except ValueError:
            detail = resp.text[:200]
        raise KeywordError(f"Groq 오류({resp.status_code}): {detail}")

    try:
        text = resp.json()["choices"][0]["message"]["content"]
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise KeywordError("Groq 응답을 해석하지 못했습니다.") from exc

    return _parse_keywords(text, n)
