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
LENS_ENDPOINT = "https://google.serper.dev/lens"

# 역방향 검색 결과에서 걸러낼 쇼핑/마켓플레이스 도메인 (디자인 레퍼런스와 무관)
_BLOCKED_DOMAINS = (
    "amazon.", "aliexpress.", "temu.com", "alibaba.com", "1688.com", "ebay.",
    "walmart.", "etsy.com", "wish.com", "shopee.", "lazada.", "coupang.com",
    "aliimg.com", "made-in-china.com", "dhgate.com", "wayfair.", "target.com",
)


def _is_blocked(link: str) -> bool:
    low = link.lower()
    return any(b in low for b in _BLOCKED_DOMAINS)


def images_enabled() -> bool:
    """Serper 키가 설정돼 있는지."""
    return bool(os.getenv("SERPER_API_KEY"))


def reverse_image_search(image_url: str, *, limit: int = 30, timeout: int = 25) -> list[dict]:
    """업로드 이미지 URL로 역방향 이미지 검색(Serper Lens) → 시각적으로 비슷한 이미지 목록.

    반환: [{"image", "link", "title", "source"}, ...] (실패하면 빈 리스트)
    """
    api_key = os.getenv("SERPER_API_KEY")
    if not api_key or not image_url:
        return []

    try:
        resp = requests.post(
            LENS_ENDPOINT,
            headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
            json={"url": image_url},
            timeout=timeout,
        )
        if resp.status_code != 200:
            return []
        data = resp.json()
    except (requests.RequestException, ValueError):
        return []

    out: list[dict] = []
    seen: set[str] = set()
    for it in (data.get("organic") or []):
        link = it.get("link") or ""
        # 안 깨지는 gstatic 썸네일 우선 (표시용). 링크는 원본 페이지.
        image = it.get("thumbnailUrl") or it.get("imageUrl")
        if not image or not link or image in seen:
            continue
        if _is_blocked(link):  # 쇼핑/마켓 결과 제외
            continue
        seen.add(image)
        out.append(
            {
                "image": image,
                "link": link,
                "title": it.get("title") or "",
                "source": it.get("source") or "",
            }
        )
        if len(out) >= limit:
            break
    return out


def _site_images(
    keyword: str, domain: str | None, limit: int, timeout: int, recency: str = ""
) -> list[dict]:
    """특정 사이트에서 키워드로 검색한 상위 이미지 결과.

    recency: "" 이면 전체 기간, "y"/"m"/"w" 면 최근 1년/1개월/1주 결과 우선(옛날 것 배제).
    """
    api_key = os.getenv("SERPER_API_KEY")
    if not api_key or not domain:
        return []

    body: dict = {"q": f"{keyword} site:{domain}", "num": max(1, min(int(limit), 10))}
    if recency:
        body["tbs"] = f"qdr:{recency}"  # Google 시간 필터 (최근 것 우선)

    try:
        resp = requests.post(
            ENDPOINT,
            headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
            json=body,
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
    recency: str = "",
) -> list[dict]:
    """키워드에 대해 사이트별 상위 레퍼런스(이미지 + 링크)를 병렬로 수집.

    sites: [{"name", "domain", "search_url"}, ...] (search_url 은 이미 완성된 링크)
    recency: "" 전체 / "y","m","w" 최근 우선.
    반환:  [{"name", "search_url", "images": [{"image", "link"}, ...]}, ...]
    """
    def _work(site: dict) -> dict:
        images = _site_images(keyword, site.get("domain"), per_site, timeout, recency)
        return {"name": site["name"], "search_url": site["search_url"], "images": images}

    if not sites:
        return []
    with ThreadPoolExecutor(max_workers=max(1, len(sites))) as ex:
        return list(ex.map(_work, sites))
