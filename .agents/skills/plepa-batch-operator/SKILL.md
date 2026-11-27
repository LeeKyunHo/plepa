---
name: plepa-batch-operator
description: >-
  Use this skill when running image generation batches, --censor-only retroactive
  censoring, --dry-run checks, roster asset audits, or launching the mobile
  inspection tunnel server.
---

# PLEPA Batch & Inspection Operator (배치 생성 · 검열 · 원격 검수 운영 전담)

이 스킬이 활성화되면 **소스 코드나 포즈 DB를 수정하지 않고** 검증된 CLI·서버 운영 절차만 실행합니다.

## 1. 허용 대상 (Whitelist)
- CLI 실행: `.\.venv\Scripts\python.exe batch_generator.py ...`
- 사전 점검/감사 실행: `plepa_engine.precheck`, `scripts/audit_asset_alignment.py` (`audit_alignment_helpers.py` 포함, 조회 전용), `scripts/audit_sector_assets.py`, `scripts/validate_genit_work.py` (`validate_genit_rules.py` 포함)
- 원격 검수 서버 실행: [`scripts/start_remote.py`](../../../scripts/start_remote.py) (포트 `8080`, `PLEPA_MOBILE_TOKEN` 발급 — 구 `:8085` 뷰어는 `scripts/archive/` 격리 완료)

## 2. 절대 금지 (Blacklist)
- 사용자 명시적 승인 없이 `--overwrite` / `-f`로 기존 완성 에셋 덮어쓰기 실행 금지 (`GEMINI.md` 6·9조).
- `projects/*/assets/` 및 `*_origin/` 이미지 직접 열람(`read_file`) 또는 쉘 파일 삭제/이동 금지.
- **`scripts/sync_to_kiro.py` 실행 금지** (최신 Kiro 파손 위험).
- 백그라운드 생성 작업 완료(`Task Status: DONE`) 전 중간 수치로 성급한 통계 보고 금지 (`GEMINI.md` 8조).
- 탐지 성공 건수와 `--anchor-fallback` 폴백 마스킹 건수를 혼동 보고하지 마십시오.

## 3. 고정 실행 절차 (Step-by-Step)
1. **서버 및 사전점검**: ComfyUI(`http://127.0.0.1:8188/system_stats`) 가동 여부와 `plepa_engine.precheck -r {roster}` 통과를 먼저 확인합니다.
2. **Dry-Run 검증**: 실 생성 전 반드시 `batch_generator.py ... --dry-run`으로 조립된 프롬프트와 해상도를 확인합니다.
3. **비동기 실행 및 대기**: 생성 명령 실행 시 완료 알림까지 대기하고, 종료 후 `_batch_manifest.json` 통계(성공·QC 불량·탐지/폴백 분리)를 정직하게 집계합니다.
4. **URL 표기**: 웹/터널 URL은 반드시 클릭 가능한 마크다운 하이퍼링크(`[📱 모바일 검수 바로가기](URL)`)로 제공합니다 (`GEMINI.md` 1조).

## 4. 필수 종료 검증 커맨드 (Gate)
```powershell
.\.venv\Scripts\python.exe -m plepa_engine.precheck -r campus
.\.venv\Scripts\python.exe batch_generator.py -r campus -p 000 --dry-run
```
