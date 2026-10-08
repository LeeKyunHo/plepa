# 플에파(PLEPA) default_mode 가이드

> **키로(Kiro) roster.py 이식 완료**  
> 캐릭터별 기본 엔진 자동 선택 기능

---

## 개요

`default_mode`는 키로 프로젝트의 roster.py 로직을 플에파에 이식한 기능으로, **캐릭터 JSON 파일에 선호 엔진을 명시**하면 CLI와 GUI에서 자동으로 해당 엔진이 적용됩니다.

---

## 지원 엔진 및 별칭

| 설정값 | 해석 결과 | 설명 |
|--------|-----------|------|
| `null` (빈칸) | 시스템 기본값 | `PLEPA_DEFAULT_ENGINE` 환경변수 또는 `sdxl` |
| `"sdxl"` | `sdxl` | SDXL 체크포인트 (Unholy Desire Mix 등) |
| `"flux"` | `flux` | FLUX.1 [dev] GGUF 고품질 |
| `"fast"`, `"f"` | `sdxl` | 고속 모드 (SDXL 별칭) |
| `"quality"`, `"q"` | `flux` | 고품질 모드 (FLUX 별칭) |

---

## 캐릭터 JSON 설정 예시

```json
{
  "prefix": "sample",
  "name": "샘플 캐릭터",
  "gender": "female",
  "default_mode": "flux",
  "appearance": {
    "face_and_hair": "A captivating young woman with...",
    "physique": "slender waist, soft feminine curves...",
    "outfit": "a pristine fitted white blouse..."
  },
  "lora": {
    "name": null,
    "weight": 0.8
  }
}
```

---

## CLI 사용법

### 단일 캐릭터 (자동 적용)

```bash
# 캐릭터의 default_mode='flux'가 --engine sdxl을 오버라이드함
python flux_batch_generator.py -c sample_character -p 000..019 --engine sdxl

# 출력:
#   [INFO] 캐릭터 'sample'의 default_mode 'flux' → 'flux' 자동 적용
#   [플에파] 듀얼 엔진 가동 모드: FLUX.1 [dev] (GGUF: flux1-dev-Q6_K.gguf)
```

### 다중 캐릭터 (명시적 엔진 우선)

```bash
# 여러 캐릭터 선택 시 --engine 값이 모두에게 적용됨 (default_mode 무시)
python flux_batch_generator.py -c oes,sce,ykn -p 038,039 --engine sdxl
```

---

## GUI 사용법

### 1. 캐릭터 default_mode 설정

1. **캐릭터 관리 페이지** (좌측 메뉴 "👥 캐릭터") 접속
2. 좌측 사이드바에서 편집할 캐릭터 선택
3. 우측 폼에서 **"⚡ 기본 엔진 모드 (default_mode)"** 드롭다운 찾기
4. 원하는 엔진 선택:
   - `(빈칸)`: 시스템 기본값
   - `sdxl`: SDXL 체크포인트
   - `flux`: FLUX.1 [dev]
   - `fast`: 고속 모드 (sdxl 별칭)
   - `quality`: 고품질 모드 (flux 별칭)
5. **저장** 버튼 클릭

### 2. 생성 페이지에서 자동 반영 확인

1. **배치 생성 페이지** (⚡ 배치 생성 설정) 접속
2. default_mode가 설정된 캐릭터 **1명만** 선택
3. 엔진 셀렉터가 자동으로 해당 캐릭터의 default_mode로 변경됨
4. 여러 캐릭터 선택 시, 엔진은 사용자가 수동 선택

---

## 자동 적용 우선순위

1. **단일 캐릭터**: `CharacterConfig.default_mode` → `--engine` 플래그 → 시스템 기본값
2. **다중 캐릭터**: `--engine` 플래그 → 시스템 기본값 (default_mode 무시)
3. **GUI**: 캐릭터 1명 선택 시 자동 변경, 여러 명 선택 시 수동 선택

---

## 코드 구조

### 핵심 파일

| 파일 | 역할 |
|------|------|
| `plepa_engine/config.py` | `_DEFAULT_MODE_MAP`, `resolve_default_mode()` 함수 정의 |
| `plepa_engine/models.py` | `CharacterConfig.default_mode` 필드 추가 |
| `plepa_engine/services/schemas.py` | `CharacterSchema.default_mode` Pydantic 검증 |
| `plepa_engine/services/generation_service.py` | `run_batch()` 시작 시 단일 캐릭터 자동 해석 |
| `plepa_gui/pages/characters.py` | GUI default_mode 입력 및 저장 로직 |

### resolve_default_mode() 함수

```python
def resolve_default_mode(raw_mode: str | None) -> str:
    """
    캐릭터 JSON default_mode 필드를 정규화.
    - None → DEFAULT_ENGINE 반환
    - 유효한 별칭 → "sdxl" 또는 "flux" 반환
    - 그 외 → ValueError
    """
    if raw_mode is None:
        return DEFAULT_ENGINE
    
    normalized = str(raw_mode).strip().lower()
    if not normalized:
        return DEFAULT_ENGINE
    
    if normalized in _DEFAULT_MODE_MAP:
        return _DEFAULT_MODE_MAP[normalized]
    
    valid_keys = ", ".join(sorted(_DEFAULT_MODE_MAP.keys()))
    raise ValueError(
        f"Invalid default_mode '{raw_mode}'. "
        f"Valid options: {valid_keys}"
    )
```

---

## 검증 및 디버깅

### Python 대화형 테스트

```python
from plepa_engine.config import resolve_default_mode

print(resolve_default_mode("flux"))      # → flux
print(resolve_default_mode("sdxl"))      # → sdxl
print(resolve_default_mode("fast"))      # → sdxl
print(resolve_default_mode("quality"))   # → flux
print(resolve_default_mode("q"))         # → flux
print(resolve_default_mode(None))        # → sdxl (시스템 기본값)
```

### CLI 디버그 로그

단일 캐릭터 생성 시 다음과 같은 로그가 출력됩니다:

```
[INFO] 캐릭터 'sample'의 default_mode 'flux' → 'flux' 자동 적용
```

만약 default_mode 값이 유효하지 않으면:

```
[경고] 캐릭터 default_mode 'invalid_value' 무효: Invalid default_mode 'invalid_value'. Valid options: f, fast, flux, q, quality, sdxl
```

---

## 마이그레이션 가이드

### 기존 캐릭터 JSON에 default_mode 추가

1. 캐릭터 JSON 파일 열기 (예: `projects/default/characters/sample_character.json`)
2. `"gender": "female"` 다음 줄에 `"default_mode": "flux"` 추가
3. 저장 후 CLI로 테스트

**Before:**
```json
{
  "prefix": "sample",
  "name": "샘플 캐릭터",
  "gender": "female",
  "appearance": { ... }
}
```

**After:**
```json
{
  "prefix": "sample",
  "name": "샘플 캐릭터",
  "gender": "female",
  "default_mode": "flux",
  "appearance": { ... }
}
```

### GUI에서 일괄 설정

1. GUI 캐릭터 관리 페이지 접속
2. 각 캐릭터별로 default_mode 드롭다운 선택 후 저장
3. 저장 시 JSON 파일에 자동으로 기록됨

---

## FAQ

**Q: default_mode를 설정하지 않으면 어떻게 되나요?**  
A: 시스템 기본값(`PLEPA_DEFAULT_ENGINE` 환경변수 또는 `sdxl`)이 사용됩니다.

**Q: 여러 캐릭터를 동시에 생성할 때도 default_mode가 적용되나요?**  
A: 아니요. 여러 캐릭터 선택 시 사용자가 명시한 `--engine` 플래그가 모두에게 적용됩니다.

**Q: GUI에서 default_mode를 설정했는데 CLI에서 반영되지 않아요.**  
A: GUI에서 저장 버튼을 눌렀는지 확인하세요. 저장하면 JSON 파일이 업데이트되고 CLI에서도 자동으로 인식됩니다.

**Q: "fast"와 "sdxl"의 차이는 무엇인가요?**  
A: 실제로는 동일한 엔진(`sdxl`)을 가리키는 별칭입니다. 사용자 편의를 위한 의미론적 구분일 뿐입니다.

---

## 참고 문서

- [프로젝트가이드.md](docs/프로젝트가이드.md) - 전체 시스템 아키텍처
- [사용법.md](docs/사용법.md) - CLI 매뉴얼
- [AI_HANDOVER_GUIDE.md](AI_HANDOVER_GUIDE.md) - AI 에이전트 인계서

---

**문서 버전**: v1.0.0  
**작성일**: 2026-10-06  
**키로 호환성**: roster.py default_mode 로직 완전 이식
