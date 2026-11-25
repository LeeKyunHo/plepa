---
name: plepa-pose-curator
description: >-
  Use this skill when adding, modifying, or renaming SDXL poses, prompt tags,
  mob_tier/partner_pos/mob_shadow flags, required_outfit slots, theme packs, or
  roster event poses in PLEPA.
---

# PLEPA Pose Curator (포즈 · 프롬프트 DB 전담)

이 스킬이 활성화되면 아래 허용 범위와 고정 절차를 벗어나지 않고 포즈 작업만 수행합니다.

## 1. 허용 파일 (Whitelist)
- [`data/sdxl_pose_database.json`](../../../data/sdxl_pose_database.json) (단, 전체 열람 금지 — 타겟 라인 범위 250줄 이하 또는 Python 키 추출만 허용)
- [`data/themes/*.json`](../../../data/themes)
- `projects/*/events.json`
- [`POSE_MAPPING.md`](../../../POSE_MAPPING.md) (및 아카이브 전까지 [`docs/POSE_MAPPING_V2.md`](../../../docs/POSE_MAPPING_V2.md))

## 2. 절대 금지 (Blacklist)
- `plepa_engine/` 파이프라인 코드 임의 수정 금지 (파이프라인 변경이 필요하면 `plepa-pipeline-qc-tuner` 사용).
- `data/legacy/` 및 `plepa_engine/legacy/`(FLUX 레거시) 열람·수정·동기화 금지.
- `projects/*/assets/` 및 `*_origin/` 기존 에셋 직접 읽기·수정·리네임·삭제 금지.
- 가중치 상한(긍정 `1.15`, 부정 `1.25`) 초과 입력 및 `bald`/`faceless`/앞머리 눈가림(`male hair over eyes`) 태그 사용 금지.
- 공용 섹션(`emotions`, `poses`, `romance`, `h_scenes`, `scenes_otokonoko`)에 `classroom`, `cafe setting` 등 로스터 종속 배경 하드코딩 금지.

## 3. 고정 실행 절차 (Step-by-Step)
1. 수정할 포즈 엔트리만 Python 스니펫으로 조회해 기존 의미·`mob_tier`·`partner_pos`·`mob_shadow`를 확인합니다.
2. 2인 포즈에서 파트너 머리가 프레임에 노출될 경우 [`docs/캐릭터_포즈_제작_규칙.md`](../../../docs/캐릭터_포즈_제작_규칙.md)에 따라 뒤통수·상안부 음영 + 주 캐릭터 눈 보호(여성 한정) + `negative_add` 눈/측면 차단 3종 세트를 반영합니다.
3. `data/sdxl_pose_database.json` 수정 직후 [`POSE_MAPPING.md`](../../../POSE_MAPPING.md)를 즉시 함께 갱신합니다.
4. `prompt_otokonoko` 대칭 또는 영향 범위를 확인한 뒤 종료 검증 커맨드를 실행합니다.

## 4. 필수 종료 검증 커맨드 (Gate)
```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_pose_db_contracts.py tests/test_pose_doc_sync.py tests/test_prompt_pipeline.py -q
.\.venv\Scripts\python.exe -m plepa_engine.precheck -r campus
.\.venv\Scripts\python.exe -m plepa_engine.precheck -r spy
```
