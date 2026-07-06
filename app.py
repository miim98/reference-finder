"""레퍼런스 찾기 - Flask 진입점.

1) 이미지 업로드 → Groq vision 으로 키워드 추출
2) 키워드 클릭 → 등록한 사이트별로 그 키워드 이미지 상위 N개(Serper) 표시
"""

from __future__ import annotations

import os

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request

from reference_finder.images import fetch_references
from reference_finder.keywords import KeywordError, extract_keywords
from reference_finder.sites import build_search_url, load_config

load_dotenv()

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024  # 업로드 상한 10MB


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/keywords", methods=["POST"])
def keywords():
    """이미지 업로드 → Groq vision 으로 키워드 추출."""
    file = request.files.get("image")
    if file is None or not file.filename:
        return jsonify({"error": "이미지를 업로드해 주세요."}), 400

    image_bytes = file.read()
    if not image_bytes:
        return jsonify({"error": "빈 파일입니다."}), 400

    media_type = file.mimetype or "application/octet-stream"

    if not os.getenv("GROQ_API_KEY"):
        return jsonify({"error": "GROQ_API_KEY 가 없습니다. Render 환경변수를 확인하세요."}), 500

    try:
        result = extract_keywords(image_bytes, media_type, n=8)
    except KeywordError as exc:
        return jsonify({"error": str(exc)}), 502

    return jsonify({"keywords": result})


@app.route("/api/references")
def references():
    """키워드 → 등록 사이트별 상위 이미지(각 10개) + 검색 링크."""
    keyword = (request.args.get("keyword") or "").strip()
    if not keyword:
        return jsonify({"error": "키워드가 없습니다."}), 400

    try:
        config = load_config()
    except (OSError, ValueError) as exc:
        return jsonify({"error": f"설정 파일 오류: {exc}"}), 500

    sites_cfg = [
        {
            "name": s["name"],
            "domain": s.get("domain"),
            "search_url": build_search_url(s["search_url"], keyword),
        }
        for s in config.get("sites", [])
    ]
    site_results = fetch_references(
        keyword,
        sites_cfg,
        per_site=int(config.get("results_per_site", 10)),
        timeout=int(config.get("request_timeout", 8)),
    )

    return jsonify({"keyword": keyword, "sites": site_results})


@app.errorhandler(413)
def too_large(_):
    return jsonify({"error": "파일이 너무 큽니다 (최대 10MB)."}), 413


if __name__ == "__main__":
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "5000"))
    app.run(host=host, port=port, debug=True)
