"""키워드 → 등록 사이트별 상위 레퍼런스 (Serper.dev 이미지 검색).

각 사이트(domain)에 대해 `키워드 site:domain` 으로 Serper 이미지 검색을 하고,
결과의 썸네일 이미지 + 결과 페이지 링크를 카드로 쓴다. Serper 는 클라우드(데이터센터)
에서도 잘 동작해 Render 배포에서도 이미지가 뜬다.

best-effort: 키 없음·오류·결과 없음 등 모든 실패를 흡수하고 빈 리스트를 반환한다.
이미지가 비어도 프런트는 '검색 결과 열기' 카드로 폴백한다.
"""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor

import requests

ENDPOINT = "https://google.serper.dev/images"


def images_enabled() -> bool:
    """Serper 키가 설정돼 있는지."""
    return bool(os.getenv("SERPER_API_KEY"))


def _site_images(keyword: str, domain: str | None, limit: int, timeout: int) -> list[dict]:
    """특정 사이트에서 키워드로 검색한 상위 이미지 결과."""
    api_key = os.getenv("SERPER_API_KEY")
    if not api_key or not domain:
        return []

    try:
        resp = requests.post(
            ENDPOINT,
            headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
            json={"q": f"{keyword} site:{domain}", "num": max(1, min(int(limit), 10))},
            timeout=timeout,
        )
        if resp.status_code != 200:
            return []
        data = resp.json()
    except (requests.RequestException, ValueError):
        return []

    out: list[dict] = []
    for it in (data.get("images") or [])[:limit]:
        image = it.get("thumbnailUrl") or it.get("imageUrl")
        link = it.get("link") or image
        if not image:
            continue
        out.append({"image": image, "link": link})
    return out


def fetch_references(
    keyword: str,
    sites: list[dict],
    *,
    per_site: int = 3,
    timeout: int = 8,
) -> list[dict]:
    """키워드에 대해 사이트별 상위 레퍼런스(이미지 + 링크)를 병렬로 수집.

    sites: [{"name", "domain", "search_url"}, ...] (search_url 은 이미 완성된 링크)
    반환:  [{"name", "search_url", "images": [{"image", "link"}, ...]}, ...]
    """
    def _work(site: dict) -> dict:
        images = _site_images(keyword, site.get("domain"), per_site, timeout)
        return {"name": site["name"], "search_url": site["search_url"], "images": images}

    if not sites:
        return []
    with ThreadPoolExecutor(max_workers=max(1, len(sites))) as ex:
        return list(ex.map(_work, sites))
