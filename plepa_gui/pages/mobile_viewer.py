"""
plepa_gui.pages.mobile_viewer
스마트폰 모바일 터치 스와이프 전용 고품질 에셋 갤러리 뷰어.
- 순수 HTML5/CSS3/Vanilla JS 기반 초경량 고속 렌더링
- [🗑️ 즉시 삭제 (휴지통 & 실행취소 Undo)]
- [🎲 단독 리롤 (원클릭 백그라운드 재추첨)]
- [⚡ 누락 포즈 일괄 채우기]
- [🆕 방금/오늘 생성분 필터]
- 좌우 터치 스와이프 제스처
"""

from __future__ import annotations

import html
import json
from pathlib import Path
import time
from typing import Any, Dict, List, Optional
import urllib.parse

from fastapi.responses import HTMLResponse
from nicegui import app, ui
from plepa_engine.config import DEFAULT_ROSTER, PROJECTS_DIR
from plepa_engine.services.character_service import default_character_service
from plepa_gui.components.header import get_active_roster


def get_mobile_gallery_data(roster: Optional[str] = None) -> Dict[str, Any]:
    """모바일 갤러리용 에셋 메타데이터 수집 (로스터 캐릭터 동적 로드)."""
    target_roster = (roster or get_active_roster() or DEFAULT_ROSTER).strip()
    assets_dir = PROJECTS_DIR / target_roster / "assets"
    if not assets_dir.is_dir():
        return {"items": [], "chars": [], "total_missing": 0, "roster": target_roster}

    char_entries = default_character_service.list_characters(target_roster)
    char_defs = [
        {"id": c.prefix, "name": f"{c.name} ({c.prefix})", "short_name": c.name}
        for _, c, _ in char_entries
    ]
    if not char_defs:
        # 캐릭터 JSON이 없어도 assets 하위 디렉터리에서 자동 탐색
        discovered_dirs = sorted(
            d.name for d in assets_dir.iterdir()
            if d.is_dir() and not d.name.endswith("_origin") and not d.name.startswith("_")
        )
        char_defs = [{"id": pfx, "name": pfx, "short_name": pfx} for pfx in discovered_dirs]

    char_name_map = {c["id"]: c["name"] for c in char_defs}
    now_ts = time.time()
    today_start = now_ts - (24 * 3600)      # 최근 24시간 이내
    recent_start = now_ts - (7 * 24 * 3600)  # 최근 7일 이내

    items = []
    for c_info in char_defs:
        char = c_info["id"]
        cdir = assets_dir / char
        if not cdir.is_dir():
            continue

        manifest_qc_map: Dict[str, Dict[str, Any]] = {}
        manifest_path = cdir / "_batch_manifest.json"
        if manifest_path.is_file():
            try:
                m_data = json.loads(manifest_path.read_text(encoding="utf-8"))
                for m_item in m_data.get("items", []):
                    m_code = str(m_item.get("code", "")).strip()
                    if m_code:
                        manifest_qc_map[m_code] = {
                            "qc_passed": m_item.get("qc_passed", True),
                            "qc_reason": m_item.get("qc_reason"),
                        }
            except Exception:
                pass

        for f in sorted(cdir.rglob("*.webp")):
            if "_origin" in f.parts or "_censored" in f.name or "_trash" in f.parts:
                continue
            parts = f.stem.split("_", 2)
            code = parts[1] if len(parts) >= 2 else ""
            label = parts[2] if len(parts) >= 3 else ""

            rel_to_projects = f.relative_to(PROJECTS_DIR).as_posix()
            web_url = "/projects_static/" + urllib.parse.quote(rel_to_projects, safe="/")

            mtime = f.stat().st_mtime
            is_newly_generated = mtime >= today_start
            is_recent_mod = mtime >= recent_start
            qc_meta = manifest_qc_map.get(code, {})

            items.append({
                "char": char,
                "char_name": char_name_map.get(char, char),
                "code": code,
                "label": label,
                "filename": f.name,
                "url": web_url,
                "rel_path": rel_to_projects,
                "is_recent": is_recent_mod,
                "is_new": is_newly_generated,
                "mtime": mtime,
                "qc_passed": qc_meta.get("qc_passed", True),
                "qc_reason": qc_meta.get("qc_reason"),
            })

    from plepa_engine.services.asset_service import default_asset_service
    missing_map = default_asset_service.get_missing_poses_by_character(target_roster)
    total_missing = sum(len(v) for v in missing_map.values())

    return {
        "items": items,
        "chars": char_defs,
        "total_missing": total_missing,
        "roster": target_roster,
    }


def generate_mobile_viewer_html(roster: Optional[str] = None) -> str:
    """순수 독립형 모바일 갤러리 HTML 문서 생성."""
    data = get_mobile_gallery_data(roster)
    data_json = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    recent_count = sum(1 for item in data["items"] if item.get("is_recent"))
    initial_mode = "recent" if recent_count > 0 else "all"
    char_buttons_html = "\n".join(
        f'                <button class="btn-chip" id="char_{html.escape(c["id"], quote=True)}" '
        f'onclick="setCharFilter({json.dumps(c["id"])})">{html.escape(c.get("short_name", c["id"]))}</button>'
        for c in data.get("chars", [])
    )

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no, viewport-fit=cover">
    <meta name="apple-mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
    <title>📱 PLEPA Mobile Studio</title>
    <style>
        * {{ box-sizing: border-box; -webkit-tap-highlight-color: transparent; }}
        html, body {{
            margin: 0; padding: 0; width: 100%; height: 100%; height: 100dvh;
            background: #020617; color: #f8fafc; overflow: hidden;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            user-select: none; -webkit-user-select: none;
        }}
        .viewer-container {{
            position: relative; width: 100%; height: 100dvh;
            display: flex; flex-direction: column; overflow: hidden;
        }}
        .stage {{
            flex: 1; position: relative; width: 100%; height: 100%;
            display: flex; align-items: center; justify-content: center;
            overflow: hidden; touch-action: pan-y pinch-zoom;
        }}
        .slide-img {{
            max-width: 100vw; max-height: 100%; width: auto; height: auto;
            object-fit: contain; transition: transform 0.2s cubic-bezier(0.25, 1, 0.5, 1), opacity 0.2s ease;
            box-shadow: 0 20px 40px rgba(0,0,0,0.8);
        }}
        .overlay {{
            position: absolute; left: 0; right: 0; z-index: 20;
            background: linear-gradient(180deg, rgba(2,6,23,0.94) 0%, rgba(2,6,23,0.5) 80%, transparent 100%);
            padding: 12px 16px; transition: opacity 0.25s ease, transform 0.25s ease;
            backdrop-filter: blur(12px); -webkit-backdrop-filter: blur(12px);
        }}
        .overlay.top {{ top: 0; padding-top: max(12px, env(safe-area-inset-top)); }}
        .overlay.bottom {{
            bottom: 0;
            background: linear-gradient(0deg, rgba(2,6,23,0.96) 0%, rgba(2,6,23,0.6) 80%, transparent 100%);
            padding-bottom: max(16px, env(safe-area-inset-bottom));
        }}
        .overlay.hidden {{ opacity: 0; pointer-events: none; transform: translateY(-10px); }}
        .overlay.bottom.hidden {{ transform: translateY(10px); }}
        .btn-chip {{
            background: rgba(30, 41, 59, 0.85); border: 1px solid rgba(71, 85, 105, 0.6);
            color: #cbd5e1; padding: 6px 13px; border-radius: 9999px; font-size: 13px;
            font-weight: 500; cursor: pointer; white-space: nowrap; transition: all 0.15s ease;
            display: inline-flex; align-items: center; gap: 4px;
        }}
        .btn-chip.active {{
            background: #2563eb; border-color: #60a5fa; color: #ffffff;
            box-shadow: 0 0 12px rgba(37, 99, 235, 0.6);
        }}
        .btn-action {{
            padding: 8px 14px; border-radius: 10px; font-size: 13px; font-weight: 700;
            cursor: pointer; border: none; display: inline-flex; align-items: center; gap: 5px;
            transition: all 0.15s ease;
        }}
        .btn-action:active {{ transform: scale(0.95); }}
        .btn-delete {{
            background: rgba(225, 29, 72, 0.25); border: 1px solid rgba(244, 63, 94, 0.6); color: #fda4af;
        }}
        .btn-delete:active {{ background: rgba(225, 29, 72, 0.5); }}
        .btn-reroll {{
            background: rgba(139, 92, 246, 0.25); border: 1px solid rgba(167, 139, 250, 0.6); color: #c4b5fd;
        }}
        .btn-recensor {{
            background: rgba(37, 99, 235, 0.28); border: 1px solid rgba(96, 165, 250, 0.65); color: #93c5fd;
        }}
        .btn-origin {{
            background: rgba(217, 119, 6, 0.25); border: 1px solid rgba(251, 191, 36, 0.6); color: #fcd34d;
        }}
        .censor-select-mini {{
            background: rgba(15, 23, 42, 0.9); border: 1px solid rgba(71, 85, 105, 0.8);
            color: #e2e8f0; border-radius: 6px; padding: 3px 6px; font-size: 11px; outline: none;
        }}
        .btn-fill {{
            background: #059669; border: 1px solid #34d399; color: #ffffff;
            box-shadow: 0 0 10px rgba(5, 150, 105, 0.5);
        }}
        .nav-tap-zone {{
            position: absolute; top: 0; bottom: 0; width: 28%; z-index: 10;
        }}
        .nav-tap-left {{ left: 0; }}
        .nav-tap-right {{ right: 0; }}
        .nav-indicator {{
            position: absolute; top: 50%; transform: translateY(-50%);
            background: rgba(15, 23, 42, 0.7); border: 1px solid rgba(51, 65, 85, 0.6);
            color: #94a3b8; width: 40px; height: 40px; border-radius: 50%;
            display: flex; align-items: center; justify-content: center;
            opacity: 0; transition: opacity 0.2s ease; pointer-events: none;
        }}
        .nav-indicator.left {{ left: 12px; }}
        .nav-indicator.right {{ right: 12px; }}
        .stage:hover .nav-indicator {{ opacity: 0.7; }}
        
        /* 토스트 알림 배너 */
        #toastBanner {{
            position: fixed; top: 18px; left: 50%; transform: translateX(-50%) translateY(-100px);
            background: rgba(15, 23, 42, 0.95); border: 1px solid #38bdf8; color: #f8fafc;
            padding: 10px 18px; border-radius: 9999px; font-size: 13px; font-weight: 600;
            z-index: 100; box-shadow: 0 10px 25px rgba(0,0,0,0.7);
            display: flex; align-items: center; gap: 10px; transition: transform 0.3s cubic-bezier(0.18, 0.89, 0.32, 1.28);
            pointer-events: none;
        }}
        #toastBanner.show {{
            transform: translateX(-50%) translateY(0); pointer-events: auto;
        }}
        .btn-undo {{
            background: #38bdf8; color: #020617; border: none; padding: 4px 10px;
            border-radius: 9999px; font-size: 11px; font-weight: 800; cursor: pointer;
        }}
    </style>
</head>
<body>
    <!-- 토스트 배너 -->
    <div id="toastBanner">
        <span id="toastMsg">알림</span>
        <button id="toastUndoBtn" class="btn-undo" style="display:none;" onclick="triggerUndo()">실행 취소</button>
    </div>

    <div id="mobileApp" class="viewer-container">
        <!-- Top Overlay -->
        <div id="topOverlay" class="overlay top">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                <div style="display: flex; align-items: center; gap: 8px;">
                    <a href="/gallery" style="color: #94a3b8; text-decoration: none; font-size: 14px; display: flex; align-items: center; gap: 4px;">
                        ❮ PC스튜디오
                    </a>
                    <span style="font-size: 14px; font-weight: 700; color: #38bdf8;">📱 PLEPA MOBILE</span>
                </div>
                <div style="display: flex; align-items: center; gap: 6px; flex-wrap: wrap;">
                    <select id="censorStyleSelect" class="censor-select-mini" title="즉시 재검열 및 리롤 스타일">
                        <option value="white_silhouette" selected>white_silhouette</option>
                        <option value="black_silhouette">black_silhouette</option>
                        <option value="mosaic">mosaic</option>
                        <option value="bar">bar</option>
                        <option value="slim_bar">slim_bar</option>
                        <option value="shadow">shadow</option>
                        <option value="debug_bbox">debug_bbox</option>
                    </select>
                    <label style="display:inline-flex;align-items:center;gap:3px;font-size:10px;color:#cbd5e1;cursor:pointer;">
                        <input type="checkbox" id="anchorFallbackToggle" />
                        <span>폴백</span>
                    </label>
                    <button class="btn-action btn-fill" id="fillMissingBtn" onclick="triggerFillMissing()" style="padding: 4px 10px; font-size: 11px;">
                        ⚡ 누락 채우기 (<span id="missingCountBadge">0</span>)
                    </button>
                    <div id="counterBadge" style="font-size: 12px; font-weight: 600; color: #94a3b8; background: rgba(30,41,59,0.8); padding: 4px 8px; border-radius: 6px;">
                        0 / 0
                    </div>
                </div>
            </div>
            <!-- Filter Chips -->
            <div style="display: flex; gap: 6px; overflow-x: auto; padding-bottom: 4px; scrollbar-width: none;">
                <button class="btn-chip {'active' if initial_mode == 'recent' else ''}" id="chipRecent" onclick="setMode('recent')">✨ 최근수정본 ({recent_count})</button>
                <button class="btn-chip" id="chipNew" onclick="setMode('new')">🆕 방금생성됨</button>
                <button class="btn-chip {'active' if initial_mode == 'all' else ''}" id="chipAll" onclick="setMode('all')">📂 전체</button>
                <div style="width: 1px; background: rgba(71,85,105,0.4); margin: 0 4px;"></div>
                <button class="btn-chip" id="char_all" onclick="setCharFilter('all')">전체캐릭</button>
{char_buttons_html}
            </div>
        </div>

        <!-- Main Swipe Stage -->
        <div class="stage" id="stage" onclick="onStageClick(event)">
            <div class="nav-tap-zone nav-tap-left" onclick="prev(event)"></div>
            <div class="nav-tap-zone nav-tap-right" onclick="next(event)"></div>
            <div class="nav-indicator left">❮</div>
            <div class="nav-indicator right">❯</div>
            <img id="mainImg" class="slide-img" src="" alt="에셋" />
        </div>

        <!-- Bottom Overlay -->
        <div id="bottomOverlay" class="overlay bottom">
            <div style="display: flex; justify-content: space-between; align-items: center; gap: 8px;">
                <div style="flex: 1; min-width: 0;">
                    <div id="poseTitle" style="font-size: 15px; font-weight: 700; color: #f1f5f9; text-shadow: 0 2px 4px rgba(0,0,0,0.9); truncate;">
                        포즈 정보
                    </div>
                    <div id="poseSubtitle" style="font-size: 12px; color: #94a3b8; margin-top: 2px;">
                        캐릭터 및 코드
                    </div>
                </div>
                <!-- Action Buttons: 삭제 & 원본 & 재검열 & 리롤 & 이전/다음 -->
                <div style="display: flex; gap: 6px; align-items: center; flex-wrap: wrap; justify-content: flex-end;">
                    <button class="btn-action btn-delete" onclick="triggerDelete(event)" title="에셋 삭제 및 휴지통 이동">
                        🗑️ 삭제
                    </button>
                    <button class="btn-action btn-origin" onclick="triggerRestoreOrigin(event)" title="무검열 원본(_origin)으로 즉시 복원">
                        🔄 원본
                    </button>
                    <button class="btn-action btn-recensor" onclick="triggerReapplyCensor(event)" title="원본 기반 0.2초 즉시 재검열">
                        ⚡ 재검열
                    </button>
                    <button class="btn-action btn-reroll" onclick="triggerReroll(event)" title="새로운 시드로 즉시 다시 생성">
                        🎲 리롤
                    </button>
                    <button class="btn-chip" onclick="prev(event)" style="padding: 8px 12px;">❮</button>
                    <button class="btn-chip" onclick="next(event)" style="padding: 8px 12px; background: #2563eb; color: #fff; border-color: #60a5fa;">❯</button>
                </div>
            </div>
        </div>
    </div>

    <script>
        const rawData = {data_json};
        let currentMode = '{initial_mode}'; // 'recent', 'new', 'all'
        let currentChar = 'all';
        let filteredItems = [];
        let currentIndex = 0;
        let lastDeletedBundle = null;
        let toastTimeout = null;

        // 누락 포즈 카운트 초기화
        document.getElementById('missingCountBadge').innerText = rawData.total_missing || 0;

        function showToast(msg, canUndo = false) {{
            const el = document.getElementById('toastBanner');
            document.getElementById('toastMsg').innerText = msg;
            const undoBtn = document.getElementById('toastUndoBtn');
            undoBtn.style.display = canUndo ? 'inline-block' : 'none';
            el.classList.add('show');
            if (toastTimeout) clearTimeout(toastTimeout);
            toastTimeout = setTimeout(() => {{
                el.classList.remove('show');
            }}, 5000);
        }}

        function applyFilters() {{
            filteredItems = rawData.items.filter(item => {{
                if (currentMode === 'recent' && !item.is_recent) return false;
                if (currentMode === 'new' && !item.is_new) return false;
                if (currentChar !== 'all' && item.char !== currentChar) return false;
                return true;
            }});
            if (currentIndex >= filteredItems.length) {{
                currentIndex = Math.max(0, filteredItems.length - 1);
            }}
            updateView();
        }}

        function setMode(mode) {{
            currentMode = mode;
            document.getElementById('chipRecent').classList.toggle('active', mode === 'recent');
            document.getElementById('chipNew').classList.toggle('active', mode === 'new');
            document.getElementById('chipAll').classList.toggle('active', mode === 'all');
            applyFilters();
        }}

        function setCharFilter(charId) {{
            currentChar = charId;
            const charIds = ['all'].concat((rawData.chars || []).map(c => c.id));
            charIds.forEach(c => {{
                const el = document.getElementById('char_' + c);
                if (el) el.classList.toggle('active', c === charId);
            }});
            applyFilters();
        }}

        function updateView() {{
            const total = filteredItems.length;
            const counter = document.getElementById('counterBadge');
            const mainImg = document.getElementById('mainImg');
            const title = document.getElementById('poseTitle');
            const subtitle = document.getElementById('poseSubtitle');

            if (total === 0) {{
                counter.innerText = '0 / 0';
                title.innerText = '표시할 에셋이 없습니다';
                subtitle.innerText = '필터를 변경해보세요';
                mainImg.src = '';
                return;
            }}

            const item = filteredItems[currentIndex];
            counter.innerText = (currentIndex + 1) + ' / ' + total;
            title.innerText = '#' + item.code + ' ' + (item.label || item.filename);
            subtitle.innerText = item.char_name + ' (' + item.char + ')' + (item.qc_passed === false ? ' ⚠️ ' + (item.qc_reason || 'QC 경고') : '');
            
            mainImg.style.opacity = '0.4';
            mainImg.src = item.url;
            mainImg.onload = () => {{
                mainImg.style.opacity = '1';
            }};

            // 다음 2장 사전 프리로드
            if (currentIndex + 1 < total) {{
                const nextImg = new Image();
                nextImg.src = filteredItems[currentIndex + 1].url;
            }}
            if (currentIndex + 2 < total) {{
                const next2 = new Image();
                next2.src = filteredItems[currentIndex + 2].url;
            }}
        }}

        function prev(e) {{
            if (e) e.stopPropagation();
            if (filteredItems.length === 0) return;
            currentIndex = (currentIndex - 1 + filteredItems.length) % filteredItems.length;
            updateView();
        }}

        function next(e) {{
            if (e) e.stopPropagation();
            if (filteredItems.length === 0) return;
            currentIndex = (currentIndex + 1) % filteredItems.length;
            updateView();
        }}

        function getPlepaAuthHeaders(extra = {{}}) {{
            const headers = Object.assign({{}}, extra || {{}});
            const tok = new URLSearchParams(window.location.search).get('token');
            if (tok) headers['X-Plepa-Token'] = tok;
            return headers;
        }}

        function getSelectedCensorOptions() {{
            const styleEl = document.getElementById('censorStyleSelect');
            const anchorEl = document.getElementById('anchorFallbackToggle');
            return {{
                censor_style: styleEl ? styleEl.value : 'white_silhouette',
                censor_targets: 'penis',
                min_confidence: 0.16,
                enable_anchor_fallback: !!(anchorEl && anchorEl.checked)
            }};
        }}

        // 에셋 삭제 (휴지통 안전 이동)
        async function triggerDelete(e) {{
            if (e) e.stopPropagation();
            if (filteredItems.length === 0) return;

            const item = filteredItems[currentIndex];
            const targetName = '#' + item.code + ' ' + item.char_name;

            try {{
                const res = await fetch('/api/assets/delete', {{
                    method: 'POST',
                    headers: getPlepaAuthHeaders({{ 'Content-Type': 'application/json' }}),
                    body: JSON.stringify({{ rel_path: item.rel_path, roster: rawData.roster }})
                }});
                const data = await res.json();
                if (data.success) {{
                    lastDeletedBundle = {{ item: item, moved: data.data.moved }};
                    // 목록에서 제거
                    rawData.items = rawData.items.filter(x => x.rel_path !== item.rel_path);
                    applyFilters();
                    showToast('🗑️ ' + targetName + ' 휴지통 이동됨', true);
                    // 누락 수 업데이트
                    const missEl = document.getElementById('missingCountBadge');
                    missEl.innerText = parseInt(missEl.innerText || 0) + 1;
                }} else {{
                    showToast('❌ 삭제 실패');
                }}
            }} catch (err) {{
                showToast('❌ 오류: ' + err.message);
            }}
        }}

        // 삭제 실행 취소 (Undo)
        async function triggerUndo() {{
            if (!lastDeletedBundle) return;
            try {{
                const res = await fetch('/api/assets/undo', {{
                    method: 'POST',
                    headers: getPlepaAuthHeaders({{ 'Content-Type': 'application/json' }}),
                    body: JSON.stringify({{ moved: lastDeletedBundle.moved }})
                }});
                const data = await res.json();
                if (data.success) {{
                    rawData.items.push(lastDeletedBundle.item);
                    applyFilters();
                    showToast('✅ 원상 복원 완료!');
                    lastDeletedBundle = null;
                }} else {{
                    showToast('❌ 복원 실패');
                }}
            }} catch (err) {{
                showToast('❌ 오류: ' + err.message);
            }}
        }}

        // 무검열 원본(_origin) 즉시 복원
        async function triggerRestoreOrigin(e) {{
            if (e) e.stopPropagation();
            if (filteredItems.length === 0) return;
            const item = filteredItems[currentIndex];
            if (!confirm('#' + item.code + ' [' + item.char + '] 이미지를 무검열 원본(_origin)으로 복원하시겠습니까?')) return;

            try {{
                const res = await fetch('/api/assets/restore-origin', {{
                    method: 'POST',
                    headers: getPlepaAuthHeaders({{ 'Content-Type': 'application/json' }}),
                    body: JSON.stringify({{ rel_path: item.rel_path, roster: rawData.roster }})
                }});
                const data = await res.json();
                if (res.ok && data.success) {{
                    item.url = item.url.split('?')[0] + '?t=' + Date.now();
                    updateView();
                    showToast('✅ 원본 이미지로 복원 완료!');
                }} else {{
                    showToast('❌ 원본 복원 실패: ' + (data.detail || '알 수 없는 오류'));
                }}
            }} catch (err) {{
                showToast('❌ 요청 오류: ' + err.message);
            }}
        }}

        // 0.2초 즉시 재검열
        async function triggerReapplyCensor(e) {{
            if (e) e.stopPropagation();
            if (filteredItems.length === 0) return;
            const item = filteredItems[currentIndex];
            const opts = getSelectedCensorOptions();

            showToast('⚡ #' + item.code + ' ' + opts.censor_style + ' 재검열 중...');
            try {{
                const res = await fetch('/api/assets/reapply-censor', {{
                    method: 'POST',
                    headers: getPlepaAuthHeaders({{ 'Content-Type': 'application/json' }}),
                    body: JSON.stringify({{
                        rel_path: item.rel_path,
                        roster: rawData.roster,
                        pose_code: item.code,
                        censor_style: opts.censor_style,
                        censor_targets: opts.censor_targets,
                        min_confidence: opts.min_confidence,
                        enable_anchor_fallback: opts.enable_anchor_fallback
                    }})
                }});
                const data = await res.json();
                if (res.ok && data.success) {{
                    item.url = item.url.split('?')[0] + '?t=' + Date.now();
                    updateView();
                    showToast('⚡ 재검열 완료 (' + opts.censor_style + ', 탐지 ' + (data.detected_count ?? 0) + '건)');
                }} else {{
                    showToast('❌ 재검열 실패: ' + (data.detail || '알 수 없는 오류'));
                }}
            }} catch (err) {{
                showToast('❌ 요청 오류: ' + err.message);
            }}
        }}

        // 현재 포즈 단독 리롤
        async function triggerReroll(e) {{
            if (e) e.stopPropagation();
            if (filteredItems.length === 0) return;
            const item = filteredItems[currentIndex];
            const opts = getSelectedCensorOptions();

            showToast('🎲 #' + item.code + ' [' + item.char + '] 백그라운드 리롤 시작...');
            try {{
                await fetch('/api/assets/reroll', {{
                    method: 'POST',
                    headers: getPlepaAuthHeaders({{ 'Content-Type': 'application/json' }}),
                    body: JSON.stringify({{
                        char: item.char,
                        code: item.code,
                        roster: rawData.roster,
                        reuse_seed: false,
                        censor_style: opts.censor_style,
                        censor_targets: opts.censor_targets,
                        auto_qc: true
                    }})
                }});
            }} catch (err) {{
                showToast('❌ 리롤 요청 오류: ' + err.message);
            }}
        }}

        // 누락 포즈 전체 일괄 생성
        async function triggerFillMissing() {{
            const count = document.getElementById('missingCountBadge').innerText;
            if (count === '0') {{
                showToast('✨ 누락된 포즈가 없습니다. 모든 포즈 완비!');
                return;
            }}
            if (!confirm('현재 로스터의 비어있는 포즈 ' + count + '개를 모두 백그라운드로 자동 생성하시겠습니까?')) return;

            const opts = getSelectedCensorOptions();
            showToast('⚡ 누락 포즈 ' + count + '개 백그라운드 생성 시작...');
            try {{
                const res = await fetch('/api/assets/fill-missing', {{
                    method: 'POST',
                    headers: getPlepaAuthHeaders({{ 'Content-Type': 'application/json' }}),
                    body: JSON.stringify({{
                        roster: rawData.roster,
                        censor_style: opts.censor_style,
                        censor_targets: opts.censor_targets,
                        auto_qc: true
                    }})
                }});
                const data = await res.json();
                showToast('🚀 ' + data.message);
            }} catch (err) {{
                showToast('❌ 요청 오류: ' + err.message);
            }}
        }}

        let uiVisible = true;
        function onStageClick(e) {{
            const rect = e.currentTarget.getBoundingClientRect();
            const x = e.clientX - rect.left;
            const w = rect.width;
            if (x < w * 0.28 || x > w * 0.72) return;
            
            uiVisible = !uiVisible;
            document.getElementById('topOverlay').classList.toggle('hidden', !uiVisible);
            document.getElementById('bottomOverlay').classList.toggle('hidden', !uiVisible);
        }}

        // 터치 스와이프 제스처
        let touchStartX = 0;
        let touchStartY = 0;
        const stage = document.getElementById('stage');

        stage.addEventListener('touchstart', (e) => {{
            touchStartX = e.changedTouches[0].screenX;
            touchStartY = e.changedTouches[0].screenY;
        }}, {{ passive: true }});

        stage.addEventListener('touchend', (e) => {{
            const touchEndX = e.changedTouches[0].screenX;
            const touchEndY = e.changedTouches[0].screenY;
            const diffX = touchEndX - touchStartX;
            const diffY = touchEndY - touchStartY;

            if (Math.abs(diffX) > Math.abs(diffY) && Math.abs(diffX) > 40) {{
                if (diffX > 0) prev();
                else next();
            }}
        }}, {{ passive: true }});

        // PC 키보드 화살표
        window.addEventListener('keydown', (e) => {{
            if (e.key === 'ArrowLeft') prev();
            if (e.key === 'ArrowRight' || e.key === ' ') next();
            if (e.key === 'Delete') triggerDelete();
            if (e.key === 'r' || e.key === 'R') triggerReroll();
        }});

        // 첫 진입 시 초기화
        setCharFilter('all');
    </script>
</body>
</html>"""


def render_mobile_viewer_page(roster: Optional[str] = None) -> None:
    """하위 호환용 NiceGUI 페이지 래퍼."""
    html_content = generate_mobile_viewer_html(roster or get_active_roster())
    ui.html(html_content)
