"""상위 결과(B) best-effort 추출.

검색 결과 페이지의 HTML 을 받아, config 의 link_pattern(정규식)에 맞는
링크를 상위 N개 긁어온다. 이 단계는 본질적으로 깨지기 쉽다:

- Pinterest/Behance 등은 결과를 JS 로 렌더링하므로 첫 HTML 에 결과가 없을 수 있다.
- 사이트 구조가 바뀌면 패턴이 안 맞을 수 있다.
- 차단/타임아웃이 날 수 있다.

따라서 **모든 실패를 흡수하고 빈 리스트를 반환**한다. 절대 예외를 위로 던지지 않는다.
호출부(A)는 이 함수의 성공 여부와 무관하게 검색 입구 링크를 유지한다.
"""

from __future__ import annotations

import re
from urllib.parse import urljoin

import requests

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)


def _label_from_url(url: str) -> str:
    """URL 마지막 의미 있는 조각을 사람이 읽을 라벨로 변환 (없으면 URL 그대로)."""
    slug = url.rstrip("/").rsplit("/", 1)[-1]
    slug = re.sub(r"^\d+-?", "", slug)  # 앞쪽 숫자 ID 제거
    label = slug.replace("-", " ").replace("_", " ").strip()
    return label[:60] if label else url


def extract_top_results(
    search_url: str,
    extract_cfg: dict | None,
    *,
    limit: int = 5,
    timeout: int = 8,
) -> list[dict]:
    """검색 페이지에서 상위 결과 링크를 추출한다.

    반환: [{"url": ..., "label": ...}, ...]  (실패하면 빈 리스트)
    """
    if not extract_cfg or not extract_cfg.get("enabled"):
        return []

    pattern = extract_cfg.get("link_pattern")
    if not pattern:
        return []

    base_url = extract_cfg.get("base_url", search_url)

    try:
        resp = requests.get(
            search_url,
            headers={"User-Agent": USER_AGENT, "Accept-Language": "en,ko;q=0.8"},
            timeout=timeout,
        )
        resp.raise_for_status()
        html = resp.text
    except requests.RequestException:
        # 네트워크 오류/차단/타임아웃 → B 만 비우고 조용히 포기
        return []

    try:
        compiled = re.compile(pattern)
    except re.error:
        # config 의 정규식이 잘못된 경우 → B 만 비움
        return []

    results: list[dict] = []
    seen: set[str] = set()

    try:
        for match in compiled.finditer(html):
            path = match.group(0)
            url = urljoin(base_url, path)
            if url in seen:
                continue
            seen.add(url)
            results.append({"url": url, "label": _label_from_url(url)})
            if len(results) >= limit:
                break
    except Exception:
        # 파싱 중 예상 못한 오류도 흡수
        return results

    return results
