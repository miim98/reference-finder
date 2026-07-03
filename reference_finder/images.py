"""키워드 → 등록 사이트별 상위 레퍼런스 (DuckDuckGo 검색 + OG 이미지).

각 사이트(domain)에 대해 DuckDuckGo HTML 검색으로 `키워드 site:domain` 상위 결과의
상세페이지 링크를 얻고, 각 페이지의 og:image(대표 이미지)를 뽑아 썸네일로 쓴다.
API 키가 전혀 필요 없다.

best-effort: 검색 차단·결과 없음·OG 없음 등 모든 실패를 흡수하고 빈 리스트를 반환한다.
절대 예외를 위로 던지지 않는다 → 이미지가 비어도 '검색 열기' 링크와 앱은 그대로.
"""

from __future__ import annotations

import html as html_mod
import re
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote, unquote

import requests

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)
DDG_ENDPOINT = "https://html.duckduckgo.com/html/"

_OG_PATTERNS = [
    r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)',
    r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',
    r'<meta[^>]+name=["\']twitter:image["\'][^>]+content=["\']([^"\']+)',
]


def _ddg_links(keyword: str, domain: str, limit: int, timeout: int) -> list[str]:
    """DuckDuckGo HTML 검색으로 site:domain 상위 결과 링크(중복 제거)."""
    try:
        resp = requests.get(
            DDG_ENDPOINT,
            params={"q": f"{keyword} site:{domain}"},
            headers={"User-Agent": UA},
            timeout=timeout,
        )
        if resp.status_code != 200:
            return []
        page = resp.text
    except requests.RequestException:
        return []

    out: list[str] = []
    seen: set[str] = set()
    for raw in re.findall(r"uddg=([^\"&]+)", page):
        url = unquote(raw)
        if domain not in url or url in seen:
            continue
        seen.add(url)
        out.append(url)
        if len(out) >= limit:
            break
    return out


def _og_image(url: str, timeout: int) -> str | None:
    """상세페이지의 og:image(없으면 twitter:image) URL."""
    try:
        resp = requests.get(url, headers={"User-Agent": UA}, timeout=timeout)
        if resp.status_code != 200:
            return None
        page = resp.text
    except requests.RequestException:
        return None

    for pat in _OG_PATTERNS:
        m = re.search(pat, page, re.IGNORECASE)
        if m:
            return html_mod.unescape(m.group(1))
    return None


def fetch_references(
    keyword: str,
    sites: list[dict],
    *,
    per_site: int = 3,
    timeout: int = 6,
) -> list[dict]:
    """키워드에 대해 사이트별 상위 레퍼런스(링크 + OG 이미지)를 병렬로 수집.

    sites: [{"name", "domain", "search_url"}, ...] (search_url 은 이미 완성된 링크)
    반환:  [{"name", "search_url", "images": [{"link", "image"}, ...]}, ...]
    """
    # 1) 사이트별 DDG 결과 링크 (병렬)
    def _links(site: dict):
        domain = site.get("domain")
        return _ddg_links(keyword, domain, per_site, timeout) if domain else []

    with ThreadPoolExecutor(max_workers=max(1, len(sites))) as ex:
        links_per_site = list(ex.map(_links, sites))

    # 2) 모든 (사이트index, 링크)에 대해 OG 이미지 병렬 수집
    tasks: list[tuple[int, str]] = []
    for si, links in enumerate(links_per_site):
        for link in links:
            tasks.append((si, link))

    images_by_site: dict[int, list[dict]] = {i: [] for i in range(len(sites))}
    if tasks:
        def _og(task: tuple[int, str]):
            si, link = task
            return si, link, _og_image(link, timeout)

        with ThreadPoolExecutor(max_workers=min(8, len(tasks))) as ex:
            for si, link, img in ex.map(_og, tasks):
                if img:
                    images_by_site[si].append({"link": link, "image": img})

    # 3) 결과 조립
    out: list[dict] = []
    for i, site in enumerate(sites):
        out.append(
            {
                "name": site["name"],
                "search_url": site["search_url"],
                "images": images_by_site[i],
            }
        )
    return out
