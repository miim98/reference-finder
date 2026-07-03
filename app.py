"""레퍼런스 찾기 - Flask 진입점.

업로드한 이미지로 역방향 이미지 검색(Serper Lens)을 해서 시각적으로 비슷한
이미지 목록을 보여준다.

Lens 는 '이미지 URL'을 받으므로, 업로드 이미지를 이 앱이 임시로 서빙(/uploads/<name>)
하고 그 공개 URL을 Lens 에 넘긴다. 외부 이미지 호스팅이 필요 없다.
"""

from __future__ import annotations

import glob
import os
import tempfile
import time
import uuid

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request, send_from_directory

from reference_finder.images import reverse_image_search

load_dotenv()

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024  # 업로드 상한 10MB

UPLOAD_DIR = os.path.join(tempfile.gettempdir(), "rf_uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)
FILE_TTL = 600  # 임시 이미지 보관 시간(초)

EXT_BY_TYPE = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/gif": ".gif",
    "image/webp": ".webp",
}


def _cleanup_old_uploads() -> None:
    """오래된 임시 업로드 파일 삭제."""
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


@app.route("/api/reverse", methods=["POST"])
def reverse():
    """업로드 이미지 → 역방향 이미지 검색 → 비슷한 이미지 목록."""
    file = request.files.get("image")
    if file is None or not file.filename:
        return jsonify({"error": "이미지를 업로드해 주세요."}), 400

    image_bytes = file.read()
    if not image_bytes:
        return jsonify({"error": "빈 파일입니다."}), 400

    ext = EXT_BY_TYPE.get((file.mimetype or "").lower())
    if ext is None:
        return jsonify({"error": "지원하지 않는 이미지 타입입니다 (PNG/JPEG/GIF/WebP)."}), 400

    if not os.getenv("SERPER_API_KEY"):
        return jsonify({"error": "SERPER_API_KEY 가 없습니다. Render 환경변수를 확인하세요."}), 500

    # 1) 임시 저장 + 공개 URL 구성
    _cleanup_old_uploads()
    name = uuid.uuid4().hex + ext
    with open(os.path.join(UPLOAD_DIR, name), "wb") as f:
        f.write(image_bytes)

    host = request.host  # 예: reference-finder-dktr.onrender.com
    scheme = "http" if host.startswith(("127.", "localhost")) else "https"
    public_url = f"{scheme}://{host}/uploads/{name}"

    # 2) 역방향 이미지 검색
    results = reverse_image_search(public_url, limit=30, timeout=25)
    return jsonify({"images": results})


@app.errorhandler(413)
def too_large(_):
    return jsonify({"error": "파일이 너무 큽니다 (최대 10MB)."}), 413


if __name__ == "__main__":
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "5000"))
    app.run(host=host, port=port, debug=True)
