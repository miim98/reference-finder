"""레퍼런스 찾기 - Flask 진입점.

이미지를 업로드하면 두 가지를 동시에 보여준다:
1) 역방향 이미지 검색 — 이 이미지와 시각적으로 비슷한 이미지 (웹 전체, Serper Lens)
2) 키워드 → 내 등록 사이트별 상위 이미지 10개씩 (Groq 키워드 + Serper 이미지)

Lens 는 '이미지 URL'을 받으므로 업로드 이미지를 이 앱이 /uploads/<name> 로 임시 서빙한다.
"""

from __future__ import annotations

import glob
import os
import tempfile
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request, send_from_directory

from reference_finder.images import fetch_references, reverse_image_search
from reference_finder.keywords import KeywordError, extract_keywords
from reference_finder.sites import build_search_url, load_config

load_dotenv()

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024  # 업로드 상한 10MB

UPLOAD_DIR = os.path.join(tempfile.gettempdir(), "rf_uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)
FILE_TTL = 600

EXT_BY_TYPE = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/gif": ".gif",
    "image/webp": ".webp",
}


def _cleanup_old_uploads() -> None:
    now = time.time()
    for path in glob.glob(os.path.join(UPLOAD_DIR, "*")):
        try:
            if now - os.path.getmtime(path) > FILE_TTL:
                os.remove(path)
        except OSError:
            pass


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/uploads/<name>")
def uploaded_file(name: str):
    """Serper Lens 가 가져갈 수 있도록 업로드 이미지를 임시로 서빙."""
    return send_from_directory(UPLOAD_DIR, name)


@app.route("/api/analyze", methods=["POST"])
def analyze():
    """업로드 이미지 → (1) 역방향 비슷한 이미지 + (2) 키워드 동시 반환."""
    file = request.files.get("image")
    if file is None or not file.filename:
        return jsonify({"error": "이미지를 업로드해 주세요."}), 400

    image_bytes = file.read()
    if not image_bytes:
        return jsonify({"error": "빈 파일입니다."}), 400

    media_type = (file.mimetype or "").lower()
    ext = EXT_BY_TYPE.get(media_type)
    if ext is None:
        return jsonify({"error": "지원하지 않는 이미지 타입입니다 (PNG/JPEG/GIF/WebP)."}), 400

    # 역방향 검색용: 임시 저장 + 공개 URL
    _cleanup_old_uploads()
    name = uuid.uuid4().hex + ext
    with open(os.path.join(UPLOAD_DIR, name), "wb") as f:
        f.write(image_bytes)
    host = request.host
    scheme = "http" if host.startswith(("127.", "localhost")) else "https"
    public_url = f"{scheme}://{host}/uploads/{name}"

    def _keywords():
        if not os.getenv("GROQ_API_KEY"):
            return {"keywords": [], "error": "GROQ_API_KEY 미설정"}
        try:
            return {"keywords": extract_keywords(image_bytes, media_type, n=8)}
        except KeywordError as exc:
            return {"keywords": [], "error": str(exc)}

    def _similar():
        return reverse_image_search(public_url, limit=40, timeout=20)

    # 키워드 추출 + 역방향 검색 병렬
    with ThreadPoolExecutor(max_workers=2) as ex:
        fut_kw = ex.submit(_keywords)
        fut_sim = ex.submit(_similar)
        kw = fut_kw.result()
        similar = fut_sim.result()

    return jsonify(
        {
            "keywords": kw.get("keywords", []),
            "keyword_error": kw.get("error"),
            "similar": similar,
        }
    )


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
