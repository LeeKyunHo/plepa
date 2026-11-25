---
name: plepa-trinity-gui-sync
description: >-
  Use this skill when adding or modifying generation options, CLI flags,
  GenerationParams, services, REST API routes, or NiceGUI pages and components
  to enforce CLI-Engine-GUI Trinity Sync.
---

# PLEPA Trinity Sync & GUI Maintainer (CLI · 서비스 · GUI 삼위일체 전담)

이 스킬이 활성화되면 **CLI · Engine · GUI · Test** 4곳을 반드시 세트로 동기화합니다 (`GEMINI.md` 3조).

## 1. 허용 파일 (Whitelist)
- [`plepa_engine/services/*`](../../../plepa_engine/services) (단, `plepa_gui` 역방향 import 금지)
- [`batch_generator.py`](../../../batch_generator.py)
- `plepa_gui/**`
- [`tests/test_cli_gui_sync.py`](../../../tests/test_cli_gui_sync.py), [`tests/test_gui_all_features.py`](../../../tests/test_gui_all_features.py), [`tests/test_mobile_inspection_api.py`](../../../tests/test_mobile_inspection_api.py), [`tests/test_wave0_hotfixes.py`](../../../tests/test_wave0_hotfixes.py)

## 2. 절대 금지 (Blacklist)
- `GENERATION_OPTION_SPECS` / `GenerationParams` / `batch_generator.py` / `plepa_gui` 중 어느 한쪽에만 옵션을 방치하지 마십시오.
- GUI 코드에서 `GlobalJobManager`를 우회해 `default_generation_service.run_batch`를 직접 스레드로 실행하지 마십시오.
- `/characters` 저장·복제 시 확장 필드 누락 및 `/settings` 프리셋 적용 시 `save_config()` 누락 금지.
- `plepa_gui/`에 FLUX 레거시 UI 잔재 재유입 금지.

## 3. 고정 실행 절차 (Step-by-Step)
1. 생성 옵션 추가·수정 시 ① `GenerationParams` & `GENERATION_OPTION_SPECS` ➔ ② `batch_generator.py` argparse ➔ ③ `plepa_gui/pages/generate.py` 및 `mobile_viewer.py` 연동 ➔ ④ `tests/test_cli_gui_sync.py` 순서로 동시 반영합니다.
2. 배치/리롤 작업 실행은 반드시 `global_job_manager.enqueue_job()`(FIFO 직렬 큐)을 경유하게 구현합니다.
3. 설정 우선순위는 항상 `명시적 호출 인자(params) > .plepa_state/config.json > CheckpointProfile`을 유지합니다.
4. 종료 검증 커맨드로 삼위일체·모바일 API·계약 가드를 확인합니다.

## 4. 필수 종료 검증 커맨드 (Gate)
```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_cli_gui_sync.py tests/test_gui_all_features.py tests/test_mobile_inspection_api.py tests/test_wave0_hotfixes.py tests/test_contract_guards.py -q
```
