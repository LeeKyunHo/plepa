---
name: plepa-doc-notebook-sync
description: >-
  Use this skill when updating documentation, writing development journal entries,
  refreshing Gemini notebook snapshots via scripts/export_context.py, or preparing
  clean Git commits and pushes.
---

# PLEPA Doc & Gemini Notebook Sync (서류 · 개발일지 · 노트북 스냅샷 전담)

이 스킬이 활성화되면 서류 정합성 동기화, 외부 Gemini 노트북 스냅샷 갱신, 무결성 검증 및 분할 커밋 절차를 수행합니다.

## 1. 허용 파일 (Whitelist)
- Active SSOT 서류: [`GEMINI.md`](../../../GEMINI.md), [`POSE_MAPPING.md`](../../../POSE_MAPPING.md), [`사용법.txt`](../../../사용법.txt), [`README.md`](../../../README.md), [`docs/DOCUMENTATION_GUIDE.md`](../../../docs/DOCUMENTATION_GUIDE.md), [`docs/AI_HANDOVER_GUIDE.md`](../../../docs/AI_HANDOVER_GUIDE.md), [`docs/RUNBOOK.md`](../../../docs/RUNBOOK.md), [`docs/GUI_GUIDE.md`](../../../docs/GUI_GUIDE.md), [`docs/플에파_기능명세.md`](../../../docs/플에파_기능명세.md), [`docs/캐릭터_포즈_제작_규칙.md`](../../../docs/캐릭터_포즈_제작_규칙.md), [`docs/개발일지.md`](../../../docs/개발일지.md)
- 스냅샷 도구: [`scripts/export_context.py`](../../../scripts/export_context.py), `scripts/context_exporter/*.py` (`scripts/archive/`, `scripts/benchmarks/`, `scripts/ml/` 격리 집계 지원), `context_snapshot/*` (`.gitignore` 대상)
- 운영 스크립트 인덱스: [`scripts/README.md`](../../../scripts/README.md)

## 2. 절대 금지 (Blacklist)
- `docs/archive/` · `scripts/archive/` · `scripts/benchmarks/` 구버전/실험 파일 임의 열람·수정 금지 (`GEMINI.md` 10조).
- Git 커밋 메시지에 성인물·신체 부위·성적 행동 등 민감 어휘 포함 금지 (`GEMINI.md` 2조).
- `pytest` 또는 `precheck` 미통과 상태에서 `git push` 실행 금지.
- `output/`, `benchmarks/`, `projects/*/assets/` 대용량 바이너리 커밋 금지.

## 3. 고정 실행 절차 (Step-by-Step)
1. 먼저 [`docs/DOCUMENTATION_GUIDE.md`](../../../docs/DOCUMENTATION_GUIDE.md)의 작업 유형별 갱신 매트릭스를 확인합니다.
2. 변경 성격에 맞는 Active SSOT 서류와 [`docs/개발일지.md`](../../../docs/개발일지.md) 최상단(역순 + Quick Symptom Index)을 갱신합니다.
3. Gemini 노트북 최신화를 위해 `.\.venv\Scripts\python.exe scripts/export_context.py`를 실행합니다.
4. `git status -s` 점검 및 전체 검증 통과 후 성격별 분할 커밋(`feat:`, `fix:`, `refactor:`, `docs:`, `test:`, `chore:`)과 `git push origin main`을 수행하고 `working tree clean`을 확인합니다.

## 4. 필수 종료 검증 커맨드 (Gate)
```powershell
.\.venv\Scripts\python.exe scripts/export_context.py
.\.venv\Scripts\python.exe -m pytest -q
git status -s
```
