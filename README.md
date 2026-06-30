# 레퍼런스 찾기 (Reference Finder)

이미지를 업로드하면 Claude가 **핵심 키워드 3개**를 뽑고, 등록된 레퍼런스 사이트(기본: Pinterest, Behance)에서
키워드별로 **검색 입구 링크**를 만들어 줍니다. 가능하면 검색 결과 상위 항목의 개별 링크도 함께 가져옵니다.

핵심 설계 원칙은 **"깨져도 죽지 않는다"** 입니다. 사이트 구조가 바뀌어 결과 추출(B)이 실패해도,
검색 입구 링크(A)는 항상 살아 있고 앱 전체가 멈추지 않습니다.

---

## 동작 흐름

```
[이미지 업로드]
      │
      ▼
[Claude API (claude-sonnet-4-6)]  ── 이미지 → 키워드 3개 (JSON only)
      │
      ▼
[각 키워드 × 각 사이트]
      ├─ (A) 검색 입구 링크 생성        ← 항상 성공 (실패해도 단순 문자열)
      └─ (B) 상위 결과 N개 추출 시도     ← 실패하면 빈 배열, A는 유지
      │
      ▼
[키워드별 / 사이트별 카드 UI]
```

- **(A) 검색 입구 링크**: `config/sites.json`의 `search_url` 템플릿에 키워드를 끼워 만든 URL. 네트워크/외부 의존 없음 → 항상 표시.
- **(B) 상위 이미지**: 등록 사이트(`domain`)에 한정해 **Google Programmable Search(이미지 검색)**로 키워드별 상위 N개 이미지를 가져옴. **베스트 에포트(best-effort)** — 키 미설정·할당량 초과·결과 없음이면 해당 영역만 비고 A는 그대로 둠.
  - (지정 사이트 직접 크롤링은 JS 렌더링 + 데이터센터 IP 차단 + 약관 때문에 서버에서 불가 → Google 검색 API를 경유)

---

## 프로젝트 구조

```
reference-finder/
├── README.md
├── requirements.txt
├── .env.example              # ANTHROPIC_API_KEY 등 환경변수 예시
├── .gitignore
├── config/
│   └── sites.json            # 레퍼런스 사이트 목록 + 추출 설정 (여기만 고치면 사이트 추가/삭제)
├── app.py                    # Flask 진입점 (라우팅, 에러 핸들링)
├── reference_finder/
│   ├── __init__.py
│   ├── keywords.py           # 이미지 → 키워드 (Claude vision, JSON-only)
│   ├── sites.py              # config 로드 + 검색 입구 링크(A) 생성
│   └── images.py             # 키워드별 상위 이미지(B) — Google Programmable Search
├── templates/
│   └── index.html            # 업로드 폼 + 결과 카드 UI (바닐라 JS)
└── static/                   # (선택) 정적 파일
```

---

## 실행 방법

### 1. 의존성 설치

```bash
cd reference-finder
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. API 키 설정

`.env` 파일에 키를 넣습니다. 기능별로 필요한 키가 다릅니다:

| 키 | 용도 | 없으면 |
|---|---|---|
| `ANTHROPIC_API_KEY` | 이미지 → 키워드 5개 자동 추출 | 이미지 분석 불가 (키워드 직접 입력은 가능) |
| `GOOGLE_API_KEY` + `GOOGLE_CSE_ID` | 키워드별 상위 이미지(B) | 이미지 영역만 비고 검색 링크(A)는 정상 |

```bash
cp .env.example .env
# .env 를 열어 키 입력
```

**Anthropic 키**: [console.anthropic.com](https://console.anthropic.com/) → API Keys → Create Key.

**Google 검색 키 (무료, 하루 100회)**:
1. [Programmable Search Engine](https://programmablesearchengine.google.com/) → **Add** → **"Search the entire web" 켜기** → 만든 뒤 **검색엔진 ID(cx)** 복사 → `GOOGLE_CSE_ID`
2. [Google Cloud Console](https://console.cloud.google.com/) → **APIs & Services** → **"Custom Search API"** 사용 설정 → **Credentials**에서 API 키 발급 → `GOOGLE_API_KEY`

> 무료 한도는 하루 100 쿼리입니다. 한 번 분석에 `키워드 5 × 사이트 4 = 20 쿼리`를 쓰므로 **하루 약 5회** 분석 가능. (키워드 수·사이트 수를 줄이면 더 많이 가능)

### 3. 서버 실행

```bash
python app.py
```

브라우저에서 http://127.0.0.1:5000 접속 → 이미지 업로드 → 결과 확인.

### 무료로 쓰기 (API 키·과금 없음)

돈이 드는 부분은 **이미지 → 키워드 추출(Claude vision)** 단 한 곳뿐입니다.
검색 입구 링크(A)와 결과 추출(B)은 전부 무료입니다.

- **키워드 직접 입력 모드**: 화면 아래 "또는 무료로 — 키워드 직접 입력"에 키워드를
  콤마로 넣으면 Claude 호출 없이 바로 레퍼런스 링크가 생성됩니다.
  → `ANTHROPIC_API_KEY` 가 없어도, `anthropic` 패키지가 없어도 동작합니다.
  (이 모드만 쓸 거면 2단계 API 키 설정은 건너뛰어도 됩니다.)
- **무료 크레딧**: 신규 Anthropic 계정의 평가판 크레딧이 있으면 이미지 자동 분석도
  그 한도 안에서 무료입니다. (콘솔 Billing/Plans 확인)

---

## 깃허브로 돌리기 — 무료 클라우드 배포 (Render)

이 앱은 **업로드 → 즉시 분석 UI**가 핵심이라 백엔드가 항상 떠 있어야 합니다.
GitHub Pages(정적)로는 백엔드를 못 돌리므로, **깃허브 repo를 Render 무료 플랜에 연결**해
인터넷에 항상 떠 있는 UI로 만듭니다. push할 때마다 자동 재배포됩니다.

> 참고: Render도 데이터센터 IP라 상위 5개 추출(B)은 로컬과 마찬가지로 비기 쉽습니다.
> 검색 입구 링크(A)는 항상 동작합니다(A항상 + B베스트에포트).

### 1) 깃허브에 올리기

```bash
cd reference-finder
git init && git add -A && git commit -m "init: reference-finder"
# 깃허브에 빈 repo를 만든 뒤 (예: gh repo create reference-finder --public --source=. --push)
# 또는 수동으로:
git branch -M main
git remote add origin https://github.com/<내아이디>/reference-finder.git
git push -u origin main
```

> `.gitignore`에 `.env`가 들어 있어 **API 키는 깃허브에 안 올라갑니다.**

### 2) Render에 배포

1. https://render.com 가입(깃허브 계정으로) → **New +** → **Blueprint**
2. 방금 올린 repo 선택 → repo 안의 `render.yaml`을 자동 인식
3. 배포 중 **Environment → ANTHROPIC_API_KEY** 에 키 입력 (이미지 분석 쓸 때만 필요. 키워드 직접 입력 모드만 쓸 거면 빈 값이어도 됨)
4. 배포 완료되면 `https://reference-finder-xxxx.onrender.com` 주소로 UI 접속

이후 코드를 고쳐 `git push` 하면 Render가 자동으로 다시 배포합니다.

> **무료 플랜 주의**: 일정 시간 미사용 시 슬립 → 첫 접속 시 30초쯤 콜드스타트가 있습니다.
> 대안: Railway, Fly.io, Hugging Face Spaces 등도 같은 `Procfile`로 배포 가능합니다.

---

## 사이트 추가/삭제 (`config/sites.json`)

사이트 목록은 코드와 분리되어 있어 JSON만 고치면 됩니다. 서버 재시작이면 반영됩니다.

```jsonc
{
  "max_keywords": 5,          // 이미지에서 뽑을 키워드 개수
  "results_per_site": 3,      // (B) 사이트당 보여줄 상위 이미지 개수
  "request_timeout": 8,       // (B) Google 요청 타임아웃(초)
  "sites": [
    {
      "name": "Pinterest",
      "search_url": "https://kr.pinterest.com/search/pins/?q={query}",  // (A) {query} 자리에 키워드가 URL 인코딩되어 들어감
      "homepage": "https://kr.pinterest.com",
      "domain": "pinterest.com"   // (B) 이 도메인에 한정해 Google 이미지 검색. 없으면 그 사이트는 A 링크만
    }
  ]
}
```

**새 사이트 추가 예 (Dribbble):**

```jsonc
{
  "name": "Dribbble",
  "search_url": "https://dribbble.com/search/shots/popular?q={query}",
  "homepage": "https://dribbble.com",
  "domain": "dribbble.com"
}
```

- `search_url`만 있고 `domain`이 없으면 → 그 사이트는 **검색 입구 링크(A)만** 제공 (이미지 영역 없음).
- `domain`까지 넣으면 → Google 이미지 검색으로 **상위 이미지(B)**도 시도.

> ⚠️ 사이트가 늘수록 Google 쿼리(키워드 × 사이트)가 늘어 무료 한도(하루 100)를 빨리 씁니다.

---

## 약관·안정성 측면에서 주의할 점

이 부분이 가장 중요합니다. 꼭 읽어주세요.

### 1. (B) 상위 이미지는 Google 검색 결과에 의존한다
- 지정 사이트(Pinterest·Behance·Cosmos·Savee 등)는 **JS 렌더링 + 데이터센터 IP 차단 + 약관** 때문에 서버에서 직접 크롤링이 사실상 불가능합니다. 그래서 **Google Programmable Search(이미지 검색)를 경유**해 해당 도메인에 한정한 상위 이미지를 가져옵니다.
- Google이 그 사이트를 색인한 범위 안에서만 결과가 나옵니다. 색인이 적은 사이트(예: 신생 SPA)는 결과가 비거나 적을 수 있습니다 — **버그가 아니라 예상된 동작**이며, 이때도 A(검색 입구 링크)는 정상입니다.
- 무료 한도(하루 100 쿼리) 초과 시 그날은 이미지가 비고 A만 나옵니다.

### 2. 약관(ToS)
- 이 앱은 사이트를 직접 스크래핑하지 않고 **Google 검색 API**를 사용합니다(약관 측면에서 직접 크롤링보다 안전). 그래도 표시되는 이미지의 저작권/사용 범위는 각 출처를 따르므로, 결과 이미지를 재배포·상업적 사용할 때는 원 출처의 라이선스를 확인하세요.
- (A) 검색 입구 링크는 사용자가 직접 그 사이트에서 검색하도록 **안내 링크만 제공**하므로 수집이 아닙니다 — 가장 안전합니다.

### 3. 호스트 IP
- 일부 사이트는 데이터센터/CI IP를 차단합니다. 이 앱은 사이트에 직접 붙지 않고 Google API만 호출하므로 이 영향은 적습니다. (참고: 기존 모니터 프로젝트에서 `yozm.wishket.com`, `contentformcontext.com` 등이 차단된 사례가 있었습니다.)

### 4. Claude API 비용·안정성
- 이미지 1장당 vision 요청 1회가 발생합니다(과금). 업로드 크기·횟수에 유의하세요.
- 키워드 응답은 JSON-only 프롬프트로 받지만, 모델이 가끔 코드펜스(```)나 설명을 붙일 수 있어 **방어적으로 파싱**합니다(코드펜스 제거 + 첫 `{`~마지막 `}` 추출). 파싱 실패 시 명확한 에러를 반환하고 앱은 죽지 않습니다.
- 더 강하게 보장하려면 Structured Outputs(`output_config.format`)로 스키마를 강제할 수 있습니다. 현재는 요청대로 "프롬프트 기반 JSON"을 기본값으로 둡니다.

### 5. 업로드 보안
- 업로드 이미지는 메모리에서만 처리하고 디스크에 저장하지 않습니다.
- 허용 확장자/타입(PNG·JPEG·GIF·WebP)과 용량 상한(기본 10MB)을 검사합니다.

---

## 동작 보장 요약

| 상황 | A(검색 입구) | B(상위 이미지) | 앱 |
|---|---|---|---|
| 정상 (키 설정됨) | ✅ | ✅ | 정상 |
| Google 키 미설정 | ✅ | ⬜ 안내문 | 정상 |
| Google 무료 한도 초과/오류 | ✅ | ⬜ 빈 결과 | 정상 |
| 해당 사이트 색인 결과 없음 | ✅ | ⬜ 빈 결과 | 정상 |
| Claude 키워드 추출 실패(키 없음 등) | — | — | 에러 메시지 반환(죽지 않음) |
