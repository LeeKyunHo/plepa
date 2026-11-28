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
3. 신규 로스터 Gen-IT v3.0 완성본(`docs/genit/*.md`) 작성·수정 시 [`GENIT_MULTI_THEME_TEMPLATE_v3.0.md`](../../../docs/genit/GENIT_MULTI_THEME_TEMPLATE_v3.0.md) · [`docs/젠잇_캐릭터채팅_제작법.md`](../../../docs/%EC%A0%A0%EC%9E%87_%EC%BA%90%EB%A6%AD%ED%84%B0%EC%B1%84%ED%8C%85_%EC%A0%9C%EC%9E%91%EB%B2%95.md)와 `validate_genit_work.py` 일치를 확인합니다:
   - 메인+추가 `<= 12,000자` · 히든 `<= 2,000자`(독립 버퍼, 메인 분량 충돌 금지) · 경로 `{{url}}{prefix}/{prefix}_{code}.webp` + 1줄 Prefix 백업 · `%` 제외 정수 · `items=` 누락 점검.
   - 고정 인원수 금지(`CHAR_META` 확장·모노그램 폴백), 상보적 선호 선물(직업/종교/자체 상품 충돌 금지), 0칸 HTML `<details>`/`[NEW RESIDENTS]`.
   - v3.0 JSX 3종(`Status` 인라인 DM `isDmOpen` + `poses`/`avatar` 혼용 `resolveAssetUrl` · `Talk` 상시 입력창 · `Board` 강제 출력), 1:1 톡 비밀 격리 3불변식(텔레파시·원격발화·`나:`대필 금지 & 답장 턴 `dm_from=없음` 초기화) + `Talk` `log=` 시간순 누적(최근 4~6개), 이미지 규칙(한 턴 `<= 2장`·동일 코드 중복 금지·성인 구간 `000~020` 표정 대체/말미 `[마지막 이미지]` 슬롯 금지), 유연 호흡 `800~1,200자`·`[계속하기]` 능동 전환·주 화자 `70%` 스포트라이트·고호감도 프롤로그 1인 집중.
4. 기존 v3.0 작품 신규 캐릭터 증설 시 **6단계 SOP**(`PART 6`)를 준수합니다: ① `{prefix}/`·대표 이미지 업로드 ➔ ② `[캐릭터]` 탭 등록 ➔ ③ `[프롬프트]` 기존 레거시 매핑 무수정 보존 + 맨 아래 `[신규 주민 에셋 인덱스]` 별도 덧붙임(`<=12,000자`) ➔ ④ `CHAR_META`(필요 시 `poses`/`avatar`)·`ICON_MAP`·`roster_stats` ➔ ⑤ 프롤로그 `roster_stats`·설정집·발견성(`Board`/DM/관계망) ➔ ⑥ `[설명]` `[NEW RESIDENTS]` 0칸 카드 복제.
5. 변경 완료 후 해당 로스터의 `precheck`와 계약 테스트를 반드시 실행합니다.

## 4. 필수 종료 검증 커맨드 (Gate)
```powershell
.\.venv\Scripts\python.exe -m plepa_engine.precheck -r campus
.\.venv\Scripts\python.exe -m plepa_engine.precheck -r spy
.\.venv\Scripts\python.exe scripts/validate_genit_work.py --force
.\.venv\Scripts\python.exe -m pytest tests/test_wave0_hotfixes.py tests/test_pose_background_integration.py tests/test_genit_work_integrity.py -q
```
