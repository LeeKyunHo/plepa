---
name: plepa-pipeline-qc-tuner
description: >-
  Use this skill when modifying prompt assembly mutators, outfit/conflict
  cleaning, Auto-QC thresholds, ComfyUI workflow builders, or censor rendering
  modules in plepa_engine/.
---

# PLEPA Pipeline, QC & Censor Tuner (파이프라인 · QA · 검열 코어 전담)

이 스킬이 활성화되면 엔진 내부 로직만 다루며, 승인 없는 임계치 변경 및 하드코딩을 차단합니다.

## 1. 허용 파일 (Whitelist)
- [`plepa_engine/prompt_pipeline.py`](../../../plepa_engine/prompt_pipeline.py) (78L 호환 파사드) & [`plepa_engine/pipeline/`](../../../plepa_engine/pipeline/__init__.py) 서브패키지 (11모듈: `__init__` · `constants` · `context` · `tags` · `pose_prep` · `assembly` · `negative_base` · `defense` · `mob_helpers` · `mob` · `sanitizer` — 전 모듈 `<=285L` · 함수 `<=89L`)
- [`plepa_engine/prompt_builder.py`](../../../plepa_engine/prompt_builder.py)
- [`plepa_engine/qa_validator.py`](../../../plepa_engine/qa_validator.py) & [`plepa_engine/qa_checks.py`](../../../plepa_engine/qa_checks.py)
- [`plepa_engine/precheck.py`](../../../plepa_engine/precheck.py) & [`plepa_engine/precheck_rules.py`](../../../plepa_engine/precheck_rules.py)
- [`plepa_engine/censor/`](../../../plepa_engine/censor/__init__.py) 서브패키지 (`__init__` 파사드 · `_runtime` · `constants` · `policy` · `models` · `geometry` · `protection` · `detection` · `lineart` · `mask_refinement` · `segmentation` · `silhouette_prompts` · `silhouette_sam` · `silhouette` · `styles_basic` · `styles` · `hybrid_gates` · `hybrid` · `pipeline` — 전 모듈 `<=350L` · 함수 `<=120L`)
- [`plepa_engine/workflow_templates.py`](../../../plepa_engine/workflow_templates.py) & [`plepa_engine/workflow_nodes.py`](../../../plepa_engine/workflow_nodes.py), [`plepa_engine/comfy_client.py`](../../../plepa_engine/comfy_client.py), [`plepa_engine/comfy_transport.py`](../../../plepa_engine/comfy_transport.py)
- `tests/test_prompt_*.py`, `tests/test_qa_validator.py`, `tests/test_smart_censor.py`, `tests/test_censor_*.py`, `tests/test_wave4b1_core_modules.py`, `tests/test_wave4b2_service_modules.py`

## 2. 절대 금지 (Blacklist)
- **ADR-99 동결 준수**: 사용자 명시 승인 및 `benchmark_censor_metrics.py` 정량 대조 없이 `censor.py` 탐지/마스크 임계치를 임의로 변경하지 마십시오.
- 엔진 코드에 특정 포즈 번호(`"034"`, `"105"` 등), 캐릭터명, 로스터명 하드코딩 추가 금지 (데이터 JSON 메타데이터 활용).
- `plepa_engine/`에서 `plepa_gui`나 `scripts`를 역방향 import 금지 (`test_ast_size_and_layer_guard` 위반).
- ComfyUI 워크플로우 `.json` 원문 열람 및 `plepa_engine/legacy/` 수정 금지.

## 3. 고정 실행 절차 (Step-by-Step)
1. 수정 대상 파일의 해당 클래스/함수 라인 범위만 정밀 열람합니다.
2. 신규 로직은 120줄 이하 단일 책임 함수로 분리하고, 기존 350줄 초과 파일의 줄수를 늘리지 않도록 주의합니다.
3. 가중치 클램핑(긍정 `1.15`, 부정 `1.25`) 및 `SanitizerMutator` 충돌 제거가 유지되는지 단위 테스트로 검증합니다.
4. 수정 후 관련 파이프라인/QA/검열 테스트와 계약 가드를 모두 통과해야 합니다.

## 4. 필수 종료 검증 커맨드 (Gate)
```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_prompt_pipeline.py tests/test_prompt_conflict.py tests/test_qa_validator.py tests/test_censor_and_pipeline_fixes.py tests/test_contract_guards.py -q
```
