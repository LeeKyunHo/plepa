"""
plepa_gui.pages.generate_sections
배치 생성 페이지의 배경 옵션, V3 퀵 팩 바, 실시간 프리뷰/상태 동기화 헬퍼.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Callable, Dict, List

from nicegui import ui
from plepa_engine.config import (
    DEFAULT_ENGINE,
    DEFAULT_SDXL_CFG,
    DEFAULT_SDXL_CKPT,
    DEFAULT_SDXL_HEIGHT,
    DEFAULT_SDXL_STEPS,
    DEFAULT_SDXL_WIDTH,
    PROJECTS_DIR,
)
from plepa_engine.services.background_service import default_background_service
from plepa_engine.services.config_service import default_config_service
from plepa_engine.services.generation_service import GENERATION_OPTION_SPECS
from plepa_engine.services.job_manager import global_job_manager
from plepa_engine.services.pose_service import default_pose_service


def get_select_options(discovered: list, current_val: str) -> List[str]:
    """발견된 모델 목록에 현재 설정값이 누락되지 않도록 선두 보정합니다."""
    opts = list(discovered)
    if current_val and current_val not in opts:
        opts.insert(0, current_val)
    return opts


def get_bg_options(roster: str, eng: str = "sdxl") -> Dict[str, str]:
    """로스터 및 엔진 기준 배경 프리셋 선택지 맵을 구성합니다."""
    bgs = default_background_service.get_backgrounds(roster, engine=eng)
    opts: Dict[str, str] = {"auto": "🎯 [Auto] 포즈별 자동 매핑 (권장)"}
    special_labels = {
        "spy": {
            "default": "default (1960s 비밀 살롱 VIP 라운지)",
            "boudoir": "boudoir (고급 살롱 사적 침실)",
            "clinic": "clinic (비밀 살롱 의료실)",
            "office": "office (1960s 첩보 아카이브 사무실)",
        }
    }
    for k in bgs.keys():
        if k == "none":
            opts[k] = "none (배경 없음 - 순백색 스튜디오) ⭐"
        elif k == "white_studio":
            opts[k] = "white_studio (화이트 스튜디오)"
        elif k == "grey_studio":
            opts[k] = "grey_studio (그레이 스튜디오)"
        elif k == "default":
            opts[k] = special_labels[roster]["default"] if roster in special_labels and "default" in special_labels[roster] else "default (프로젝트 기본 배경)"
        else:
            opts[k] = special_labels[roster][k] if roster in special_labels and k in special_labels[roster] else k
    return opts


def build_initial_generate_state(active_roster: str, conf: Dict[str, Any]) -> Dict[str, Any]:
    """배치 생성 폼의 초기 상태 딕셔너리를 GENERATION_OPTION_SPECS 기준으로 초기화합니다."""
    state: Dict[str, Any] = {
        "roster": active_roster,
        "selected_chars": [],
        "pose_selection_mode": "set",
        "selected_pose_set": "sample10",
        "custom_pose_expr": "000..019",
        "engine": DEFAULT_ENGINE,
        "sdxl_ckpt": conf.get("sdxl_ckpt", DEFAULT_SDXL_CKPT),
        "bg_preset": "auto",
        "is_running": False,
        "cancel_requested": False,
    }
    for spec in GENERATION_OPTION_SPECS:
        f = spec["field"]
        state[f] = conf.get(f, spec["default"]) if spec.get("widget") == "select" else spec["default"]
    return state


def resolve_state_pose_codes(state: Dict[str, Any]) -> List[str]:
    """현재 선택된 포즈 세트 또는 커스텀 표현식의 포즈 코드 목록을 반환합니다."""
    try:
        if state["pose_selection_mode"] == "set":
            sets = default_pose_service.load_pose_sets()
            target_set = next((s for s in sets if s.id == state["selected_pose_set"]), None)
            if target_set and target_set.codes:
                return list(target_set.codes)
        else:
            expr = state["custom_pose_expr"].strip()
            if expr:
                db = default_pose_service.load_pose_db(engine=state["engine"], roster=state["roster"])
                return default_pose_service.resolve_pose_codes(expr, db, roster=state["roster"])
    except Exception:
        pass
    return []


def render_pose_quick_pack_bar(select_genit_set: Callable[[str, str], None]) -> None:
    """V3 상용 표준 퀵 셀렉트 버튼 바를 렌더링합니다."""
    with ui.row().classes("w-full items-center gap-1.5 p-1.5 bg-indigo-950/40 border border-indigo-700/50 rounded-lg mb-2 flex-wrap"):
        ui.label("👑 V3 표준 팩:").classes("text-[11px] font-bold text-indigo-300 mr-1")
        ui.button("🎀 오토코노코 108", on_click=lambda: select_genit_set("oto_108", "오토코노코 108종 풀패키지")).props("unelevated dense size=xs color=pink-600 text-color=white font-bold").tooltip("000~052, 060~079(활성), 150~194, 200~202 (오토코노코 108종 표준)")
        ui.button("☀️ 일상 53종", on_click=lambda: select_genit_set("v3_daily_53", "일상·감정·이벤트 53종 (000~052)")).props("unelevated dense size=xs color=sky-600 text-color=white font-bold").tooltip("감정(20) + 일상포즈(20) + 이벤트(13)")
        ui.button("여성 100종", on_click=lambda: select_genit_set("unified_100", "여성 100종 표준 패키지")).props("unelevated dense size=xs color=indigo-500 text-color=white font-bold").tooltip("감정(20) + 일상(20) + 이벤트(8) + 로맨스/봉사(14) + H씬(38)")
        ui.button("마스터(142종)", on_click=lambda: select_genit_set("unified_152", "통합 마스터 142종")).props("outline dense size=xs color=indigo-300").tooltip("여성 100종 + 오토코노코 고유 성인 42종 전체")
        ui.button("🔥 성인 H씬(52)", on_click=lambda: select_genit_set("h_scenes_52", "여성 성인 H씬 52종 (060~079 활성, 080~124)")).props("outline dense size=xs color=rose-300")
        ui.button("🎀 오토코노코 H(52)", on_click=lambda: select_genit_set("otokonoko_52", "오토코노코 성인 52종 (060~079 활성, 150~194)")).props("outline dense size=xs color=pink-300")
        ui.button("⚔️ 무협 C", on_click=lambda: select_genit_set("wuxia_actions", "무협 전용 10종 (C1~C10)")).props("unelevated dense size=xs color=amber-700 text-color=white font-bold").tooltip("운기수련, 전투대치, 초식공격, 내공주입, 주화입마, 경공 등")
        ui.button("🔫 첩보 S", on_click=lambda: select_genit_set("spy_actions", "첩보 살롱 전용 10종 (S1~S10)")).props("unelevated dense size=xs color=rose-700 text-color=white font-bold").tooltip("기밀열람, 권총겨눔, 밀실심문, 자백제투여, 살롱접대, 도청감시, 잠입수색, 포박위기, 밀실거래, 밀실독욕")
        ui.button("👗 의상 D/E/F", on_click=lambda: select_genit_set("genit_costumes", "의상 팩 22종 (수영복/BDSM/바니걸)")).props("outline dense size=xs color=indigo-300")


def build_status_preview_widgets() -> Dict[str, Any]:
    """우측 실시간 진행 현황 및 라이브 프리뷰 위젯 딕셔너리를 생성합니다."""
    ui.label("📊 실시간 생성 현황 & 라이브 프리뷰").classes("text-xl font-bold text-slate-100 mb-3")
    with ui.row().classes("w-full items-center justify-between mb-2"):
        status_label = ui.label("대기 중").classes("text-sm font-semibold text-slate-400")
        progress_text = ui.label("0 / 0 (0%)").classes("text-sm font-mono text-amber-400")

    progress_bar = ui.linear_progress(value=0.0).props("color=amber-400 size=10px stripe").classes("rounded mb-4")
    preview_container = ui.card().classes("w-full bg-slate-950/70 border border-slate-800 p-3 rounded-lg mb-4 flex flex-row items-center gap-4")
    preview_img = ui.image().classes("w-28 h-40 object-cover rounded shadow border border-slate-700")
    with ui.column().classes("flex-1 gap-1 text-xs"):
        with ui.row().classes("w-full justify-between items-center"):
            preview_title = ui.label("생성 대기 중").classes("text-sm font-bold text-amber-300")
            ui.button("🎨 갤러리 열기 (최신순)", icon="collections", on_click=lambda: ui.navigate.to("/gallery")).props("flat dense size=xs color=amber-400 font-bold").tooltip("새로 생성된 이미지를 최신순으로 갤러리에서 즉시 검수합니다.")
        preview_seed = ui.label("Seed: -").classes("font-mono text-slate-400")
        preview_file = ui.label("파일명: -").classes("font-mono text-slate-400 truncate max-w-[280px]")
        preview_time = ui.label("소요 시간: -").classes("text-emerald-400")
    preview_container.set_visibility(False)

    ui.label("생성 로그:").classes("text-xs font-semibold text-slate-400 mb-1")
    log_box = ui.column().classes("w-full h-80 overflow-y-auto bg-slate-950 p-3 rounded-lg border border-slate-800 font-mono text-xs text-slate-300 gap-1")
    return {
        "status_label": status_label,
        "progress_text": progress_text,
        "progress_bar": progress_bar,
        "preview_container": preview_container,
        "preview_img": preview_img,
        "preview_title": preview_title,
        "preview_seed": preview_seed,
        "preview_file": preview_file,
        "preview_time": preview_time,
        "log_box": log_box,
    }


def sync_generate_status_widgets(widgets: Dict[str, Any], rendered_log_count: int) -> int:
    """GlobalJobManager 상태를 읽어 진행률·라이브 프리뷰·콘솔 로그 위젯을 갱신합니다."""
    status = global_job_manager.get_status()
    is_running = status["is_running"]
    start_btn, cancel_btn = widgets["start_btn"], widgets["cancel_btn"]

    if is_running:
        start_btn.disable()
        cancel_btn.enable()
        widgets["progress_bar"].value = status["percentage"]
        widgets["progress_text"].set_text(f"{status['current']} / {status['total']} ({int(status['percentage'] * 100)}%)")
        widgets["status_label"].set_text(status["current_msg"])
    else:
        start_btn.enable()
        cancel_btn.disable()
        widgets["status_label"].set_text(status["current_msg"])
        if status["total"] > 0:
            widgets["progress_bar"].value = status["percentage"]
            widgets["progress_text"].set_text(f"{status['current']} / {status['total']} ({int(status['percentage'] * 100)}%)")

    latest = status.get("latest_result")
    if latest and latest.get("image_path"):
        try:
            p_obj = Path(latest["image_path"])
            if p_obj.exists():
                rel_p = p_obj.relative_to(PROJECTS_DIR).as_posix()
                widgets["preview_img"].set_source(f"/projects_static/{rel_p}?t={int(time.time())}")
                widgets["preview_title"].set_text(f"✨ #{latest['code']} {latest['label']}")
                widgets["preview_seed"].set_text(f"🔒 Seed: {latest.get('seed') or '미기록'}")
                widgets["preview_file"].set_text(f"📁 {latest['filename']}")
                widgets["preview_time"].set_text(f"⏱️ {latest['duration_sec']:.1f}초 완료 ({latest['timestamp']})")
                widgets["preview_container"].set_visibility(True)
        except Exception:
            pass

    logs = status["logs"]
    if len(logs) > rendered_log_count:
        with widgets["log_box"]:
            for entry in logs[rendered_log_count:]:
                ui.label(f"[{entry['timestamp']}] {entry['text']}").classes(
                    "text-emerald-400" if entry["success"] else "text-rose-400"
                )
        return len(logs)
    return rendered_log_count


def format_config_badge_text() -> str:
    """전역 config에서 SDXL 설정 배지 문자열을 생성합니다."""
    conf = default_config_service.get_config()
    return (
        f"⚙️ SDXL 설정: CFG {conf.get('sdxl_cfg', DEFAULT_SDXL_CFG)} | "
        f"{conf.get('sdxl_steps', DEFAULT_SDXL_STEPS)}스텝 | "
        f"{conf.get('sdxl_width', DEFAULT_SDXL_WIDTH)}x{conf.get('sdxl_height', DEFAULT_SDXL_HEIGHT)}"
    )
