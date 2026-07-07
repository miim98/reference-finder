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
        f"A designer wants to find reference images that LOOK LIKE this uploaded image on "
        f"Pinterest or Behance. Give the {n} search queries that would actually return images "
        f"with the same look.\n\n"
        f"STEP 1 — Identify the MEDIUM (most important). Is the image a PHOTOGRAPH, an "
        f"ILLUSTRATION / drawing, a 3D render, or a GRAPHIC / typographic design?\n\n"
        f"STEP 2 — Every query MUST match that medium, so results are the SAME TYPE of image:\n"
        f"- If ILLUSTRATION / drawing / graphic: use words like 'illustration', 'illustrated "
        f"poster', 'character illustration', 'digital art', 'graphic poster', 'vector art', "
        f"'drawn'. NEVER use 'photography', 'photo', 'photoshoot', or a bare 'portrait' — those "
        f"return real people/photos.\n"
        f"- If PHOTOGRAPH: photographic terms are fine ('... photography', 'portrait photography', "
        f"'film photo').\n"
        f"- If 3D: '3d render', 'cgi', 'octane render', etc.\n\n"
        f"STEP 3 — Combine the medium with the dominant EFFECT / TECHNIQUE and TEXTURE "
        f"(e.g. blur, fog/haze, diffusion, grain, halftone, risograph, flat, gradient, collage) "
        f"and mood — so each query is concrete, e.g. \"blurred portrait illustration\", "
        f"\"grainy risograph poster\", \"hazy film portrait\", \"flat vector poster\".\n\n"
        f"BANNED — never output abstract words that return the wrong results:\n"
        f"- NO 'muted color palette' / 'color palette' (returns swatch charts)\n"
        f"- NO 'low contrast images' / 'high contrast' (returns tutorials/comparisons)\n"
        f"- NO bare 'skin', 'monochrome skin' (returns skincare / game skins)\n"
        f"- NO 'typewriter font' or any '... font' (returns font specimens)\n\n"
        f"Also: ignore any text written in the image. 2-4 words each, english, lowercase, "
        f"prioritize technique/texture, no near-duplicates.\n"
        f'Respond with JSON only: {{"keywords": ["q1", "q2", ...]}} — no markdown. Exactly {n} queries.'
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
