"""
plepa_gui.pages.gallery_parts.dialogs
갤러리 Genit 상용 내보내기 및 로스터 전수 감사 모달 다이얼로그.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List

from nicegui import run, ui
from plepa_engine.reporter import open_in_explorer
from plepa_engine.services.asset_service import default_asset_service
from plepa_engine.services.character_service import default_character_service
from plepa_engine.services.generation_service import GenerationParams
from plepa_engine.services.genit_exporter import default_genit_exporter
from plepa_engine.services.job_manager import global_job_manager


async def _run_genit_export(
    roster: str,
    chars: list,
    c_prefix: str,
    naming_mode: str,
    size_key: str,
    custom_code: str,
) -> None:
    """Genit 상용 규격 내보내기를 io_bound 스레드에서 실행하고 탐색기를 엽니다."""
    keep_orig = naming_mode == "original_name"
    size_map = {"1024x1536": (1024, 1536), "832x1216": (832, 1216), "original": None}
    target_sz = size_map.get(size_key)
    size_label = size_key if target_sz else "원본"

    ui.notify(f"📦 Genit 내보내기 진행 중 ({size_label})...", type="info")
    if c_prefix == "__ALL__":
        total_cnt, out_root, char_cnt = await run.io_bound(
            default_genit_exporter.export_roster,
            roster=roster,
            target_size=target_sz,
            keep_original_filename=keep_orig,
        )
        if total_cnt > 0:
            ui.notify(f"🎉 '{roster}' {char_cnt}명 총 {total_cnt}장 Genit 내보내기 완료! ({size_label})", type="positive")
            open_in_explorer(out_root)
        else:
            ui.notify(f"⚠️ 내보낼 수 있는 에셋이 없습니다: {roster}", type="warning")
        return

    c_obj = next(c for _, c, _ in chars if c.prefix == c_prefix)
    c_code = custom_code.strip().upper() or "AA"
    count, out_path, final_code = await run.io_bound(
        default_genit_exporter.export_character,
        roster=roster,
        char_prefix=c_prefix,
        char_name=c_obj.name,
        custom_export_code=c_code,
        target_size=target_sz,
        keep_original_filename=keep_orig,
    )
    if count > 0:
        ui.notify(f"🎉 {c_obj.name} ({final_code}) 에셋 {count}장 Genit 내보내기 완료! ({size_label})", type="positive")
        open_in_explorer(out_path)
    else:
        ui.notify(f"⚠️ 내보낼 수 있는 에셋이 없습니다: {c_prefix}", type="warning")


def open_genit_export_dialog(state: Dict[str, Any]) -> None:
    """Genit 규격 내보내기 모달 다이얼로그 (해상도 통일 + 전체 일괄 내보내기 지원)."""
    chars = default_character_service.list_characters(roster=state["roster"])
    if not chars:
        ui.notify(f"로스터 '{state['roster']}'에 캐릭터가 없습니다.", type="warning")
        return

    with ui.dialog() as dlg, ui.card().classes("w-[540px] max-w-[95vw] p-6 bg-slate-900 border border-indigo-700/60 rounded-xl shadow-2xl"):
        ui.label("📦 Genit 상용 규격 에셋 내보내기").classes("text-lg font-bold text-indigo-300 mb-1")
        ui.label("로컬 원본 에셋은 100% 무손실 보존하고, dist/genit/ 폴더로 규격 변환·해상도 통일하여 내보냅니다.").classes("text-xs text-slate-400 mb-4")

        char_opts = {"__ALL__": f"🌟 로스터 전체 일괄 내보내기 ({len(chars)}명)"}
        for _, c, _ in chars:
            char_opts[c.prefix] = f"{c.name} ({c.prefix})"
        selected_char_prefix = {"val": "__ALL__"}

        init_char_obj = chars[0][1]
        init_export_code = default_genit_exporter.resolve_export_code(init_char_obj.name, init_char_obj.prefix, roster=state["roster"])
        code_input_state = {"val": init_export_code}
        naming_state = {"val": "original_name"}
        size_state = {"val": "1024x1536"}

        def _sync_code_visibility():
            code_box.set_visibility(selected_char_prefix["val"] != "__ALL__" and naming_state["val"] == "legacy_code")

        def on_dialog_char_change(prefix_val):
            selected_char_prefix["val"] = prefix_val
            if prefix_val != "__ALL__":
                c_obj = next(c for _, c, _ in chars if c.prefix == prefix_val)
                new_code = default_genit_exporter.resolve_export_code(c_obj.name, c_obj.prefix, roster=state["roster"])
                code_input.value = new_code
                code_input_state["val"] = new_code
            _sync_code_visibility()

        ui.label("1. 대상 캐릭터 선택").classes("text-xs font-bold text-amber-400 mb-1")
        ui.select(options=char_opts, value="__ALL__", on_change=lambda e: on_dialog_char_change(e.value)).props("dense outlined dark options-dense").classes("w-full mb-3")

        ui.label("2. 경로·파일명 규격").classes("text-xs font-bold text-amber-400 mb-1")
        ui.select(
            options={
                "original_name": "✨ 폴더/원본파일명 유지 (예: aya/aya_000_평상.webp — v2.2 권장)",
                "legacy_code": "레거시 2글자 코드 (예: AA/A0.webp)",
            },
            value="original_name",
            on_change=lambda e: (naming_state.update({"val": e.value}), _sync_code_visibility()),
        ).props("dense outlined dark options-dense").classes("w-full mb-3")

        code_box = ui.column().classes("w-full mb-3 gap-1")
        with code_box:
            ui.label("2-1. 캐릭터 코드 (2글자 대문자)").classes("text-xs font-bold text-amber-400")
            code_input = ui.input(value=init_export_code, on_change=lambda e: code_input_state.update({"val": e.value.upper()})).props("dense outlined dark").classes("w-full font-mono font-bold")
        code_box.set_visibility(False)

        ui.label("3. 출력 해상도 통일").classes("text-xs font-bold text-amber-400 mb-1")
        ui.select(
            options={
                "1024x1536": "✨ 1024×1536 / 가로 1536×1024 통일 (권장 · 방향 자동 감지 고해상도)",
                "832x1216": "832×1216 / 가로 1216×832 통일 (SDXL 표준 · 방향 자동 감지)",
                "original": "원본 해상도 그대로 (무손실 복사)",
            },
            value="1024x1536",
            on_change=lambda e: size_state.update({"val": e.value}),
        ).props("dense outlined dark options-dense").classes("w-full mb-6")

        async def do_export():
            dlg.close()
            await _run_genit_export(
                state["roster"], chars, selected_char_prefix["val"],
                naming_state["val"], size_state["val"], code_input_state["val"],
            )

        with ui.row().classes("w-full justify-end gap-2"):
            ui.button("취소", on_click=dlg.close).props("flat color=slate-400")
            ui.button("내보내기 실행", icon="check", on_click=do_export).props("unelevated color=indigo-500 font-bold")
    dlg.open()


def _render_audit_row(r: Dict[str, Any], state: Dict[str, Any], dlg: Any, sync_queue_cb: Callable[[bool], None]) -> None:
    """에셋 전수 감사 테이블의 단일 캐릭터 행을 렌더링합니다."""
    with ui.element("tr").classes("border-b border-slate-800/70 hover:bg-slate-800/40"):
        ui.element("td").classes("p-2.5 font-mono font-bold text-amber-300")._text = r["prefix"]
        ui.element("td").classes("p-2.5 text-slate-200 font-semibold")._text = r["name"]
        ui.element("td").classes("p-2.5 font-mono text-slate-300")._text = f"{r['present_count']} / {r['expected_count']}"

        with ui.element("td").classes("p-2.5"):
            rate = r["completion_rate"]
            color = "emerald" if rate >= 100 else ("amber" if rate >= 50 else "rose")
            ui.badge(f"{rate}%", color=color).props("dense text-[10px]")

        with ui.element("td").classes("p-2.5"):
            orig_cnt = r["origin_count"]
            if orig_cnt > 0:
                ui.badge(f"{orig_cnt}장 백업", color="cyan-800").props("dense text-[10px]")
            else:
                ui.label("-").classes("text-slate-500")

        missing: List[str] = r["missing_codes"]
        with ui.element("td").classes("p-2.5"):
            if not missing:
                ui.label("✔ 완벽").classes("text-emerald-400 font-bold")
            else:
                m_text = ",".join(missing[:4]) + (f".. (+{len(missing)-4})" if len(missing) > 4 else "")
                ui.label(m_text).classes("font-mono text-rose-300 text-[11px]").tooltip(",".join(missing))

        with ui.element("td").classes("p-2.5 text-right"):
            if missing:
                async def trigger_missing(char_p=r["prefix"], miss_codes=missing):
                    dlg.close()
                    m_params = GenerationParams(
                        character_expr=char_p, pose_expr=",".join(miss_codes), roster=state["roster"],
                        censor=True, censor_style=state["censor_style"], censor_targets=state["censor_targets"],
                    )
                    started, pos = global_job_manager.enqueue_job(m_params, label=f"결손 보완 {char_p} ({len(miss_codes)}종)")
                    ui.notify(f"⚡ {char_p} 누락 포즈 {len(miss_codes)}개 생성 시작!" if started else f"📋 {char_p} 대기열 #{pos} 등록!", type="info")
                    sync_queue_cb(True)

                ui.button("⚡ 누락분 즉시 생성", on_click=trigger_missing).props(
                    "unelevated dense size=xs color=amber-500 text-color=slate-950 font-bold"
                ).tooltip("누락된 포즈들만 묶어서 즉시 생성합니다")
            else:
                ui.label("완비").classes("text-slate-500 text-[11px]")


def open_audit_dialog(state: Dict[str, Any], sync_queue_cb: Callable[[bool], None]) -> None:
    """로스터 내 에셋 완비율 및 누락 포즈 1초 전수 감사 모달 다이얼로그."""
    reports = default_asset_service.audit_roster_assets(roster=state["roster"])
    if not reports:
        ui.notify(f"로스터 '{state['roster']}'에 감사할 캐릭터가 없습니다.", type="warning")
        return

    with ui.dialog() as dlg, ui.card().classes("w-[900px] max-w-[95vw] max-h-[85vh] p-6 bg-slate-900 border border-emerald-700/60 rounded-xl shadow-2xl overflow-y-auto"):
        with ui.row().classes("w-full justify-between items-center mb-4 pb-2 border-b border-slate-800"):
            with ui.row().classes("items-center gap-2"):
                ui.icon("assessment", size="26px").classes("text-emerald-400")
                ui.label(f"📊 '{state['roster']}' 에셋 전수 감사 리포트 (총 {len(reports)}명)").classes("text-lg font-bold text-slate-100")
            ui.button(icon="close", on_click=dlg.close).props("flat dense round color=slate-400")

        with ui.element("table").classes("w-full border-collapse text-left text-xs mb-2"):
            with ui.element("thead"):
                with ui.element("tr").classes("border-b border-slate-700 bg-slate-800/80"):
                    for col_title, extra_cls in (
                        ("식별자", ""), ("이름", ""), ("보유 / 기대", ""),
                        ("완비율", ""), ("무검열 백업(_origin)", ""),
                        ("누락 포즈 코드", ""), ("원클릭 액션", " text-right"),
                    ):
                        ui.element("th").classes(f"p-2.5 text-slate-300 font-bold{extra_cls}")._text = col_title
            with ui.element("tbody"):
                for r in reports:
                    _render_audit_row(r, state, dlg, sync_queue_cb)

    dlg.open()
