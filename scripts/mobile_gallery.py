import glob
import html
import os
import sys
import time
from pathlib import Path
from typing import Dict, Optional
from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
import uvicorn

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from plepa_engine.config import DEFAULT_ROSTER, PROJECTS_DIR
from plepa_engine.services.character_service import default_character_service
from plepa_engine.services.pose_service import default_pose_service

app = FastAPI(title="Plepa Realtime Mobile Gallery")


def _resolve_active_roster() -> str:
    env_roster = os.environ.get("PLEPA_MOBILE_ROSTER", "").strip()
    if env_roster:
        return env_roster
    if (PROJECTS_DIR / DEFAULT_ROSTER / "assets").is_dir():
        return DEFAULT_ROSTER
    for r in default_character_service.list_rosters():
        if (PROJECTS_DIR / r / "assets").is_dir():
            return r
    return DEFAULT_ROSTER


ACTIVE_ROSTER = _resolve_active_roster()
BENCH1_DIR = PROJECTS_DIR / ACTIVE_ROSTER / "artist_benchmark"
BENCH2_DIR = PROJECTS_DIR / ACTIVE_ROSTER / "artist_benchmark_v2"
BENCH_RATATATA_DIR = PROJECTS_DIR / ACTIVE_ROSTER / "artist_benchmark_ratatata"
if BENCH1_DIR.is_dir():
    app.mount("/bench1", StaticFiles(directory=BENCH1_DIR, html=True), name="bench1")
if BENCH2_DIR.is_dir():
    app.mount("/bench2", StaticFiles(directory=BENCH2_DIR, html=True), name="bench2")
if BENCH_RATATATA_DIR.is_dir():
    app.mount("/bench_ratatata", StaticFiles(directory=BENCH_RATATATA_DIR, html=True), name="bench_ratatata")

ASSETS_DIR = PROJECTS_DIR / ACTIVE_ROSTER / "assets"

LEGACY_CHAR_NAMES: Dict[str, str] = {
    "hay": "설하율 (4녀)",
    "ser": "설세린 (2녀)",
    "sia": "설시아 (3녀)",
    "yua": "설유아 (1녀)",
}


def _load_char_names(roster: str) -> Dict[str, str]:
    names: Dict[str, str] = {}
    try:
        for _, c, _ in default_character_service.list_characters(roster):
            code = str(getattr(c, "prefix", "") or "").lower()
            if not code:
                continue
            if code in LEGACY_CHAR_NAMES:
                names[code] = LEGACY_CHAR_NAMES[code]
            else:
                char_name = str(getattr(c, "name", "") or "").strip()
                names[code] = f"{char_name} ({code})" if char_name and char_name != code else code.upper()
    except Exception:
        pass
    if not names and roster == "ykn":
        return dict(LEGACY_CHAR_NAMES)
    return names


CHAR_NAMES = _load_char_names(ACTIVE_ROSTER)


def _calc_total_target(roster: str, char_count: int) -> int:
    try:
        pose_db = default_pose_service.load_pose_db(engine="sdxl", roster=roster)
        if pose_db and char_count > 0:
            return char_count * len(pose_db)
    except Exception:
        pass
    return max(char_count * 100, 1)


TOTAL_TARGET = _calc_total_target(ACTIVE_ROSTER, len(CHAR_NAMES))

@app.get("/api/status")
def get_status(char: Optional[str] = None):
    # Scan all webp files excluding _origin
    pattern = str(ASSETS_DIR / "**" / "*.webp")
    all_files = glob.glob(pattern, recursive=True)
    
    items = []
    char_names = dict(CHAR_NAMES) if CHAR_NAMES else _load_char_names(ACTIVE_ROSTER)
    char_counts = {c: 0 for c in char_names}
    
    for f in all_files:
        if "_origin" in f or "새 폴더" in f or "ckpt_" in f:
            continue
        p = Path(f)
        rel = p.relative_to(ASSETS_DIR)
        parts = rel.parts
        if not parts:
            continue
        c_code = parts[0].lower()
        if c_code not in char_counts:
            char_counts[c_code] = 0
            char_names.setdefault(c_code, LEGACY_CHAR_NAMES.get(c_code, c_code.upper()))
        char_counts[c_code] += 1
            
        mtime = os.path.getmtime(f)
        
        # Filter by character if requested
        if char and char != "all" and c_code != char:
            continue
            
        # Parse label
        filename = p.name
        label = p.stem
        # e.g. hay_043_침대숙면 -> 043 침대숙면
        tokens = filename.replace(".webp", "").split("_")
        display_name = filename
        if len(tokens) >= 3:
            display_name = f"#{tokens[1]} {tokens[2]}"
        elif len(tokens) == 2:
            display_name = f"#{tokens[1]}"
            
        items.append({
            "filename": filename,
            "char": c_code,
            "char_name": char_names.get(c_code, c_code),
            "display_name": display_name,
            "subfolder": parts[1] if len(parts) > 2 else "",
            "url": f"/asset/{rel.as_posix()}",
            "mtime": mtime,
            "mtime_str": time.strftime("%H:%M:%S", time.localtime(mtime))
        })
        
    # Sort newest first
    items.sort(key=lambda x: x["mtime"], reverse=True)
    
    total_count = sum(char_counts.values())
    target_count = _calc_total_target(ACTIVE_ROSTER, len(char_counts)) if TOTAL_TARGET <= 1 else TOTAL_TARGET
    progress_pct = round((total_count / max(target_count, 1)) * 100, 1)
    
    return {
        "roster": ACTIVE_ROSTER,
        "total_count": total_count,
        "target": target_count,
        "progress_pct": progress_pct,
        "char_names": char_names,
        "char_counts": char_counts,
        "images": items
    }

@app.get("/asset/{file_path:path}")
def serve_asset(file_path: str):
    try:
        base_dir = ASSETS_DIR.resolve()
        target = (base_dir / file_path).resolve()
        if not target.is_relative_to(base_dir):
            return HTMLResponse("Forbidden", status_code=403)
    except Exception:
        return HTMLResponse("Invalid Path", status_code=400)
    if "_origin" in target.parts:
        return HTMLResponse("Forbidden", status_code=403)
    if not target.exists() or not target.is_file():
        return HTMLResponse("File Not Found", status_code=404)
    return FileResponse(target, media_type="image/webp")

@app.get("/", response_class=HTMLResponse)
def index():
    safe_roster = html.escape(ACTIVE_ROSTER.upper())
    initial_tabs = ['<button class="tab-btn active" data-char="all">전체 (0)</button>']
    for c_code, c_label in CHAR_NAMES.items():
        initial_tabs.append(
            f'<button class="tab-btn" data-char="{html.escape(c_code, quote=True)}">{html.escape(c_label)} (0)</button>'
        )
    tabs_markup = "\n            ".join(initial_tabs)
    html_doc = """<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>플에파 __ROSTER__ 실시간 모바일 갤러리</title>
    <style>
        :root {
            --bg-color: #0f1117;
            --card-bg: #1a1d27;
            --text-main: #f0f2f5;
            --text-sub: #9ba1b0;
            --primary: #ff4d88;
            --primary-glow: rgba(255, 77, 136, 0.3);
            --border: #282c3f;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; -webkit-tap-highlight-color: transparent; }
        body {
            background-color: var(--bg-color);
            color: var(--text-main);
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
            padding-bottom: 60px;
        }
        header {
            position: sticky;
            top: 0;
            z-index: 100;
            background: rgba(15, 17, 23, 0.95);
            backdrop-filter: blur(12px);
            border-bottom: 1px solid var(--border);
            padding: 12px 16px;
        }
        .header-top {
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 8px;
        }
        .header-title {
            font-size: 17px;
            font-weight: 700;
            color: #fff;
            display: flex;
            align-items: center;
            gap: 6px;
        }
        .live-badge {
            background: #00e676;
            color: #000;
            font-size: 10px;
            font-weight: 800;
            padding: 2px 6px;
            border-radius: 10px;
            animation: pulse 1.5s infinite;
        }
        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.4; }
        }
        .progress-box {
            background: var(--card-bg);
            border-radius: 8px;
            padding: 8px 12px;
            margin-bottom: 8px;
            border: 1px solid var(--border);
        }
        .progress-label {
            display: flex;
            justify-content: space-between;
            font-size: 12px;
            color: var(--text-sub);
            margin-bottom: 5px;
        }
        .progress-bar-bg {
            height: 7px;
            background: #25293a;
            border-radius: 4px;
            overflow: hidden;
        }
        .progress-bar-fill {
            height: 100%;
            background: linear-gradient(90deg, #ff4d88, #ff80ab);
            width: 0%;
            transition: width 0.4s ease;
        }
        .char-tabs {
            display: flex;
            gap: 6px;
            overflow-x: auto;
            padding-bottom: 4px;
            scrollbar-width: none;
        }
        .char-tabs::-webkit-scrollbar { display: none; }
        .tab-btn {
            background: var(--card-bg);
            border: 1px solid var(--border);
            color: var(--text-sub);
            padding: 6px 12px;
            border-radius: 20px;
            font-size: 12px;
            font-weight: 600;
            white-space: nowrap;
            cursor: pointer;
            transition: all 0.2s;
        }
        .tab-btn.active {
            background: var(--primary);
            color: #fff;
            border-color: var(--primary);
            box-shadow: 0 0 10px var(--primary-glow);
        }
        .grid-container {
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 10px;
            padding: 12px;
        }
        @media (min-width: 768px) {
            .grid-container { grid-template-columns: repeat(4, 1fr); gap: 14px; padding: 16px; }
        }
        .card {
            background: var(--card-bg);
            border-radius: 12px;
            overflow: hidden;
            border: 1px solid var(--border);
            display: flex;
            flex-direction: column;
            cursor: pointer;
            transition: transform 0.15s ease;
        }
        .card:active { transform: scale(0.97); }
        .card-img-wrap {
            position: relative;
            width: 100%;
            padding-top: 140%;
            background: #141721;
        }
        .card-img {
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            object-fit: cover;
        }
        .card-info {
            padding: 8px 10px;
        }
        .card-title {
            font-size: 13px;
            font-weight: 700;
            color: #fff;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }
        .card-meta {
            display: flex;
            justify-content: space-between;
            align-items: center;
            font-size: 11px;
            color: var(--text-sub);
            margin-top: 3px;
        }
        .tag-char {
            background: rgba(255, 77, 136, 0.15);
            color: #ff80ab;
            padding: 1px 5px;
            border-radius: 4px;
            font-weight: 600;
        }
        /* Modal Viewer */
        .modal {
            display: none;
            position: fixed;
            top: 0; left: 0; right: 0; bottom: 0;
            background: rgba(0, 0, 0, 0.95);
            z-index: 1000;
            flex-direction: column;
            justify-content: center;
            align-items: center;
            backdrop-filter: blur(8px);
        }
        .modal.open { display: flex; }
        .modal-img {
            max-width: 96%;
            max-height: 80vh;
            border-radius: 8px;
            object-fit: contain;
            box-shadow: 0 10px 30px rgba(0,0,0,0.8);
        }
        .modal-info {
            color: #fff;
            margin-top: 12px;
            text-align: center;
            font-size: 14px;
        }
        .modal-close {
            position: absolute;
            top: 20px;
            right: 20px;
            background: rgba(255,255,255,0.2);
            color: #fff;
            border: none;
            width: 36px;
            height: 36px;
            border-radius: 50%;
            font-size: 18px;
            cursor: pointer;
        }
        .toast {
            position: fixed;
            bottom: 20px;
            left: 50%;
            transform: translateX(-50%);
            background: rgba(255, 77, 136, 0.9);
            color: #fff;
            padding: 8px 16px;
            border-radius: 20px;
            font-size: 12px;
            font-weight: bold;
            opacity: 0;
            transition: opacity 0.3s;
            pointer-events: none;
            z-index: 2000;
        }
        .toast.show { opacity: 1; }
    </style>
</head>
<body>
    <header>
        <div class="header-top">
            <div class="header-title">
                🌸 __ROSTER__ 실시간 갤러리
                <span class="live-badge">LIVE</span>
            </div>
            <div style="font-size: 11px; color: var(--text-sub);" id="last-update">대기 중...</div>
        </div>
        
        <div class="progress-box">
            <div class="progress-label">
                <span id="progress-text">생성 진행도: 계산 중...</span>
                <span id="progress-percent" style="font-weight: 700; color: #ff80ab;">0%</span>
            </div>
            <div class="progress-bar-bg">
                <div class="progress-bar-fill" id="progress-fill"></div>
            </div>
        </div>

        <div class="char-tabs" id="char-tabs">
            __TABS__
        </div>
    </header>

    <main class="grid-container" id="grid"></main>

    <!-- Fullscreen Modal -->
    <div class="modal" id="modal" onclick="closeModal()">
        <button class="modal-close" onclick="closeModal()">✕</button>
        <img class="modal-img" id="modal-img" src="" alt="확대">
        <div class="modal-info" id="modal-info"></div>
    </div>

    <div class="toast" id="toast">새로운 이미지가 생성되었습니다!</div>

    <script>
        let currentChar = "all";
        let lastCount = 0;
        let isFirstLoad = true;

        async function fetchImages() {
            try {
                const res = await fetch(`/api/status?char=${currentChar}&t=${Date.now()}`);
                const data = await res.json();
                
                // Update Progress
                document.getElementById('progress-text').innerText = `생성 완료: ${data.total_count} / ${data.target}장`;
                document.getElementById('progress-percent').innerText = `${data.progress_pct}%`;
                document.getElementById('progress-fill').style.width = `${Math.min(data.progress_pct, 100)}%`;
                document.getElementById('last-update').innerText = new Date().toLocaleTimeString();

                // Update Tab counts dynamically
                const tabContainer = document.getElementById('char-tabs');
                const counts = data.char_counts || {};
                const names = data.char_names || {};
                const codes = Object.keys(counts);
                if (tabContainer) {
                    const existing = {};
                    tabContainer.querySelectorAll('.tab-btn[data-char]').forEach(btn => {
                        existing[btn.getAttribute('data-char')] = btn;
                    });
                    if (existing['all']) {
                        existing['all'].innerText = `전체 (${data.total_count})`;
                    }
                    codes.forEach(code => {
                        const label = names[code] || code.toUpperCase();
                        const count = counts[code] || 0;
                        let btn = existing[code];
                        if (!btn) {
                            btn = document.createElement('button');
                            btn.className = 'tab-btn';
                            btn.setAttribute('data-char', code);
                            if (currentChar === code) btn.classList.add('active');
                            tabContainer.appendChild(btn);
                        }
                        btn.innerText = `${label} (${count})`;
                    });
                }

                if (data.total_count > lastCount && !isFirstLoad) {
                    showToast(`새 이미지 추가됨! (+${data.total_count - lastCount}장)`);
                }
                lastCount = data.total_count;
                isFirstLoad = false;

                renderGrid(data.images);
            } catch (e) {
                console.error("Fetch error:", e);
            }
        }

        function escapeHtml(val) {
            return String(val ?? '')
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;')
                .replace(/'/g, '&#39;');
        }

        function renderGrid(images) {
            const grid = document.getElementById('grid');
            if (images.length === 0) {
                grid.innerHTML = '<div style="grid-column: 1/-1; text-align: center; color: var(--text-sub); padding: 40px;">생성된 이미지가 아직 없습니다. 생성이 진행되면 자동으로 표시됩니다.</div>';
                return;
            }
            grid.innerHTML = images.map(img => `
                <div class="card" data-url="${escapeHtml(img.url)}" data-title="${escapeHtml(img.display_name + ' - ' + img.char_name)}" onclick="openModal(this.dataset.url, this.dataset.title)">
                    <div class="card-img-wrap">
                        <img class="card-img" src="${escapeHtml(img.url)}" loading="lazy" alt="${escapeHtml(img.display_name)}">
                    </div>
                    <div class="card-info">
                        <div class="card-title">${escapeHtml(img.display_name)}</div>
                        <div class="card-meta">
                            <span class="tag-char">${escapeHtml((img.char || '').toUpperCase())}</span>
                            <span>${escapeHtml(img.mtime_str)}</span>
                        </div>
                    </div>
                </div>
            `).join('');
        }

        function showToast(msg) {
            const toast = document.getElementById('toast');
            toast.innerText = msg;
            toast.classList.add('show');
            setTimeout(() => toast.classList.remove('show'), 2500);
        }

        function openModal(url, title) {
            if (!url || !String(url).startsWith('/asset/')) return;
            document.getElementById('modal-img').src = url;
            document.getElementById('modal-info').innerText = title || '';
            document.getElementById('modal').classList.add('open');
        }

        function closeModal() {
            document.getElementById('modal').classList.remove('open');
        }

        // Tab click
        document.getElementById('char-tabs').addEventListener('click', (e) => {
            if (e.target.classList.contains('tab-btn')) {
                document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
                e.target.classList.add('active');
                currentChar = e.target.getAttribute('data-char');
                fetchImages();
            }
        });

        // Polling every 3.5 seconds
        fetchImages();
        setInterval(fetchImages, 3500);
    </script>
</body>
</html>"""
    return html_doc.replace("__ROSTER__", safe_roster).replace("__TABS__", tabs_markup)

if __name__ == "__main__":
    BENCH_RATATATA_DIR.mkdir(parents=True, exist_ok=True)
    uvicorn.run(app, host="0.0.0.0", port=8080, log_level="warning")
