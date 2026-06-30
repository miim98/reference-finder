"""레퍼런스 찾기 - Flask 진입점.

라우팅과 에러 핸들링만 담당한다. 핵심 로직은 reference_finder 패키지에 있다.
어떤 단계가 실패해도 앱 전체가 500 으로 죽지 않도록 JSON 에러로 감싼다.
"""

from __future__ import annotations

import os
import re

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request

from reference_finder.images import fetch_site_images, google_keys_present
from reference_finder.keywords import KeywordError, extract_keywords
from reference_finder.sites import build_search_url, load_config

load_dotenv()

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024  # 업로드 상한 10MB


@app.route("/")
def index():
    return render_template("index.html")


def _build_results(keywords: list[str], config: dict) -> list[dict]:
    """키워드 목록 → 키워드 × 사이트 결과.

    각 사이트마다:
      - search_url : 검색 입구 링크(A). 항상 생성 (외부 의존 없음).
      - images     : 등록 사이트에서 키워드로 검색한 상위 N개 이미지(Google). best-effort.
    이미지 검색이 실패해도 빈 리스트만 반환 → A 링크와 앱은 그대로.
    """
    per_site = int(config.get("results_per_site", 3))
    timeout = int(config.get("request_timeout", 8))
    sites = config.get("sites", [])
    images_enabled = google_keys_present()

    results = []
    for keyword in keywords:
        site_results = []
        for site in sites:
            search_url = build_search_url(site["search_url"], keyword)  # (A) 항상 성공
            domain = site.get("domain")

            images = fetch_site_images(
                keyword, domain, limit=per_site, timeout=timeout
            )  # (B) 실패해도 [] (예외 안 던짐)

            site_results.append(
                {
                    "name": site["name"],
                    "homepage": site.get("homepage"),
                    "search_url": search_url,
                    "images": images,
                    "image_search_enabled": bool(images_enabled and domain),
                }
            )

        results.append({"keyword": keyword, "sites": site_results})

    return results


@app.route("/api/search", methods=["POST"])
def search():
    """이미지 업로드 → Gemini vision 으로 키워드 5개 자동 추출."""
    # 1) 업로드 검증
    file = request.files.get("image")
    if file is None or not file.filename:
        return jsonify({"error": "이미지를 업로드해 주세요."}), 400

    image_bytes = file.read()
    if not image_bytes:
        return jsonify({"error": "빈 파일입니다."}), 400

    media_type = file.mimetype or "application/octet-stream"

    # 2) 설정 로드 (매 요청마다 → sites.json 수정이 재시작으로 반영)
    try:
        config = load_config()
    except (OSError, ValueError) as exc:
        return jsonify({"error": f"설정 파일을 읽을 수 없습니다: {exc}"}), 500

    # 3) 키워드 추출 (실패하면 여기서 중단하고 에러 반환 — 단, 앱은 죽지 않음)
    if not os.getenv("GEMINI_API_KEY"):
        return jsonify({
            "error": "GEMINI_API_KEY 가 없습니다. Render 환경변수에 무료 Gemini 키를 넣어주세요."
        }), 500

    n = int(config.get("max_keywords", 5))
    try:
        keywords = extract_keywords(image_bytes, media_type, n=n)
    except KeywordError as exc:
        return jsonify({"error": str(exc)}), 502

    return jsonify({"keywords": keywords, "results": _build_results(keywords, config)})


@app.route("/api/search-keywords", methods=["POST"])
def search_keywords():
    """키워드 직접 입력 → 검색 링크/결과만 생성. API 키·과금 없음 (완전 무료)."""
    data = request.get_json(silent=True) or {}
    raw = data.get("keywords", "")

    # 콤마/줄바꿈 구분, 공백 제거, 중복 제거
    parts = [p.strip() for p in re.split(r"[,\n]", str(raw)) if p.strip()]
    keywords: list[str] = []
    for p in parts:
        if p.lower() not in (k.lower() for k in keywords):
            keywords.append(p)

    if not keywords:
        return jsonify({"error": "키워드를 1개 이상 입력해 주세요 (콤마로 구분)."}), 400

    try:
        config = load_config()
    except (OSError, ValueError) as exc:
        return jsonify({"error": f"설정 파일을 읽을 수 없습니다: {exc}"}), 500

    n = int(config.get("max_keywords", 5))
    keywords = keywords[:n]

    return jsonify({"keywords": keywords, "results": _build_results(keywords, config)})


@app.errorhandler(413)
def too_large(_):
    return jsonify({"error": "파일이 너무 큽니다 (최대 10MB)."}), 413


if __name__ == "__main__":
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "5000"))
    app.run(host=host, port=port, debug=True)
