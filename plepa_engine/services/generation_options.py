"""
plepa_engine.services.generation_options
CLI·Engine·GUI 삼위일체(Trinity Sync)용 생성 옵션 단일 레지스트리 및 LoRA 해석기.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple


_DISABLED_LORA_TOKENS = {"none", "null", "off", "false"}


# CLI와 GUI가 단일 진실 공급원(SSOT)으로 공유하는 생성 옵션 메타데이터 레지스트리
GENERATION_OPTION_SPECS: List[Dict[str, Any]] = [
    {
        "field": "face_detailer",
        "cli_flag": "--face-detailer",
        "label": "Face Detailer",
        "tooltip": "얼굴 디테일러(Face Detailer) 후처리 적용 (기본 권장)",
        "default": True,
        "widget": "checkbox",
    },
    {
        "field": "hand_detailer",
        "cli_flag": "--hand-detailer",
        "label": "Hand Detailer",
        "tooltip": "손 디테일러(Hand Detailer) 체이닝으로 손가락 왜곡 자동 보정",
        "default": False,
        "widget": "checkbox",
    },
    {
        "field": "freeu",
        "cli_flag": "--freeu",
        "label": "FreeU 화질 부스팅",
        "tooltip": "ComfyUI FreeU 노드로 SDXL 선명도, 콘트라스트 및 피부 질감 극대화",
        "default": True,
        "widget": "checkbox",
    },
    {
        "field": "upscale",
        "cli_flag": "--upscale",
        "label": "4x AI 업스케일",
        "tooltip": "4x-UltraSharp 모델을 통한 4K 초해상화",
        "default": False,
        "widget": "checkbox",
    },
    {
        "field": "censor",
        "cli_flag": "--censor",
        "label": "화이트 실루엣 검열",
        "tooltip": "YOLO 자동 탐지 기반 화이트 실루엣 검열 (_origin 백업 유지)",
        "default": True,
        "widget": "checkbox",
    },
    {
        "field": "censor_style",
        "cli_flag": "--censor-style",
        "label": "검열 스타일",
        "tooltip": "자동 검열 시 적용할 마스킹 스타일",
        "default": "white_silhouette",
        "widget": "select",
        "choices": {
            "white_silhouette": "화이트 실루엣", "black_silhouette": "블랙 실루엣",
            "manga_bar": "망가 회전 바", "manga_glow": "망가 화이트 글로우",
            "silhouette": "실루엣(기본)", "bar": "와이드 솔리드 바",
            "wide_bar": "와이드 바", "slim_bar": "슬림 사선 바",
            "shadow": "그림자 음영", "mosaic": "모자이크", "debug_bbox": "디버그 BBox",
        },
    },
    {
        "field": "censor_targets",
        "cli_flag": "--censor-targets",
        "label": "검열 대상",
        "tooltip": "검열 탐지 및 마스킹 대상 부위",
        "default": "penis",
        "widget": "select",
        "choices": {"penis": "남성기 (penis)", "pussy": "여성기 (pussy)", "all": "전체 (all)"},
    },
    {
        "field": "naming",
        "cli_flag": "--naming",
        "label": "파일명 형식",
        "tooltip": "저장되는 에셋 파일명의 명명 규칙",
        "default": "hybrid",
        "widget": "select",
        "choices": {
            "hybrid": "혼합형 (prefix_000_라벨)", "code": "코드형 (prefix_000)", "label": "라벨형 (prefix_라벨)",
        },
    },
    {
        "field": "auto_qc",
        "cli_flag": "--auto-qc",
        "label": "Auto-QC 품질 검증",
        "tooltip": "생성 직후 품질·정합성 자동 검증 및 불량 시 자동 리롤 (CLI 해제: --no-qc)",
        "default": True,
        "widget": "checkbox",
    },
    {
        "field": "retry_qc_failed",
        "cli_flag": "--retry-qc-failed",
        "label": "QC 불량 항목 재시도",
        "tooltip": "_batch_manifest.json의 qc_passed=False 항목을 덮어쓰기 없이 자동 재시도",
        "default": True,
        "widget": "checkbox",
    },
    {
        "field": "max_retries",
        "cli_flag": "--max-retries",
        "label": "최대 Auto-QC 리롤 횟수",
        "tooltip": "Auto-QC 불량 판정 시 포즈당 최대 재시도(리롤) 횟수",
        "default": 3,
        "widget": "int",
        "min": 0,
        "max": 10,
    },
    {
        "field": "prompt_alert_threshold",
        "cli_flag": "--prompt-alert-threshold",
        "label": "연속 불량 경고 임계치",
        "tooltip": "연속 불량 N회 도달 시 프롬프트 점검 경고 발령 임계치",
        "default": 2,
        "widget": "int",
        "min": 1,
        "max": 10,
    },
    {
        "field": "reuse_seed",
        "cli_flag": "--reuse-seed",
        "label": "🔒 골든 시드 고정",
        "tooltip": "_batch_manifest.json의 이전 시드를 재사용하여 구도를 유지하고 의상/태그만 갱신",
        "default": False,
        "widget": "checkbox",
    },
    {
        "field": "deterministic_pose_seed",
        "cli_flag": "--deterministic-pose-seed",
        "label": "🧭 포즈 고정 시드",
        "tooltip": "포즈 코드와 캐릭터 기반의 결정론적 시드를 자동 산출하여 실행 간 구도 편차를 억제",
        "default": False,
        "widget": "checkbox",
    },
    {
        "field": "seed",
        "cli_flag": "--seed",
        "label": "고정 난수 시드",
        "tooltip": "특정 시드 번호를 직접 고정하여 생성 (비워두면 무작위 시드)",
        "default": None,
        "widget": "int",
    },
    {
        "field": "strict_censor_qc",
        "cli_flag": "--strict-censor-qc",
        "label": "🛡️ 엄격 검열 리롤 (Auto-QC)",
        "tooltip": "성인 H씬에서 성기 미탐지(구도 왜곡 등) 시 통과시키지 않고 자동 리롤",
        "default": False,
        "widget": "checkbox",
    },
    {
        "field": "anchor_fallback",
        "cli_flag": "--anchor-fallback",
        "label": "안전 앵커 폴백",
        "tooltip": "성기 미탐지 시 체위별 안전 앵커 좌표로 폴백 마스킹 (오검열 방지를 위해 기본 비활성)",
        "default": False,
        "widget": "checkbox",
    },
    {
        "field": "censor_only",
        "cli_flag": "--censor-only",
        "label": "⚡ 0.2초 소급 검열 전용",
        "tooltip": "신규 생성 없이 기존 에셋에 실루엣 검열만 즉시 일괄 적용",
        "default": False,
        "widget": "checkbox",
    },
    {
        "field": "overwrite",
        "cli_flag": "--overwrite",
        "label": "강제 덮어쓰기 (리롤)",
        "tooltip": "기존에 완료된 에셋을 건너뛰지 않고 새로 생성하여 덮어씁니다",
        "default": False,
        "widget": "checkbox",
    },
    {
        "field": "no_ref",
        "cli_flag": "--no-ref",
        "label": "순수 프롬프트 (IP-Adapter 끄기)",
        "tooltip": "레퍼런스 이미지(IP-Adapter) 색감·화풍 간섭 차단 (기본 권장)",
        "default": True,
        "widget": "checkbox",
    },
    {
        "field": "ref_weight",
        "cli_flag": "--ref-weight",
        "label": "IP-Adapter 가중치",
        "tooltip": "참조 이미지 반영 강도 (0.0~1.5, 비워두면 캐릭터/엔진 기본값)",
        "default": None,
        "widget": "float",
        "min": 0.0,
        "max": 1.5,
        "step": 0.05,
    },
    {
        "field": "lora",
        "cli_flag": "--lora",
        "label": "LoRA 파일명/체이닝",
        "tooltip": "쉼표로 구분한 LoRA 파일명 (예: a.safetensors,b.safetensors:0.7 / none=해제 / 빈값=캐릭터 설정 사용)",
        "default": None,
        "widget": "text",
        "placeholder": "예: style.safetensors (빈값=캐릭터 설정)",
    },
    {
        "field": "lora_weight",
        "cli_flag": "--lora-weight",
        "label": "LoRA 기본 강도",
        "tooltip": "LoRA 적용 강도 (비워두면 캐릭터 설정 또는 0.8)",
        "default": None,
        "widget": "float",
        "min": 0.0,
        "max": 2.0,
        "step": 0.05,
    },
    {
        "field": "bg",
        "cli_flag": "--bg",
        "label": "즉석 배경 프롬프트",
        "tooltip": "배경 프리셋보다 우선 적용되는 사용자 지정 배경 프롬프트",
        "default": None,
        "widget": "text",
        "placeholder": "예: warm bedroom, sunset light",
    },
    {
        "field": "custom_pos",
        "cli_flag": "--custom-pos",
        "label": "추가 긍정 프롬프트",
        "tooltip": "생성 시 항상 결합할 추가 긍정/화풍 태그",
        "default": None,
        "widget": "text",
        "placeholder": "예: soft rim light, delicate shading",
    },
    {
        "field": "custom_neg",
        "cli_flag": "--custom-neg",
        "label": "추가 네거티브 프롬프트",
        "tooltip": "생성 시 추가로 억제할 네거티브 태그",
        "default": None,
        "widget": "text",
        "placeholder": "예: comic, monochrome",
    },
    {
        "field": "ckpt_tag",
        "cli_flag": "--ckpt-tag",
        "label": "체크포인트 태그 폴더",
        "tooltip": "지정 시 assets/{prefix}/ckpt_{태그}/ 하위 폴더에 분리 저장",
        "default": None,
        "widget": "text",
        "placeholder": "예: wai, unholy",
    },
    {
        "field": "mock",
        "cli_flag": "--mock",
        "label": "Mock 시뮬레이션",
        "tooltip": "ComfyUI 서버 연동 없이 0.001초 가상 생성 테스트",
        "default": False,
        "widget": "checkbox",
    },
    {
        "field": "dry_run", "cli_flag": "--dry-run", "label": "드라이런 (프롬프트 점검)",
        "tooltip": "이미지 생성 없이 프롬프트 조립 및 저장 경로만 사전 점검",
        "default": False, "widget": "checkbox",
    },
]


def _clean_lora_name(raw_name: Any) -> Optional[str]:
    text = str(raw_name or "").strip()
    return None if not text or text.lower() in _DISABLED_LORA_TOKENS else text


def _parse_lora_token(token: str, default_weight: float) -> Optional[Tuple[str, float]]:
    raw = token.strip()
    if not raw or raw.lower() in _DISABLED_LORA_TOKENS:
        return None
    if ":" in raw:
        maybe_name, maybe_weight = raw.rsplit(":", 1)
        try:
            clean_name = _clean_lora_name(maybe_name)
            return (clean_name, float(maybe_weight.strip())) if clean_name else None
        except ValueError:
            pass
    clean = _clean_lora_name(raw)
    return (clean, float(default_weight)) if clean else None


def resolve_workflow_loras(char: Any, params: Any) -> List[Tuple[str, float]]:
    """GenerationParams와 CharacterConfig의 LoRA 설정을 우선순위에 따라 체이닝 목록으로 해석합니다."""
    param_lora = getattr(params, "lora", None)
    param_weight = getattr(params, "lora_weight", None)
    char_lora = getattr(char, "lora", None) if char is not None else None
    char_default_w = float(char_lora.weight) if char_lora is not None and getattr(char_lora, "weight", None) is not None else 0.8

    if param_lora is not None:
        raw_param = str(param_lora).strip()
        if raw_param.lower() in _DISABLED_LORA_TOKENS:
            return []
        if raw_param:
            fallback_w = float(param_weight) if param_weight is not None else char_default_w
            resolved: List[Tuple[str, float]] = []
            seen: set[str] = set()
            for token in raw_param.split(","):
                parsed = _parse_lora_token(token, fallback_w)
                if parsed and parsed[0].lower() not in seen:
                    seen.add(parsed[0].lower())
                    resolved.append(parsed)
            return resolved

    collected: List[Tuple[str, float]] = []
    seen = set()
    if char_lora is not None:
        primary_name = _clean_lora_name(getattr(char_lora, "name", None))
        if primary_name:
            seen.add(primary_name.lower())
            collected.append((primary_name, float(param_weight) if param_weight is not None else char_default_w))
    for extra in getattr(char, "loras", []) or []:
        extra_name = _clean_lora_name(getattr(extra, "name", None))
        if not extra_name or extra_name.lower() in seen:
            continue
        seen.add(extra_name.lower())
        extra_w = getattr(extra, "weight", 0.8)
        collected.append((extra_name, float(extra_w if extra_w is not None else 0.8)))
    return collected
