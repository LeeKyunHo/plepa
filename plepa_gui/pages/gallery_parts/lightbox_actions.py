"""
plepa_gui.pages.gallery_parts.lightbox_actions
라이트박스 내 리롤, 삭제, 직접 검열, 원본 복원, 4K 업스케일 액션 핸들러.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
import re
import threading
import time
from typing import Any, Callable, Dict, Optional, Tuple
import urllib.parse

from nicegui import run, ui
from plepa_engine.config import PROJECTS_DIR
from plepa_engine.reporter import open_in_explorer
from plepa_engine.services.asset_service import default_asset_service
from plepa_engine.services.generation_service import GenerationParams
from plepa_engine.services.job_manager import global_job_manager
from plepa_engine.services.upscale_service import default_upscale_service
from plepa_gui.pages.gallery_parts.data_helpers import parse_manifest_items_map, safe_notify

logger = logging.getLogger(__name__)


def parse_char_and_pose_code(filename: str) -> Tuple[Optional[str], Optional[str]]:
    """에셋 파일명에서 캐릭터 prefix와 포즈 코드를 추출합니다."""
    m_code = re.match(r"^([a-zA-Z0-9]+)_([a-zA-Z0-9]+)", filename)
    if not m_code:
        return None, None
    return m_code.group(1), m_code.group(2)


def find_origin_candidate(roster: str, main_asset_p: Path, prefix_val: Optional[str]) -> Path:
    """2-Track(_origin) 구조에서 본체 파일에 대응하는 무검열 원본 후보를 탐색합니다."""
    char_pfx = prefix_val or main_asset_p.name.split("_")[0]
    cand_sub = PROJECTS_DIR / roster / "assets" / f"{char_pfx}_origin" / main_asset_p.parent.name / main_asset_p.name
    cand_flat = PROJECTS_DIR / roster / "assets" / f"{char_pfx}_origin" / main_asset_p.name
    return cand_sub if cand_sub.is_file() else cand_flat


def render_lightbox_meta(meta_box: Any, curr_path: Path, manifest_cache: Dict[Path, Dict[str, Any]]) -> None:
    """라이트박스 하단 메타데이터 바(시드·생성시각·단축키)를 렌더링합니다."""
    meta_box.clear()
    prefix_val, code_val = parse_char_and_pose_code(curr_path.name)
    manifest_p = (
        (curr_path.parent.parent / "_batch_manifest.json")
        if (curr_path.parent.parent / "_batch_manifest.json").is_file()
        else (curr_path.parent / "_batch_manifest.json")
    )
    if manifest_p not in manifest_cache:
        loaded_m: Dict[str, Any] = {}
        if manifest_p.is_file():
            try:
                with open(manifest_p, "r", encoding="utf-8") as f:
                    loaded_m = parse_manifest_items_map(json.load(f))
            except Exception as exc:
                logger.debug("매니페스트 로드 스킵 (%s): %s", manifest_p, exc)
        manifest_cache[manifest_p] = loaded_m
    manifest_map = manifest_cache[manifest_p]
    manifest_item = manifest_map.get(str(code_val or ""), {}) or manifest_map.get(f"{prefix_val}_{code_val}", {})

    seed_val = manifest_item.get("seed") or "미기록"
    ts_val = manifest_item.get("timestamp", "-")
    with meta_box:
        with ui.row().classes("items-center gap-3"):
            ui.label(f"🔒 골든 시드: {seed_val}").classes("text-amber-300 font-bold")
            ui.label(f"🕒 생성시각: {ts_val}").classes("text-slate-400")
            ui.label(f"📁 {curr_path.name}").classes("text-slate-500 truncate max-w-sm")
        with ui.row().classes("items-center gap-2"):
            ui.label("단축키: ← 이전 | → 다음 | Space 원본/검열 토글").classes("text-[11px] text-slate-500")


async def enqueue_lightbox_reroll(
    prefix_val: str,
    code_val: str,
    reuse_seed: bool,
    target_item_path: Path,
    ctx: Dict[str, Any],
) -> None:
    """라이트박스에서 단독 리롤 작업을 GlobalJobManager FIFO 큐에 등록하고 결과를 UI에 반영합니다."""
    try:
        state = ctx["state"]
        r_params = GenerationParams(
            character_expr=prefix_val,
            pose_expr=code_val,
            roster=state["roster"],
            overwrite=True,
            censor=True,
            censor_style=state["censor_style"],
            censor_targets=state["censor_targets"],
            reuse_seed=reuse_seed,
        )
        done_event = threading.Event()
        callback_holder: Dict[str, Any] = {"results": [], "error": None}

        def _on_reroll_done(res_list, err):
            callback_holder["results"] = res_list
            callback_holder["error"] = err
            done_event.set()

        started, queue_pos = global_job_manager.enqueue_job(
            r_params, label=f"갤러리 리롤 {prefix_val}:{code_val}", on_complete=_on_reroll_done
        )
        ctx["sync_queue_panel"](True)
        ui.notify(
            f"🔄 #{code_val} {'골든 시드 고정' if reuse_seed else '새 시드'} 리롤 시작..."
            if started
            else f"⏳ #{code_val} 리롤이 대기열 #{queue_pos}에 등록되었습니다.",
            type="info",
        )

        await run.io_bound(done_event.wait)
        ctx["sync_queue_panel"](True)
        if callback_holder["error"] is not None:
            ui.notify(f"⚠️ 리롤 중단/오류: {callback_holder['error']}", type="warning")
            return

        results = callback_holder["results"]
        if not (results and results[0].success):
            ui.notify(f"❌ [{prefix_val}] #{code_val} 리롤 생성 실패", type="negative")
            return

        res_img = results[0].image_path
        rel = res_img.relative_to(PROJECTS_DIR).as_posix()
        ts_val = int(time.time())
        if rel in ctx["image_widgets_by_rel"]:
            ctx["refresh_single_thumbnail"](rel, ts_val)
        else:
            ctx["retouched_versions"][rel] = ts_val
        ui.notify(f"🎉 [{prefix_val}] #{code_val} 리롤 완료!", type="positive")

        items, nav_state = ctx["items"], ctx["nav_state"]
        if bool(ctx["dialog"].value and items and items[nav_state["idx"]] == target_item_path):
            ctx["curr"]["path"] = res_img
            ctx["curr"]["url"] = f"/projects_static/{rel}?t={ts_val}"
            ctx["url_cache"][res_img] = ctx["curr"]["url"]
            ctx["dim_cache"].pop(res_img, None)
            ctx["manifest_cache"].clear()
            ctx["refresh_all"]()
    except Exception as ex:
        ui.notify(f"❌ 리롤 오류: {ex}", type="negative")


def add_origin_and_retouch_buttons(
    p: Path,
    prefix_val: Optional[str],
    code_val: Optional[str],
    ctx: Dict[str, Any],
) -> None:
    """직접 검열 에디터, 원본 토글, 원본 복원 버튼을 추가합니다."""
    items, nav_state, state = ctx["items"], ctx["nav_state"], ctx["state"]
    main_asset_p = items[nav_state["idx"]] if items else p
    origin_cand = find_origin_candidate(state["roster"], main_asset_p, prefix_val)
    rel_main_asset = main_asset_p.relative_to(PROJECTS_DIR).as_posix()

    retouch_payload = {
        "relPath": rel_main_asset,
        "roster": state["roster"],
        "title": f"✏️ {main_asset_p.name} 수동 검열/덧칠",
        "imageUrl": f"/projects_static/{urllib.parse.quote(rel_main_asset, safe='/')}",
        "originUrl": (
            f"/projects_static/{urllib.parse.quote(origin_cand.relative_to(PROJECTS_DIR).as_posix(), safe='/')}"
            if origin_cand.is_file()
            else ""
        ),
    }

    def _on_retouch_saved_refresh(payload: dict) -> None:
        if not isinstance(payload, dict) or payload.get("rel_path") != rel_main_asset:
            return
        ts_val = payload.get("timestamp") or int(time.time())
        ctx["showing_origin"]["val"] = False
        ctx["curr"]["path"] = main_asset_p
        ctx["curr"]["url"] = f"/projects_static/{urllib.parse.quote(rel_main_asset, safe='/')}?t={ts_val}"
        ctx["url_cache"][main_asset_p] = ctx["curr"]["url"]
        ctx["refresh_single_thumbnail"](rel_main_asset, ts_val)
        ctx["refresh_all"]()

    ctx["active_lightbox_retouch_cb"]["fn"] = _on_retouch_saved_refresh

    async def open_manual_retouch():
        await ui.run_javascript(f"openRetouchEditor({json.dumps(retouch_payload, ensure_ascii=False)});")

    ui.button("✏️ 직접 검열", icon="brush", on_click=open_manual_retouch).props(
        "unelevated dense size=sm color=emerald-700 text-white font-bold"
    ).tooltip("기존 검열 제거(원본 로드) 후 직접 화이트 브러시/지우개로 편집하고 파일을 즉시 교체합니다")

    if not origin_cand.is_file():
        ctx["toggle_origin_holder"]["fn"] = None
        return

    def on_toggle_origin():
        ctx["showing_origin"]["val"] = not ctx["showing_origin"]["val"]
        target_f = origin_cand if ctx["showing_origin"]["val"] else main_asset_p
        ctx["curr"]["path"] = target_f
        ctx["curr"]["url"] = ctx["get_cached_url"](target_f)
        toggle_btn.text = "🛡️ 검열본" if ctx["showing_origin"]["val"] else "👁️ 원본"
        ctx["refresh_img"]()

    ctx["toggle_origin_holder"]["fn"] = on_toggle_origin
    toggle_btn = ui.button(
        "🛡️ 검열본" if ctx["showing_origin"]["val"] else "👁️ 원본",
        icon="visibility",
        on_click=on_toggle_origin,
    ).props("unelevated dense size=sm color=slate-700 text-amber-300 border border-amber-500/40").tooltip("무검열 원본과 검열본을 번갈아 비교합니다 (단축키: Space)")

    async def on_restore_origin():
        ok = await run.io_bound(default_asset_service.restore_from_origin, prefix_val, code_val, state["roster"])
        if not ok:
            ui.notify("복원 실패", type="negative")
            return
        ui.notify("⏪ 무검열 원본으로 복원되었습니다!", type="positive")
        ctx["showing_origin"]["val"] = False
        ctx["curr"]["path"] = main_asset_p
        rel = main_asset_p.relative_to(PROJECTS_DIR).as_posix()
        ts_val = int(time.time())
        ctx["curr"]["url"] = f"/projects_static/{rel}?t={ts_val}"
        ctx["url_cache"][main_asset_p] = ctx["curr"]["url"]
        ctx["refresh_single_thumbnail"](rel, ts_val)
        ctx["refresh_all"]()

    ui.button("⏪ 원본 복원", icon="undo", on_click=on_restore_origin).props("flat dense size=sm color=rose-400").tooltip(
        "assets/{char}_origin/의 무검열 원본을 본 폴더로 복사해 검열을 해제합니다"
    )


def add_upscale_and_utility_buttons(p: Path, is_already: bool, ctx: Dict[str, Any]) -> None:
    """4K AI 업스케일, 새 탭 뷰어, 폴더 열기, 닫기 버튼을 추가합니다."""

    async def on_upscale_click():
        upscale_btn.props("loading")
        ui.notify("🚀 AI 초해상화(4x-UltraSharp) 연산 중입니다... (약 15~20초 소요)", type="info")
        try:
            res_path = await run.io_bound(default_upscale_service.upscale_file, ctx["curr"]["path"], overwrite=False)
            if res_path and res_path.exists():
                ctx["curr"]["path"] = res_path
                rel = res_path.relative_to(PROJECTS_DIR).as_posix()
                ts_val = int(time.time())
                ctx["curr"]["url"] = f"/projects_static/{rel}?t={ts_val}"
                ctx["url_cache"][res_path] = ctx["curr"]["url"]
                ctx["dim_cache"].pop(res_path, None)
                ui.notify(f"🎉 4K 업스케일 완료: {res_path.name}", type="positive")
                ctx["refresh_all"]()
                if rel in ctx["image_widgets_by_rel"]:
                    ctx["refresh_single_thumbnail"](rel, ts_val)
                else:
                    ctx["render_content"]()
            else:
                ui.notify("❌ 4K 업스케일 생성에 실패했습니다.", type="negative")
        except Exception as ex:
            ui.notify(f"❌ 업스케일 오류: {ex}", type="negative")
        finally:
            upscale_btn.props(remove="loading")

    upscale_btn = ui.button(
        "4K 완료 (재연산)" if is_already else "✨ 4K AI 업스케일",
        icon="auto_fix_high",
        on_click=on_upscale_click,
    ).props(f"unelevated dense size=sm color={'emerald-700' if is_already else 'purple-600'} text-white").tooltip(
        "이미 4K 초고화질입니다 (클릭 시 재연산)" if is_already else "4x-UltraSharp 초해상화 모델로 4K(4096x6144) 무손실 업스케일"
    )

    view_url = f"/view_image?src={ctx['curr']['url']}&name={p.name}"
    ui.button("새 탭", icon="open_in_new", on_click=lambda u=view_url: ui.navigate.to(u, new_tab=True)).props(
        f'flat dense size=sm color=amber-400 href="{view_url}" target="_blank"'
    ).tooltip("새 탭에서 고화질 뷰어로 보기")

    def handle_open_folder():
        open_in_explorer(ctx["curr"]["path"])
        safe_notify(f"🖥️ PC 파일 탐색기를 열었습니다: {ctx['curr']['path'].name}", type="positive")

    ui.button(icon="folder", on_click=handle_open_folder).props("flat dense size=sm color=slate-300").tooltip("호스트 PC 파일 탐색기에서 해당 파일 위치 열기")
    ui.button(icon="close", on_click=ctx["dialog"].close).props("flat round dense color=slate-300")
