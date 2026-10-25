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

import json
from pathlib import Path
import time
from typing import Any, Dict, List
import urllib.parse

from fastapi.responses import HTMLResponse
from nicegui import app, ui
from plepa_engine.config import PROJECTS_DIR


def get_mobile_gallery_data(roster: str = "campus") -> Dict[str, Any]:
    """모바일 갤러리용 에셋 메타데이터 수집."""
    assets_dir = PROJECTS_DIR / roster / "assets"
    if not assets_dir.is_dir():
        return {"items": [], "chars": [], "total_missing": 0}

    chars = ["aya", "har", "kao", "mai", "shz", "yur"]
    recent_codes = {"112", "115", "131", "060", "064", "065", "066", "067", "068", "069", "071"}

    char_names = {
        "aya": "아야메 (Aya)",
        "har": "하루 (Haru)",
        "kao": "카오루 (Kaoru)",
        "mai": "마이 (Mai)",
        "shz": "시즈쿠 (Shizuku)",
        "yur": "유리카 (Yurika)",
    }

    now_ts = time.time()
    today_start = now_ts - (24 * 3600)  # 최근 24시간 이내

    items = []
    for char in chars:
        cdir = assets_dir / char
        if not cdir.is_dir():
            continue
        for f in sorted(cdir.rglob("*.webp")):
            if "_origin" in f.parts or "_censored" in f.name or "_trash" in f.parts:
                continue
            parts = f.stem.split("_", 2)
            code = parts[1] if len(parts) >= 2 else ""
            label = parts[2] if len(parts) >= 3 else ""

            rel_to_projects = f.relative_to(PROJECTS_DIR).as_posix()
            web_url = "/projects_static/" + urllib.parse.quote(rel_to_projects, safe="/")

            mtime = f.stat().st_mtime
            is_recent_mod = code in recent_codes
            is_newly_generated = mtime >= today_start

            items.append({
                "char": char,
                "char_name": char_names.get(char, char),
                "code": code,
                "label": label,
                "filename": f.name,
                "url": web_url,
                "rel_path": rel_to_projects,
                "is_recent": is_recent_mod,
                "is_new": is_newly_generated,
                "mtime": mtime,
            })

    from plepa_engine.services.asset_service import default_asset_service
    missing_map = default_asset_service.get_missing_poses_by_character(roster)
    total_missing = sum(len(v) for v in missing_map.values())

    return {
        "items": items,
        "chars": [{"id": c, "name": char_names.get(c, c)} for c in chars],
        "total_missing": total_missing,
        "roster": roster,
    }


def generate_mobile_viewer_html(roster: str = "campus") -> str:
    """순수 독립형 모바일 갤러리 HTML 문서 생성."""
    data = get_mobile_gallery_data(roster)
    data_json = json.dumps(data, ensure_ascii=False)

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
                <div style="display: flex; align-items: center; gap: 6px;">
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
                <button class="btn-chip active" id="chipRecent" onclick="setMode('recent')">✨ 최근수정본 (66)</button>
                <button class="btn-chip" id="chipNew" onclick="setMode('new')">🆕 방금생성됨</button>
                <button class="btn-chip" id="chipAll" onclick="setMode('all')">📂 전체</button>
                <div style="width: 1px; background: rgba(71,85,105,0.4); margin: 0 4px;"></div>
                <button class="btn-chip" id="char_all" onclick="setCharFilter('all')">전체캐릭</button>
                <button class="btn-chip" id="char_aya" onclick="setCharFilter('aya')">아야메</button>
                <button class="btn-chip" id="char_har" onclick="setCharFilter('har')">하루</button>
                <button class="btn-chip" id="char_kao" onclick="setCharFilter('kao')">카오루</button>
                <button class="btn-chip" id="char_mai" onclick="setCharFilter('mai')">마이</button>
                <button class="btn-chip" id="char_shz" onclick="setCharFilter('shz')">시즈쿠</button>
                <button class="btn-chip" id="char_yur" onclick="setCharFilter('yur')">유리카</button>
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
                <!-- Action Buttons: 삭제 & 리롤 & 이전/다음 -->
                <div style="display: flex; gap: 6px; align-items: center;">
                    <button class="btn-action btn-delete" onclick="triggerDelete(event)" title="에셋 삭제 및 휴지통 이동">
                        🗑️ 삭제
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
        let currentMode = 'recent'; // 'recent', 'new', 'all'
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
            ['all', 'aya', 'har', 'kao', 'mai', 'shz', 'yur'].forEach(c => {{
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
            subtitle.innerText = item.char_name + ' (' + item.char + ')';
            
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

        // 에셋 삭제 (휴지통 안전 이동)
        async function triggerDelete(e) {{
            if (e) e.stopPropagation();
            if (filteredItems.length === 0) return;

            const item = filteredItems[currentIndex];
            const targetName = '#' + item.code + ' ' + item.char_name;

            try {{
                const res = await fetch('/api/assets/delete', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
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
                    headers: {{ 'Content-Type': 'application/json' }},
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

        // 현재 포즈 단독 리롤
        async function triggerReroll(e) {{
            if (e) e.stopPropagation();
            if (filteredItems.length === 0) return;
            const item = filteredItems[currentIndex];

            showToast('🎲 #' + item.code + ' [' + item.char + '] 백그라운드 리롤 시작...');
            try {{
                await fetch('/api/assets/reroll', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{
                        char: item.char,
                        code: item.code,
                        roster: rawData.roster,
                        reuse_seed: false
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

            showToast('⚡ 누락 포즈 ' + count + '개 백그라운드 생성 시작...');
            try {{
                const res = await fetch('/api/assets/fill-missing', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ roster: rawData.roster }})
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


def render_mobile_viewer_page() -> None:
    """하위 호환용 NiceGUI 페이지 래퍼."""
    html_content = generate_mobile_viewer_html("campus")
    ui.html(html_content)
