import os
import glob
import time
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
import uvicorn

app = FastAPI(title="Plepa Realtime Mobile Gallery")

BENCH1_DIR = Path(__file__).resolve().parent.parent / "projects" / "ykn" / "artist_benchmark"
BENCH2_DIR = Path(__file__).resolve().parent.parent / "projects" / "ykn" / "artist_benchmark_v2"
if BENCH1_DIR.exists():
    app.mount("/bench1", StaticFiles(directory=BENCH1_DIR, html=True), name="bench1")
if BENCH2_DIR.exists():
    app.mount("/bench2", StaticFiles(directory=BENCH2_DIR, html=True), name="bench2")

ASSETS_DIR = Path(__file__).resolve().parent.parent / "projects" / "ykn" / "assets"
TOTAL_TARGET = 476

CHAR_NAMES = {
    "hay": "설하율 (4녀)",
    "ser": "설세린 (2녀)",
    "sia": "설시아 (3녀)",
    "yua": "설유아 (1녀)"
}

@app.get("/api/status")
def get_status(char: Optional[str] = None):
    # Scan all webp files excluding _origin
    pattern = str(ASSETS_DIR / "**" / "*.webp")
    all_files = glob.glob(pattern, recursive=True)
    
    items = []
    char_counts = {c: 0 for c in CHAR_NAMES}
    
    for f in all_files:
        if "_origin" in f or "새 폴더" in f or "ckpt_" in f:
            continue
        p = Path(f)
        rel = p.relative_to(ASSETS_DIR)
        parts = rel.parts
        if not parts:
            continue
        c_code = parts[0].lower()
        if c_code in char_counts:
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
            "char_name": CHAR_NAMES.get(c_code, c_code),
            "display_name": display_name,
            "subfolder": parts[1] if len(parts) > 2 else "",
            "url": f"/asset/{rel.as_posix()}",
            "mtime": mtime,
            "mtime_str": time.strftime("%H:%M:%S", time.localtime(mtime))
        })
        
    # Sort newest first
    items.sort(key=lambda x: x["mtime"], reverse=True)
    
    total_count = sum(char_counts.values())
    progress_pct = round((total_count / TOTAL_TARGET) * 100, 1)
    
    return {
        "total_count": total_count,
        "target": TOTAL_TARGET,
        "progress_pct": progress_pct,
        "char_counts": char_counts,
        "images": items
    }

@app.get("/asset/{file_path:path}")
def serve_asset(file_path: str):
    target = ASSETS_DIR / file_path
    if not target.exists():
        return HTMLResponse("File Not Found", status_code=404)
    return FileResponse(target, media_type="image/webp")

@app.get("/", response_class=HTMLResponse)
def index():
    return """<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>플에파 YKN 실시간 모바일 갤러리</title>
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
                🌸 YKN 실시간 갤러리
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
            <button class="tab-btn active" data-char="all">전체 (0)</button>
            <button class="tab-btn" data-char="hay">설하율 (0)</button>
            <button class="tab-btn" data-char="ser">설세린 (0)</button>
            <button class="tab-btn" data-char="sia">설시아 (0)</button>
            <button class="tab-btn" data-char="yua">설유아 (0)</button>
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

                // Update Tab counts
                const tabs = document.querySelectorAll('.tab-btn');
                tabs[0].innerText = `전체 (${data.total_count})`;
                tabs[1].innerText = `설하율 (${data.char_counts.hay || 0})`;
                tabs[2].innerText = `설세린 (${data.char_counts.ser || 0})`;
                tabs[3].innerText = `설시아 (${data.char_counts.sia || 0})`;
                tabs[4].innerText = `설유아 (${data.char_counts.yua || 0})`;

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

        function renderGrid(images) {
            const grid = document.getElementById('grid');
            if (images.length === 0) {
                grid.innerHTML = '<div style="grid-column: 1/-1; text-align: center; color: var(--text-sub); padding: 40px;">생성된 이미지가 아직 없습니다. 생성이 진행되면 자동으로 표시됩니다.</div>';
                return;
            }
            grid.innerHTML = images.map(img => `
                <div class="card" onclick="openModal('${img.url}', '${img.display_name} - ${img.char_name}')">
                    <div class="card-img-wrap">
                        <img class="card-img" src="${img.url}" loading="lazy" alt="${img.display_name}">
                    </div>
                    <div class="card-info">
                        <div class="card-title">${img.display_name}</div>
                        <div class="card-meta">
                            <span class="tag-char">${img.char.toUpperCase()}</span>
                            <span>${img.mtime_str}</span>
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
            document.getElementById('modal-img').src = url;
            document.getElementById('modal-info').innerText = title;
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

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080, log_level="warning")
