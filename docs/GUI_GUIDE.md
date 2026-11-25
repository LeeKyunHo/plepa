# 🖥️ 플에파(PLEPA) 웹 스튜디오 GUI 운영 & 기능 가이드 (`plepa_gui`)

> **문서 목적**: ComfyUI + SDXL 기반 에셋 제작을 브라우저에서 제어하는 NiceGUI 로컬 웹 스튜디오(`127.0.0.1:8080`) **8대 페이지** 및 **공용 수동 검열 에디터·REST API** 사용 설명서입니다.

---

## 1. 스튜디오 실행 및 전역 구조

```powershell
# PC 로컬 스튜디오 (http://localhost:8080)
.\.venv\Scripts\python.exe -m plepa_gui.app

# 원격 모바일 터널 + PLEPA_MOBILE_TOKEN 보안 URL 자동 발급 (/mobile?token=...)
.\.venv\Scripts\python.exe scripts/start_remote.py
```

* **공통 상단 네비게이션바 (`plepa_gui/components/header.py`)**:
  - **로고 (`⚡ PLEPA`)**: 클릭 시 메인 대시보드(`/gallery`) 이동.
  - **8대 메뉴 탭**: `캐릭터 관리` (`/characters`), `포즈 DB` (`/poses`), `배경 프리셋` (`/backgrounds`), `포즈 세트` (`/pose-sets`), `배치 생성` (`/generate`), `갤러리` (`/gallery`), `📱 모바일 뷰어` (`/mobile`), `환경 설정` (`/settings`).
  - **전역 활성 로스터 셀렉터**: 현역 활성 로스터(`campus`, `spy`, `oto` 등 7개, `status=legacy` 구형 5종 기본 분리)를 전 페이지에 실시간 동기화.
  - **우측 상태 뱃지**: `🩺 진단`(HealthService 10단계 무결성 자가 진단), 백그라운드 배치 진행률(`GlobalJobManager` FIFO), ComfyUI(`127.0.0.1:8188`) 연결 감시.

---

## 2. 8대 페이지별 상세 기능

### ① 캐릭터 관리 (`/characters`)
* **무손실 스키마 편집 (`build_updated_character_schema`)**: `sdxl_positive`, `sdxl_nude_positive`, `sdxl_negative`, `signature_accessories`, `outfits`, `profiles`, `pose_restrictions`, `lora` 등을 기존 확장 필드 손실 없이 편집·원자적 저장(`.plepa_backup/` 자동 백업).
* **프롬프트 조립 실시간 미리보기**: 좌측 캐릭터 + 테스트 포즈 선택 시 7단계 Mutator 체인 결과(`Positive / Negative / slot`)를 즉시 확인.
* **복제 마법사 (`clone_character`)**: 기존 캐릭터의 모든 확장 메타데이터를 보존한 채 새 `prefix`/이름/체형으로 복제.

### ② 포즈 DB 관리 (`/poses`)
* **V3 코어 DB (`175`키) & 로스터 이벤트 (`events.json`) 편집**: `000~202` 코드별 `label`, `description`, `required_outfit`, `mob_tier`(`0~3`), `partner_pos`, `mob_shadow`, `status`(`active`/`deprecated`) 조회·수정.
* **라벨 변경 & 에셋 안전 리네임**: 라벨 수정 시 연관 파일 일괄 리네임 드라이런 미리보기 및 2-Pass 적용.

### ③ 배경 프리셋 (`/backgrounds`)
* `projects/{roster}/background.json`의 로스터별 배경 키(`default`, `bedroom`, `aya_tea`, `mai_office` 등)와 `pose_background_mapping.json` 연동 관리.

### ④ 포즈 세트 관리 (`/pose-sets`)
* `data/pose_sets.json`의 V3 표준 세트(`sample10`, `v3_daily_53`, `campus_108`, `oto_108`, `unified_100`, `unified_152` 등 142종 포함) 생성·수정·영숫자 정렬 저장.

### ⑤ 배치 생성 (`/generate`)
* **V3 표준 퀵바 & 옵션 동적 렌더링 (`GENERATION_OPTION_SPECS`, 29종)**:
  - **퀵 프리셋**: `sample10`, `v3_daily_53`, `campus_108`, `oto_108`, `unified_152` 등 원클릭 선택.
  - **29종 삼위일체 동기화 옵션 (`option_controls.py`)**: 체크박스(`Face Detailer`, `Hand Detailer`, `FreeU`, `4x AI 업스케일`, `Auto-QC`, `QC 재시도`, `검열`, `엄격 검열 리롤`, `골든 시드`, `포즈 시드`, `앵커 폴백`, `소급 검열`, `Mock`, `Dry-Run`), 선택형(`검열 스타일 11종`, `검열 대상`, `파일명 규칙`), 수치형(`최대 리롤`, `경고 임계치`, `시드`, `IP-Adapter/LoRA 가중치`), 고급 접이식 텍스트(`LoRA 체이닝`, `즉석 배경`, `추가 긍정/부정`, `ckpt_tag`).
* **FIFO 대기열 일원화**: `/generate` 및 `/gallery`의 누락 채우기·리롤 요청은 모두 `GlobalJobManager.enqueue_job()` FIFO 대기열을 통해 ComfyUI 경합 없이 순차 실행됩니다.

### ⑥ 에셋 갤러리 & 통합 작업실 (`/gallery`)
* **최신 생성순/포즈순 정렬 & 서브필터**: `NEW` 뱃지, 성별·섹션·미생성 필터, 라이트박스 확대 및 `📦 Genit 내보내기` (`GenitExporter.export_roster()` — 로컬 원본 100% 보존 + 패키지용 `1024×1536` Lanczos 중앙 크롭 통일).
* **인라인 3대 액션**:
  - `✏️ 터치 덧칠` (`plepa_gui/components/retouch_editor.py`): 현재 이미지 또는 `🧹 검열 제거(원본 로드)` 후 `🖌️ 화이트 덧칠` / `🩹 지우개(원본 복원)` 편집 ➔ `POST /api/assets/retouch`로 본체 WebP 원자적 교체(`_origin` 보호).
  - `⚡ 재검열` (`POST /api/assets/reapply-censor`) · `🔄 원본 복원` (`POST /api/assets/restore-origin`) · `🎲 리롤` (`POST /api/assets/reroll`) · `휴지통` (`POST /api/assets/delete` / `undo`).

### ⑦ 모바일 전용 고속 뷰어 (`/mobile` · `/m`)
* Vue/Quasar 오버헤드 없는 경량 HTML5 스와이프 뷰어 + `retouch_editor.py` 수동 터치 캔버스 + 상단 `검열 스타일`/`검열 대상`/`앵커 폴백` 툴바 + 원격 구동 시 `PLEPA_MOBILE_TOKEN` 쿠키·Origin 인증 자동 적용.
* 보조 벤치마크 경로: `/otoko` (`/o`), `/compare` (`/c`), `/view_image`.

### ⑧ 환경 설정 (`/settings`)
* **체크포인트·추론 기본값 영속 관리**: `comfy_host`, 기본 로스터, `sdxl_ckpt`, `steps`(28), `cfg`(4.0), `sampler`(`dpmpp_2m`), `scheduler`(`karras`), 기본 해상도(`832×1216`, 하이브리드 025+ `1216×832`).
* **원클릭 체크포인트 프리셋 (`apply_settings_preset`)**: `Unholy V9` / `WAI-Illustrious` / `HexMix v5` 선택 즉시 폼 반영 및 `data/config.json` 영구 저장.
