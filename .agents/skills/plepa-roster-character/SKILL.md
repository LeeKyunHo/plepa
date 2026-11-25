---
name: plepa-roster-character
description: >-
  Use this skill when editing character JSON configs, background presets,
  pose_background_mapping.json, roster metadata, or Gen-IT 5-tab markdown docs
  in docs/genit/.
---

# PLEPA Roster & Character Specialist (캐릭터 · 로스터 · Gen-IT 전담)

이 스킬이 활성화되면 캐릭터·로스터 설정과 Gen-IT 시나리오 문서 정합성 작업만 수행합니다.

## 1. 허용 파일 (Whitelist)
- `projects/{roster}/characters/*.json`
- `projects/{roster}/background.json`, `projects/{roster}/pose_background_mapping.json`, `projects/{roster}/pose_overrides.json`, `projects/{roster}/genit_map.json`
- `docs/genit/*.md`
- [`docs/캐릭터_포즈_제작_규칙.md`](../../../docs/캐릭터_포즈_제작_규칙.md), [`docs/젠잇_캐릭터채팅_제작법.md`](../../../docs/젠잇_캐릭터채팅_제작법.md)

## 2. 절대 금지 (Blacklist)
- `projects/*/assets/` 및 `*_origin/` 기존 에셋 직접 열람·수정·이동·삭제 금지.
- `plepa_engine/precheck.py` 파이썬 코드에 특정 캐릭터 prefix나 의상 토큰 하드코딩 추가 금지.
- 캐릭터 JSON 저장·수정 시 `sdxl_nude_positive`, `outfits`, `pose_restrictions`, `signature_accessories` 필드 누락 금지.
- `long slender limbs` 태그 사용 금지 (`balanced body proportions` 표준 준수).

## 3. 고정 실행 절차 (Step-by-Step)
1. 캐릭터 JSON 편집 시 `sdxl_positive`·`sdxl_nude_positive` 양쪽에 `BREAK` 구분자 및 필수 외형/소품(`signature_accessories`)이 보존되었는지 확인합니다.
2. 배경 추가 시 색조 오염(`yellow tint`, `amber lighting` 등) 차단 네거티브가 캐릭터 JSON에 유지되는지 점검합니다.
3. Gen-IT 완성본(`docs/genit/*.md`) 수정 시 메인+추가 프롬프트 합산 8,000자 이하, 설정집/캐릭터 한도 및 실존 에셋 서픽스(`validate_genit_work.py`) 일치를 확인합니다.
4. 변경 완료 후 해당 로스터의 `precheck`와 계약 테스트를 반드시 실행합니다.

## 4. 필수 종료 검증 커맨드 (Gate)
```powershell
.\.venv\Scripts\python.exe -m plepa_engine.precheck -r campus
.\.venv\Scripts\python.exe -m plepa_engine.precheck -r spy
.\.venv\Scripts\python.exe scripts/validate_genit_work.py --force
.\.venv\Scripts\python.exe -m pytest tests/test_wave0_hotfixes.py tests/test_pose_background_integration.py tests/test_genit_work_integrity.py -q
```
