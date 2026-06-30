"""키워드 + 사이트 → 상위 이미지 결과 (Google Programmable Search, 이미지 검색).

"내가 등록한 사이트에 한정해서 키워드별 상위 이미지 N개"를 가져오는 모듈.
Google Custom Search JSON API 의 이미지 검색을 쓰고, `siteSearch` 로 특정 도메인에
한정한다. 무료 한도는 하루 100 쿼리.

모든 실패(키 없음·할당량 초과·네트워크 오류·결과 없음)를 흡수하고 빈 리스트를
반환한다. 절대 예외를 위로 던지지 않는다 → 이미지 영역만 비고 검색 입구 링크(A)와
앱 전체는 그대로 동작한다.
"""

from __future__ import annotations

import os

import requests

ENDPOINT = "https://www.googleapis.com/customsearch/v1"


def google_keys_present() -> bool:
    """Google 검색에 필요한 키 2개가 모두 설정돼 있는지."""
    return bool(os.getenv("GOOGLE_API_KEY") and os.getenv("GOOGLE_CSE_ID"))


def fetch_site_images(
    keyword: str,
    domain: str | None,
    *,
    limit: int = 3,
    timeout: int = 8,
) -> list[dict]:
    """특정 사이트(domain)에서 keyword 로 검색한 상위 이미지 N개.

    반환: [{"image": 썸네일URL, "link": 원본 페이지URL, "title": ...}, ...]
          (실패하면 빈 리스트)
    """
    api_key = os.getenv("GOOGLE_API_KEY")
    cse_id = os.getenv("GOOGLE_CSE_ID")
    if not api_key or not cse_id or not domain:
        return []

    params = {
        "key": api_key,
        "cx": cse_id,
        "q": keyword,
        "searchType": "image",
        "siteSearch": domain,
        "siteSearchFilter": "i",  # i = include (해당 도메인만)
        "num": max(1, min(int(limit), 10)),
        "safe": "active",
    }

    try:
        resp = requests.get(ENDPOINT, params=params, timeout=timeout)
        if resp.status_code != 200:
            # 403/429 = 할당량 초과/권한 등 → 조용히 비움
            return []
        data = resp.json()
    except (requests.RequestException, ValueError):
        return []

    items = data.get("items") or []
    results: list[dict] = []
    for it in items[:limit]:
        image_url = it.get("link")
        if not image_url:
            continue
        context = (it.get("image") or {}).get("contextLink") or image_url
        results.append(
            {
                "image": image_url,
                "link": context,
                "title": it.get("title", ""),
            }
        )
    return results
