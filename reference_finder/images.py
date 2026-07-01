"""키워드 → 상위 이미지 (Pexels 무료 API).

Pexels 는 프로젝트/사용설정 없이 키 1개만 발급하면 바로 쓰는 무료 이미지 API다.
키워드로 검색해 상위 N개 사진(썸네일 + 원본 페이지 링크)을 가져온다.

모든 실패(키 없음·오류·결과 없음)를 흡수하고 빈 리스트를 반환한다. 절대 예외를
위로 던지지 않는다 → 이미지 영역만 비고 검색 입구 링크(A)와 앱은 그대로 동작한다.
"""

from __future__ import annotations

import os

import requests

ENDPOINT = "https://api.pexels.com/v1/search"


def images_enabled() -> bool:
    """Pexels 키가 설정돼 있는지."""
    return bool(os.getenv("PEXELS_API_KEY"))


def fetch_keyword_images(
    keyword: str,
    *,
    limit: int = 3,
    timeout: int = 8,
) -> list[dict]:
    """키워드로 Pexels 에서 상위 이미지 N개를 가져온다.

    반환: [{"image": 썸네일URL, "link": 원본페이지URL, "title": ..., "credit": 작가}, ...]
          (실패하면 빈 리스트)
    """
    api_key = os.getenv("PEXELS_API_KEY")
    if not api_key:
        return []

    try:
        resp = requests.get(
            ENDPOINT,
            params={"query": keyword, "per_page": max(1, min(int(limit), 15))},
            headers={"Authorization": api_key},
            timeout=timeout,
        )
        if resp.status_code != 200:
            return []
        data = resp.json()
    except (requests.RequestException, ValueError):
        return []

    results: list[dict] = []
    for photo in (data.get("photos") or [])[:limit]:
        src = photo.get("src") or {}
        image_url = src.get("medium") or src.get("large") or src.get("original")
        if not image_url:
            continue
        results.append(
            {
                "image": image_url,
                "link": photo.get("url") or image_url,
                "title": photo.get("alt") or "",
                "credit": photo.get("photographer") or "",
            }
        )
    return results
