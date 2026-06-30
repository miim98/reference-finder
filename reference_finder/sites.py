"""사이트 설정 로드 + 검색 입구 링크(A) 생성.

(A)는 외부 네트워크 의존이 전혀 없다. config 의 search_url 템플릿에
URL 인코딩한 키워드를 끼워넣기만 하므로 항상 성공한다.
"""

from __future__ import annotations

import json
import os
from urllib.parse import quote

CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "config",
    "sites.json",
)

DEFAULTS = {
    "max_keywords": 3,
    "results_per_site": 5,
    "request_timeout": 8,
    "sites": [],
}


def load_config(path: str = CONFIG_PATH) -> dict:
    """sites.json 을 읽어 기본값과 병합한다. 매 요청마다 호출 → 수정 시 재시작만으로 반영."""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    config = {**DEFAULTS, **data}
    config["sites"] = data.get("sites", [])
    return config


def build_search_url(search_url_template: str, keyword: str) -> str:
    """검색 입구 링크(A) 생성. {query} 자리에 URL 인코딩된 키워드를 넣는다."""
    return search_url_template.replace("{query}", quote(keyword))
