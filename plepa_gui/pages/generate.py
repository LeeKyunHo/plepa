"""
plepa_gui.pages.generate
캐릭터 x 포즈 배치 생성 설정, 실시간 진행률 및 비동기 작업 제어 페이지.
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import List, Optional

from nicegui import run, ui
from plepa_engine.comfy_client import ComfyClient
from plepa_engine.config import DEFAULT_ENGINE, DEFAULT_ROSTER, PROJECTS_DIR
from plepa_engine.models import GenerationResult
from plepa_engine.services.background_service import default_background_service
from plepa_engine.services.character_service import default_character_service
from plepa_engine.services.config_service import default_config_service
from plepa_engine.services.generation_service import (
    GENERATION_OPTION_SPECS,
    GenerationParams,
    default_generation_service,
)
from plepa_engine.services.job_manager import global_job_manager
from plepa_engine.services.pose_background_service import default_pose_bg_service
from plepa_engine.services.pose_service import default_pose_service
from plepa_gui.components.header import get_active_roster, render_header


def render_generate_page() -> None:
    """배치 생성 페이지 렌더링."""
    render_header("/generate")

    conf = default_config_service.get_config()
    comfy_client = ComfyClient(host=conf.get("comfy_host", "127.0.0.1:8188"))
    discovered_models = comfy_client.get_available_models()

    def get_select_options(discovered: list, current_val: str) -> list:
        opts = list(discovered)
        if current_val and current_val not in opts:
            opts.insert(0, current_val)
        return opts

    ckpt_options = get_select_options(discovered_models.get("checkpoints", []), conf.get("sdxl_ckpt", "unholyDesireMixSinister_v90.safetensors"))

    def get_bg_options(r: str, eng: str = "sdxl") -> dict:
        bgs = default_background_service.get_backgrounds(r, engine=eng)
        opts = {}
        
        # 프로젝트별 특수 라벨 정의
        special_labels = {
            "spy": {
                "default": "default (1960s 비밀 살롱 VIP 라운지)",
                "boudoir": "boudoir (고급 살롱 사적 침실)",
                "clinic": "clinic (비밀 살롱 의료실)",
                "office": "office (1960s 첩보 아카이브 사무실)"
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
                # 로스터별 특수 라벨이 있으면 사용
                if r in special_labels and "default" in special_labels[r]:
                    opts[k] = special_labels[r]["default"]
                else:
                    opts[k] = "default (프로젝트 기본 배경)"
            else:
                # 로스터별 특수 라벨이 있으면 사용
                if r in special_labels and k in special_labels[r]:
                    opts[k] = special_labels[r][k]
                else:
                    opts[k] = k
        return opts

    active_r = get_active_roster()

    # 반응형 폼 상태
    state = {
        "roster": active_r,
        "selected_chars": [],
        "pose_selection_mode": "set",  # 'set' or 'custom'
        "selected_pose_set": "sample10",
        "custom_pose_expr": "000..019",
        "engine": "sdxl",
        "sdxl_ckpt": conf.get("sdxl_ckpt", "unholyDesireMixSinister_v90.safetensors"),
        "bg_preset": "none",
        "is_running": False,
        "cancel_requested": False,
    }
    # GENERATION_OPTION_SPECS 레지스트리 기반 옵션 자동 바인딩
    for spec in GENERATION_OPTION_SPECS:
        state[spec["field"]] = spec["default"]

    available_rosters = sorted([p.name for p in PROJECTS_DIR.iterdir() if p.is_dir() and not p.name.startswith(".")])
    if not available_rosters:
        available_rosters = [DEFAULT_ROSTER]

    all_chars = default_character_service.list_characters(roster=state["roster"])
    pose_sets = default_pose_service.load_pose_sets()
    bg_options = get_bg_options(state["roster"], state["engine"])

    with ui.row().classes("w-full max-w-7xl mx-auto p-6 gap-6 items-start"):
        # 좌측: 생성 파라미터 제어판
        with ui.card().classes("w-[520px] bg-slate-900 border border-slate-800 p-6 rounded-xl shadow-lg"):
            ui.label("⚡ 배치 생성 설정").classes("text-xl font-bold text-slate-100 mb-4")

            # 1. 로스터 및 캐릭터 선택
            with ui.row().classes("w-full items-center justify-between mb-1"):
                ui.label("1. 대상 캐릭터 선택").classes("text-xs font-bold text-amber-400")
                with ui.row().classes("gap-1"):
                    ui.button("전체 선택", icon="done_all", on_click=lambda: select_all_chars(True)).props("flat dense size=xs color=amber-400").tooltip("현재 로스터의 모든 캐릭터 선택")
                    ui.button("선택 해제", icon="remove_done", on_click=lambda: select_all_chars(False)).props("flat dense size=xs color=slate-400").tooltip("선택 해제")

            with ui.row().classes("w-full items-center justify-between mb-2"):
                ui.label("로스터:").classes("text-xs text-slate-400")
                roster_sel = ui.select(
                    options=available_rosters,
                    value=state["roster"],
                    on_change=lambda e: on_roster_changed(e.value),
                ).props("dense outlined dark options-dense").classes("w-48 text-sm")

            chars_box = ui.column().classes("w-full max-h-36 overflow-y-auto bg-slate-800/40 p-2 rounded border border-slate-700/50 mb-4")

            # 2. 포즈 선택 (세트 또는 표현식)
            with ui.row().classes("w-full items-center justify-between mb-1"):
                ui.label("2. 포즈 선택").classes("text-xs font-bold text-amber-400")
                with ui.row().classes("gap-1"):
                    ui.button("🌟 10대 골든 (sample10)", icon="star", on_click=lambda: select_genit_set("sample10", "10대 대표 골든 샘플러")).props(
                        "unelevated dense size=xs color=amber-500 text-color=slate-950 font-bold"
                    ).tooltip("000, 002, 020, 024, 034, 040, 044, 060, 080, 088 (1분 고속 검증)")
                    ui.button("🏫 캠퍼스 106종", icon="school", on_click=lambda: select_genit_set("campus_106", "캠퍼스 표준 106종")).props(
                        "unelevated dense size=xs color=amber-500/20 text-color=amber-300 border border-amber-500/40"
                    ).tooltip("000~052, 060~063, 080~127, 130 (오토코노코 자동 +70 매핑)")

            # V2 상용 표준 퀵 셀렉트 버튼 바
            with ui.row().classes("w-full items-center gap-1.5 p-1.5 bg-indigo-950/40 border border-indigo-700/50 rounded-lg mb-2 flex-wrap"):
                ui.label("👑 V2 표준 팩:").classes("text-[11px] font-bold text-indigo-300 mr-1")
                ui.button("여성 100종", on_click=lambda: select_genit_set("unified_100", "여성 100종 표준 패키지")).props(
                    "unelevated dense size=xs color=indigo-500 text-color=white font-bold"
                ).tooltip("감정(20) + 일상(20) + 이벤트(8) + 로맨스(4) + H씬(48)")
                ui.button("마스터(148종)", on_click=lambda: select_genit_set("unified_152", "통합 마스터 148종")).props(
                    "outline dense size=xs color=indigo-300"
                ).tooltip("여성 100종 + 오토코노코 성인 48종 전체")
                ui.button("🔥 성인 H씬(52)", on_click=lambda: select_genit_set("h_scenes_52", "여성 성인 H씬 52종 (060~063, 080~127)")).props(
                    "outline dense size=xs color=rose-300"
                )
                ui.button("🎀 오토코노코 H(52)", on_click=lambda: select_genit_set("otokonoko_52", "오토코노코 성인 52종 (060~063, 150~197)")).props(
                    "outline dense size=xs color=pink-300"
                )
                ui.button("⚔️ 무협 C", on_click=lambda: select_genit_set("wuxia_actions", "무협 전용 10종 (C1~C10)")).props(
                    "unelevated dense size=xs color=amber-700 text-color=white font-bold"
                ).tooltip("운기수련, 전투대치, 초식공격, 내공주입, 주화입마, 경공 등")
                ui.button("🔫 첩보 S", on_click=lambda: select_genit_set("spy_actions", "첩보 살롱 전용 10종 (S1~S10)")).props(
                    "unelevated dense size=xs color=rose-700 text-color=white font-bold"
                ).tooltip("기밀열람, 권총겨눔, 밀실심문, 자백제투여, 살롱접대, 도청감시, 잠입수색, 포박위기, 밀실거래, 밀실독욕")
                ui.button("👗 의상 D/E/F", on_click=lambda: select_genit_set("genit_costumes", "의상 팩 22종 (수영복/BDSM/바니걸)")).props(
                    "outline dense size=xs color=indigo-300"
                )


            with ui.row().classes("w-full gap-4 mb-2"):
                mode_set_btn = ui.radio(
                    ["포즈 세트 사용", "코드 직접 입력"],
                    value="포즈 세트 사용",
                    on_change=lambda e: on_pose_mode_changed(e.value)
                ).props("dark inline dense")

            pose_mode_container = ui.column().classes("w-full mb-3")

            # 스마트 스킵 안내 배너
            with ui.row().classes("w-full p-2.5 bg-emerald-950/40 border border-emerald-600/40 rounded-lg items-center gap-2 mb-4"):
                ui.icon("check_circle", size="18px").classes("text-emerald-400")
                ui.label("기본 동작: 이미 있는 이미지는 자동 건너뛰고 누락된 포즈만 채웁니다.").classes("text-[11px] text-emerald-200")

            # 3. 모델 및 보정 옵션
            with ui.row().classes("w-full items-center justify-between mb-1"):
                ui.label("3. 모델 및 보정 옵션").classes("text-xs font-bold text-amber-400")
                config_badge = ui.label("").classes("text-xs font-mono px-2 py-0.5 rounded bg-amber-500/10 text-amber-300 border border-amber-500/30")

            with ui.row().classes("w-full gap-4 mb-2 items-center"):
                ui.badge("SDXL 공식 엔진", color="emerald-700").props("dense text-xs")

                bg_sel = ui.select(
                    options=bg_options,
                    value=state["bg_preset"],
                    label="배경 프리셋",
                    on_change=lambda e: state.update({"bg_preset": e.value})
                ).props("dense outlined dark options-dense").classes("flex-1")
                
                # 배경 자동 매칭 버튼
                ui.button(
                    "🎯",
                    on_click=lambda: auto_match_background()
                ).props("flat dense color=amber-400").tooltip("선택된 포즈에 맞는 배경 자동 매칭 (로스터별 최적화)")

            model_select_container = ui.column().classes("w-full mb-3")

            # 레지스트리 기반 옵션 체크박스 동적 렌더링
            with ui.row().classes("w-full items-center gap-3 p-3 bg-slate-800/40 rounded-lg border border-slate-700/50 mb-6 flex-wrap"):
                for spec in GENERATION_OPTION_SPECS:
                    f = spec["field"]
                    ui.checkbox(
                        spec["label"],
                        value=state[f],
                        on_change=lambda e, field=f: state.update({field: e.value})
                    ).props("dark dense").tooltip(spec["tooltip"])

            # 생성 시작 및 취소 버튼
            with ui.row().classes("w-full justify-between items-center"):
                start_btn = ui.button("배치 생성 시작", icon="play_arrow", on_click=lambda: start_generation()).props(
                    "unelevated color=amber-500 text-color=slate-950 font-bold px-6 py-2"
                )
                cancel_btn = ui.button("중단(취소)", icon="stop", on_click=lambda: request_cancel()).props(
                    "outline color=negative dense px-4"
                )
                cancel_btn.disable()

        # 우측: 실시간 진행 현황, 라이브 프리뷰어 및 콘솔 로그 카드
        with ui.card().classes("flex-1 bg-slate-900 border border-slate-800 p-6 rounded-xl shadow-lg min-h-[600px]"):
            ui.label("📊 실시간 생성 현황 & 라이브 프리뷰").classes("text-xl font-bold text-slate-100 mb-3")

            with ui.row().classes("w-full items-center justify-between mb-2"):
                status_label = ui.label("대기 중").classes("text-sm font-semibold text-slate-400")
                progress_text = ui.label("0 / 0 (0%)").classes("text-sm font-mono text-amber-400")

            progress_bar = ui.linear_progress(value=0.0).props("color=amber-400 size=10px stripe").classes("rounded mb-4")

            # 실시간 최신 생성 이미지 라이브 프리뷰 카드
            preview_container = ui.card().classes("w-full bg-slate-950/70 border border-slate-800 p-3 rounded-lg mb-4 flex flex-row items-center gap-4")
            preview_img = ui.image().classes("w-28 h-40 object-cover rounded shadow border border-slate-700")
            with ui.column().classes("flex-1 gap-1 text-xs"):
                preview_title = ui.label("생성 대기 중").classes("text-sm font-bold text-amber-300")
                preview_seed = ui.label("Seed: -").classes("font-mono text-slate-400")
                preview_file = ui.label("파일명: -").classes("font-mono text-slate-400 truncate max-w-[280px]")
                preview_time = ui.label("소요 시간: -").classes("text-emerald-400")
            preview_container.set_visibility(False)

            ui.label("생성 로그:").classes("text-xs font-semibold text-slate-400 mb-1")
            log_box = ui.column().classes("w-full h-80 overflow-y-auto bg-slate-950 p-3 rounded-lg border border-slate-800 font-mono text-xs text-slate-300 gap-1")

    def select_all_chars(select: bool):
        chars = default_character_service.list_characters(roster=state["roster"])
        if select:
            state["selected_chars"] = [c.prefix for _, c, _ in chars]
            ui.notify(f"로스터 '{state['roster']}' 캐릭터 {len(chars)}명 전체 선택 완료", type="info")
        else:
            state["selected_chars"] = []
            ui.notify("선택 해제 완료", type="info")
        refresh_char_checkboxes(keep_selection=True)

    def select_all_80_poses():
        state["pose_selection_mode"] = "set"
        state["selected_pose_set"] = "all_80"
        mode_set_btn.value = "포즈 세트 사용"
        on_pose_mode_changed("포즈 세트 사용")
        auto_match_background()
        ui.notify("⭐ 기본 80종 포즈 (000~159) 선택 완료!", type="positive")

    def select_genit_set(set_id: str, label_name: str):
        state["pose_selection_mode"] = "set"
        state["selected_pose_set"] = set_id
        mode_set_btn.value = "포즈 세트 사용"
        on_pose_mode_changed("포즈 세트 사용")
        auto_match_background()
        ui.notify(f"👑 Genit {label_name} 선택 완료!", type="positive")

    def on_roster_changed(new_r: str):
        state["roster"] = new_r
        refresh_char_checkboxes()
        # 배경 목록 갱신
        new_opts = get_bg_options(new_r, state["engine"])
        bg_sel.options = new_opts
        if state["bg_preset"] not in new_opts:
            state["bg_preset"] = "none" if "none" in new_opts else list(new_opts.keys())[0]
            bg_sel.value = state["bg_preset"]
        # 로스터 변경 시 자동으로 배경 매칭
        auto_match_background()

    def _get_current_pose_codes() -> List[str]:
        """현재 선택된 포즈 세트 또는 커스텀 표현식의 포즈 코드 목록을 반환합니다."""
        try:
            if state["pose_selection_mode"] == "set":
                if state["selected_pose_set"] == "all_80":
                    return [f"{i:03d}" for i in range(60)] + [f"{i:03d}" for i in range(140, 160)]
                sets = default_pose_service.load_pose_sets()
                target_set = next((s for s in sets if s.id == state["selected_pose_set"]), None)
                if target_set and target_set.codes:
                    return list(target_set.codes)
            else:
                expr = state["custom_pose_expr"].strip()
                if expr:
                    db = default_pose_service.load_pose_db(engine=state["engine"], roster=state["roster"])
                    return default_pose_service.resolve_pose_codes(expr, db)
        except Exception:
            pass
        return []

    def auto_match_background():
        """선택된 로스터와 포즈(세트/표현식)에 맞는 배경을 자동으로 매칭합니다."""
        try:
            codes = _get_current_pose_codes()
            recommended_bg = default_pose_bg_service.get_recommended_background_for_poses(
                state["roster"], codes
            )

            bg_options_list = get_bg_options(state["roster"], state["engine"])
            if recommended_bg in bg_options_list:
                state["bg_preset"] = recommended_bg
                bg_sel.value = recommended_bg
                ui.notify(
                    f"🎯 {state['roster']} 포즈 맞춤 배경 자동 적용: {bg_options_list[recommended_bg]}",
                    type="positive",
                )
            elif "default" in bg_options_list:
                state["bg_preset"] = "default"
                bg_sel.value = "default"
                ui.notify(f"🎯 기본 배경 적용: {bg_options_list['default']}", type="info")
        except Exception as e:
            print(f"[WARNING] auto_match_background: {e}")

    def update_config_badge():
        conf = default_config_service.get_config()
        cfg_v = conf.get("sdxl_cfg", 5.0)
        steps_v = conf.get("sdxl_steps", 30)
        w_v = conf.get("sdxl_width", 832)
        h_v = conf.get("sdxl_height", 1216)
        config_badge.set_text(f"⚙️ SDXL 설정: CFG {cfg_v} | {steps_v}스텝 | {w_v}x{h_v}")

    def render_model_selector():
        model_select_container.clear()
        with model_select_container:
            label_text = f"SDXL 체크포인트 ({len(discovered_models.get('checkpoints', []))}종 감지됨)" if discovered_models.get("checkpoints") else "SDXL 체크포인트 모델명"
            ui.select(
                options=ckpt_options,
                value=state["sdxl_ckpt"],
                label=label_text,
                on_change=lambda e: state.update({"sdxl_ckpt": e.value})
            ).props("dense outlined dark options-dense use-input new-value-mode=add-unique").classes("w-full text-xs").tooltip("ComfyUI models/checkpoints 폴더 내 모델을 선택하거나 직접 입력합니다.")
        update_config_badge()

    def refresh_char_checkboxes(keep_selection: bool = False):
        chars_box.clear()
        chars = default_character_service.list_characters(roster=state["roster"])
        if not keep_selection:
            state["selected_chars"] = []

        with chars_box:
            for _, c, _ in chars:
                is_chk = c.prefix in state["selected_chars"]

                def toggle_char(prefix=c.prefix):
                    if prefix in state["selected_chars"]:
                        state["selected_chars"].remove(prefix)
                    else:
                        state["selected_chars"].append(prefix)

                ui.checkbox(
                    f"{c.name} ({c.prefix})",
                    value=is_chk,
                    on_change=lambda e, p=c.prefix: (state["selected_chars"].append(p) if e.value else state["selected_chars"].remove(p))
                ).props("dark dense").classes("text-xs text-slate-200")

    def on_pose_set_selected(new_set_id: str):
        state["selected_pose_set"] = new_set_id
        auto_match_background()

    def on_pose_mode_changed(mode_str: str):
        pose_mode_container.clear()
        sets = default_pose_service.load_pose_sets()
        set_options = {}
        for s in sets:
            set_options[s.id] = f"{s.name} ({len(s.codes)}종)"
        set_options["all_80"] = "⭐ 전체 80종 포즈 (000~159) [레거시]"

        if state["selected_pose_set"] not in set_options and set_options:
            state["selected_pose_set"] = next(iter(set_options.keys()))

        with pose_mode_container:
            if "포즈 세트" in mode_str:
                state["pose_selection_mode"] = "set"
                ui.select(
                    options=set_options,
                    value=state["selected_pose_set"],
                    on_change=lambda e: on_pose_set_selected(e.value)
                ).props("outlined dark dense options-dense").classes("w-full text-sm")
            else:
                state["pose_selection_mode"] = "custom"
                ui.input(
                    "포즈 표현식 (예: all, 000..019, 038,039,057)",
                    value=state["custom_pose_expr"],
                    on_change=lambda e: state.update({"custom_pose_expr": e.value})
                ).props("outlined dark dense").classes("w-full text-sm")

    def request_cancel():
        if global_job_manager.is_running:
            global_job_manager.cancel_job()
            status_label.set_text("취소 요청됨... (현재 항목 완료 후 중단)")
            ui.notify("생성 중단 요청이 전달되었습니다.", type="warning")

    def start_generation():
        if global_job_manager.is_running:
            ui.notify("이미 다른 배치 작업이 진행 중입니다.", type="warning")
            return

        if not state["selected_chars"]:
            ui.notify("최소 1명 이상의 캐릭터를 선택해 주십시오.", type="warning")
            return

        # 포즈 표현식 산출
        if state["pose_selection_mode"] == "set":
            if state["selected_pose_set"] == "all_80":
                pose_expr = "all"
            else:
                sets = default_pose_service.load_pose_sets()
                target_set = next((s for s in sets if s.id == state["selected_pose_set"]), None)
                if not target_set or not target_set.codes:
                    ui.notify("선택된 포즈 세트에 포즈가 없습니다.", type="warning")
                    return
                pose_expr = ",".join(target_set.codes)
        else:
            pose_expr = state["custom_pose_expr"].strip()
            if not pose_expr:
                ui.notify("포즈 표현식을 입력해 주십시오.", type="warning")
                return

        char_expr = ",".join(state["selected_chars"])

        option_kwargs = {spec["field"]: state.get(spec["field"], spec["default"]) for spec in GENERATION_OPTION_SPECS}
        params = GenerationParams(
            character_expr=char_expr,
            pose_expr=pose_expr,
            roster=state["roster"],
            engine="sdxl",
            ckpt=state["sdxl_ckpt"],
            bg_preset=state["bg_preset"],
            **option_kwargs,
        )

        log_box.clear()
        nonlocal rendered_log_count
        rendered_log_count = 0

        started = global_job_manager.start_job(params)
        if started:
            ui.notify("백그라운드 배치 작업 시작! 다른 페이지로 이동해도 멈추지 않고 계속 생성됩니다.", type="positive")
            sync_job_status()
        else:
            ui.notify("작업 시작 실패 (이미 실행 중)", type="warning")

    # 전역 백그라운드 작업 상태 실시간 동기화
    rendered_log_count = 0

    def sync_job_status():
        nonlocal rendered_log_count
        status = global_job_manager.get_status()
        is_running = status["is_running"]

        if is_running:
            start_btn.disable()
            cancel_btn.enable()
            progress_bar.value = status["percentage"]
            progress_text.set_text(f"{status['current']} / {status['total']} ({int(status['percentage'] * 100)}%)")
            status_label.set_text(status["current_msg"])
        else:
            start_btn.enable()
            cancel_btn.disable()
            status_label.set_text(status["current_msg"])
            if status["total"] > 0:
                progress_bar.value = status["percentage"]
                progress_text.set_text(f"{status['current']} / {status['total']} ({int(status['percentage'] * 100)}%)")

        # 실시간 최신 생성 이미지 프리뷰 카드 업데이트
        latest = status.get("latest_result")
        if latest and latest.get("image_path"):
            try:
                p_obj = Path(latest["image_path"])
                if p_obj.exists():
                    rel_p = p_obj.relative_to(PROJECTS_DIR).as_posix()
                    preview_img.set_source(f"/projects_static/{rel_p}?t={int(time.time())}")
                    preview_title.set_text(f"✨ #{latest['code']} {latest['label']}")
                    preview_seed.set_text(f"🔒 Seed: {latest.get('seed') or '미기록'}")
                    preview_file.set_text(f"📁 {latest['filename']}")
                    preview_time.set_text(f"⏱️ {latest['duration_sec']:.1f}초 완료 ({latest['timestamp']})")
                    preview_container.set_visibility(True)
            except Exception:
                pass

        logs = status["logs"]
        if len(logs) > rendered_log_count:
            with log_box:
                for entry in logs[rendered_log_count:]:
                    ui.label(f"[{entry['timestamp']}] {entry['text']}").classes(
                        "text-emerald-400" if entry["success"] else "text-rose-400"
                    )
            rendered_log_count = len(logs)

    ui.timer(0.8, sync_job_status)

    # 초기화
    refresh_char_checkboxes()
    on_pose_mode_changed("포즈 세트 사용")
    render_model_selector()
    update_config_badge()
    sync_job_status()
