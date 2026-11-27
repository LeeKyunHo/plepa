# 📱 플에파 원격 검수 & 수동 덧칠 시스템 종합 가이드 (Remote Inspection Runbook)

> **문서 버전**: v2.0.0 (2원화 원격 구조 반영)  
> **핵심 목적**: 로컬 Wi-Fi 및 Cloudflare Quick Tunnel을 통해 스마트폰 터치만으로 에셋 열람, 수동 검열 덧칠(ADR-86), 무검열 원본 즉시 복원, 실시간 재검열 및 리롤을 수행하는 원격 검수 파이프라인 가이드입니다.

---

## 1. 2원화 원격 검수 아키텍처 (`8080 스튜디오` vs 은퇴 `:8085` 아카이브)

| 구분 | **주력 상용 스튜디오 (`:8080`)** | **은퇴 벤치마크 뷰어 (`:8085`, `scripts/archive/`)** |
| :--- | :--- | :--- |
| **기동 스크립트** | `.\.venv\Scripts\python.exe scripts/start_remote.py` | `.\.venv\Scripts\python.exe scripts/archive/serve_benchmark_mobile.py` |
| **모바일 뷰어 경로** | `/mobile` (또는 `/m`) · PC 갤러리 `/gallery` | `/inspect` (사전 빌드 HTML: `scripts/archive/generate_inspection_viewer.py`) |
| **보안 인증** | `PLEPA_MOBILE_TOKEN` 자동 발급 (`?token=` ➔ `HttpOnly` 쿠키 + `Origin` 검증) | `ACCESS_TOKEN` 인증 + `_resolve_safe_subpath` + `Origin` 검증 |
| **수동 덧칠 API** | `POST /api/assets/retouch` (`retouch_editor.py` 공용, 본체 WebP 교체) | `POST /api/retouch_censor` (웹 뷰어 + `output/benchmarks/ground_truth/` 미러링) |
| **재검열 · 원본 복원** | `POST /api/assets/reapply-censor` / `restore-origin` | `POST /api/reapply_censor` / `restore_origin` |
| **비동기 FIFO 리롤** | `GlobalJobManager` (`POST /api/assets/reroll` · `fill-missing`) | `RerollQueueManager` (`POST /api/reroll_queue`, `GET /api/reroll_queue_status`) |

---

## 2. 원격 터널 접속 & 하이퍼링크 불변식

### 2.1 주력 8080 원격 터널 즉시 실행 (`scripts/start_remote.py`)
```powershell
.\.venv\Scripts\python.exe scripts/start_remote.py
```
1. 포트 `8080` NiceGUI 스튜디오가 닫혀 있으면 `PLEPA_MOBILE_TOKEN` 무작위 토큰을 생성해 자동 기동합니다.
2. `cloudflared.exe tunnel --url http://127.0.0.1:8080`으로 공인 HTTPS Quick Tunnel을 열어 `?token=...`이 포함된 `/mobile`, `/otoko`, PC 스튜디오 링크를 출력합니다.
3. 로컬 전용·오프라인 테스트 시에는 `PLEPA_MOBILE_TOKEN` 미설정 상태로 무인증 즉시 호환됩니다.

### 2.2 링크 제공 불변식 (`GEMINI.md` Rule 1)
* 사용자에게 전달하는 모든 웹/터널 URL은 백틱(``)이나 일반 텍스트 대신 **반드시 원클릭 마크다운 하이퍼링크**로 제공합니다:
  - `[📱 모바일 검수 뷰어 바로가기](https://<터널>.trycloudflare.com/mobile?token=...)`

---

## 3. 검수 갤러리 UX · 검열 툴바 · 저장소 계약

* **공용 수동 검열 캔버스 에디터 (`plepa_gui/components/retouch_editor.py`)**:
  - `🧹 검열 제거(원본 로드)`: `{char}_origin/` 무검열 원본을 캔버스에 불러와 새로 마스킹.
  - `🖌️ 화이트 덧칠` / `🩹 지우개(원본 복원)` + 브러시 크기(`6~80px`) + `↩️ 실행 취소` + `💾 저장`.
  - 무검열 원본(`_origin`) 경로 직접 덮어쓰기는 백엔드에서 **HTTP 403으로 영구 차단**됩니다.
* **검열 옵션 (`Phase P2.5` 동결 기준, `ADR-99`)**:
  - 11종 `censor_style`: `white_silhouette` (기본), `black_silhouette`, `manga_bar`, `manga_glow`, `silhouette`, `bar`, `wide_bar`, `slim_bar`, `shadow`, `mosaic`, `debug_bbox`.
  - `enable_anchor_fallback=False` 기본 (미탐지 오마스킹 방지).
* **디렉토리 표준 계약 (`projects/{roster}/assets/`)**:
  - `{char}/01_normal/` (`000~059`), `{char}/02_h_scenes/` (`060~209+`), `{char}_origin/` (무검열 원본 무손실 백업).

---

## 4. 트러블슈팅 빠른 조치

```powershell
# 8080 / 8085 포트 점유 프로세스 강제 종료
Get-NetTCPConnection -LocalPort 8080 -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }

# 터널 로그 확인: $env:TEMP\plepa_tunnel.log (8080) / $env:TEMP\plepa_bench_tunnel.log (8085)
```
* **한글 콘솔 인코딩**: 모든 스크립트 상단 `plepa_engine.config.configure_stdio()`(UTF-8 reconfigure) 유지.
