"""
plepa_gui.components.retouch_editor
PC 갤러리(/gallery)와 모바일 뷰어(/mobile)에서 공용으로 사용하는 HTML5 캔버스 수동 검열/덧칠 에디터 컴포넌트.
- 초기 로드: 현재 이미지(검열본 또는 원본)를 캔버스에 불러옵니다.
- [🧹 검열 제거(원본 로드)]: 매핑되는 무검열 원본(_origin)을 캔버스 전체에 불러와 기존 자동 검열을 지우고 직접 작업합니다.
- [🖌️ 화이트 덧칠]: 부드러운 화이트 실루엣 방사형 브러시(마우스/터치 드래그 선분 보간 지원).
- [🩹 지우개(원본 복원)]: 브러시 영역만 무검열 원본(_origin) 픽셀(없으면 초기 이미지)로 부분 복원합니다.
- [💾 저장(파일 교체)]: /api/assets/retouch 호출로 본체 에셋 파일을 원자적으로 교체합니다.
"""

from __future__ import annotations

RETOUCH_EDITOR_CSS = """
<style id="plepa-retouch-css">
    .plepa-retouch-modal {
        display: none;
        position: fixed;
        inset: 0;
        z-index: 9999;
        background: rgba(2, 6, 23, 0.96);
        backdrop-filter: blur(10px);
        -webkit-backdrop-filter: blur(10px);
        flex-direction: column;
        overflow: hidden;
        user-select: none;
        -webkit-user-select: none;
    }
    .plepa-retouch-modal.active {
        display: flex;
    }
    .plepa-retouch-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        gap: 10px;
        padding: 10px 16px;
        padding-top: max(10px, env(safe-area-inset-top));
        background: #0f172a;
        border-bottom: 1px solid #334155;
        color: #f8fafc;
        flex-shrink: 0;
    }
    .plepa-retouch-title-wrap {
        display: flex;
        flex-direction: column;
        min-width: 0;
    }
    .plepa-retouch-title {
        font-size: 14px;
        font-weight: 700;
        color: #f8fafc;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
    }
    .plepa-retouch-sub {
        font-size: 11px;
        color: #94a3b8;
    }
    .plepa-retouch-close {
        background: #334155;
        color: #f8fafc;
        border: 1px solid #475569;
        border-radius: 8px;
        padding: 6px 12px;
        font-size: 12px;
        font-weight: 600;
        cursor: pointer;
        flex-shrink: 0;
    }
    .plepa-retouch-stage {
        flex: 1;
        display: flex;
        align-items: center;
        justify-content: center;
        overflow: hidden;
        padding: 12px;
        position: relative;
        touch-action: none;
    }
    #plepaEditorCanvas {
        max-width: 100%;
        max-height: 100%;
        width: auto;
        height: auto;
        object-fit: contain;
        border-radius: 8px;
        box-shadow: 0 20px 50px rgba(0, 0, 0, 0.85);
        cursor: crosshair;
        touch-action: none;
        background: #0b1120;
    }
    .plepa-retouch-toolbar {
        display: flex;
        flex-wrap: wrap;
        align-items: center;
        justify-content: center;
        gap: 8px;
        padding: 10px 14px;
        padding-bottom: max(12px, env(safe-area-inset-bottom));
        background: #0f172a;
        border-top: 1px solid #334155;
        flex-shrink: 0;
    }
    .plepa-retouch-group {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        flex-wrap: wrap;
    }
    .plepa-tool-btn {
        background: #1e293b;
        color: #e2e8f0;
        border: 1px solid #475569;
        border-radius: 8px;
        padding: 7px 11px;
        font-size: 12px;
        font-weight: 600;
        cursor: pointer;
        transition: all 0.12s ease;
        white-space: nowrap;
    }
    .plepa-tool-btn:hover:not(:disabled) {
        background: #334155;
    }
    .plepa-tool-btn:disabled {
        opacity: 0.42;
        cursor: not-allowed;
    }
    .plepa-tool-btn.active {
        background: #2563eb;
        border-color: #60a5fa;
        color: #ffffff;
        box-shadow: 0 0 10px rgba(37, 99, 235, 0.55);
    }
    .plepa-tool-btn.warn {
        background: rgba(217, 119, 6, 0.22);
        border-color: rgba(251, 191, 36, 0.65);
        color: #fde68a;
    }
    .plepa-tool-btn.warn:hover:not(:disabled) {
        background: rgba(217, 119, 6, 0.38);
    }
    .plepa-save-btn {
        background: #10b981;
        color: #022c22;
        border: 1px solid #34d399;
        border-radius: 8px;
        padding: 8px 16px;
        font-size: 13px;
        font-weight: 800;
        cursor: pointer;
        white-space: nowrap;
    }
    .plepa-save-btn:hover:not(:disabled) {
        background: #34d399;
    }
    .plepa-save-btn:disabled {
        opacity: 0.6;
        cursor: wait;
    }
</style>
"""

RETOUCH_EDITOR_HTML = """
<div id="plepaRetouchModal" class="plepa-retouch-modal" aria-hidden="true">
    <div class="plepa-retouch-header">
        <div class="plepa-retouch-title-wrap">
            <div class="plepa-retouch-title" id="plepaRetouchTitle">✏️ 수동 검열 에디터</div>
            <div class="plepa-retouch-sub" id="plepaRetouchSubtitle">저장 시 현재 에셋 파일이 즉시 교체됩니다 (_origin 원본 보존)</div>
        </div>
        <button type="button" class="plepa-retouch-close" onclick="closeRetouchEditor()">닫기 ✕</button>
    </div>
    <div class="plepa-retouch-stage">
        <canvas id="plepaEditorCanvas"></canvas>
    </div>
    <div class="plepa-retouch-toolbar">
        <div class="plepa-retouch-group">
            <button type="button" class="plepa-tool-btn warn" id="plepaBtnLoadOrigin" onclick="loadOriginToCanvas()" title="무검열 원본(_origin)으로 캔버스를 초기화해 기존 자동 검열을 제거합니다">
                🧹 검열 제거(원본 로드)
            </button>
            <button type="button" class="plepa-tool-btn active" id="plepaBtnBrush" onclick="setRetouchTool('brush')">
                🖌️ 화이트 덧칠
            </button>
            <button type="button" class="plepa-tool-btn" id="plepaBtnEraser" onclick="setRetouchTool('eraser')" title="드래그한 영역만 무검열 원본 픽셀로 지워 복원합니다">
                🩹 지우개(원본 복원)
            </button>
            <button type="button" class="plepa-tool-btn" onclick="undoRetouchStroke()">
                ↩️ 취소
            </button>
            <button type="button" class="plepa-tool-btn" onclick="resetRetouchCanvas()" title="에디터를 열었을 때의 초기 이미지로 되돌립니다">
                🔄 리셋
            </button>
        </div>
        <div class="plepa-retouch-group">
            <span style="font-size:12px;color:#94a3b8;">크기:</span>
            <input type="range" id="plepaBrushSize" min="6" max="80" value="28" style="width:92px;" oninput="updateRetouchBrushSize(this.value)" />
            <span id="plepaBrushSizeVal" style="font-size:12px;color:#38bdf8;font-weight:700;min-width:24px;text-align:right;">28</span>
        </div>
        <button type="button" class="plepa-save-btn" id="plepaBtnRetouchSave" onclick="saveRetouchEdit()">
            💾 저장 (파일 교체)
        </button>
    </div>
</div>
"""


def build_retouch_editor_script(
    on_saved_js: str = "",
    on_notify_js: str = "console.log(msg);",
) -> str:
    """PC 갤러리 및 모바일 뷰어에서 공용으로 삽입할 수동 검열 캔버스 JS 블록을 생성합니다."""
    return f"""
<script id="plepa-retouch-script">
(function() {{
    let retouchState = {{
        isOpen: false,
        relPath: '',
        roster: '',
        imageUrl: '',
        originUrl: '',
        initialImgObj: null,
        originImgObj: null,
        originReady: false,
        canvas: null,
        ctx: null,
        isDrawing: false,
        lastPos: null,
        tool: 'brush',
        brushRadius: 28,
        undoStack: [],
        saving: false
    }};

    function notifyRetouch(msg, isError) {{
        try {{
            {on_notify_js}
        }} catch (e) {{
            console.log(msg);
        }}
    }}

    function buildAuthHeaders(extra) {{
        const headers = Object.assign({{}}, extra || {{}});
        const tok = new URLSearchParams(window.location.search).get('token');
        if (tok) headers['X-Plepa-Token'] = tok;
        return headers;
    }}

    function cacheBustUrl(url) {{
        if (!url) return '';
        const base = url.split('?')[0];
        return base + '?t=' + Date.now();
    }}

    function pushUndoState() {{
        if (!retouchState.ctx || !retouchState.canvas) return;
        if (retouchState.undoStack.length >= 20) {{
            retouchState.undoStack.shift();
        }}
        retouchState.undoStack.push(
            retouchState.ctx.getImageData(0, 0, retouchState.canvas.width, retouchState.canvas.height)
        );
    }}

    function getEraserSource() {{
        if (retouchState.originReady && retouchState.originImgObj) {{
            return retouchState.originImgObj;
        }}
        return retouchState.initialImgObj;
    }}

    function drawCircleAt(x, y) {{
        const ctx = retouchState.ctx;
        const r = retouchState.brushRadius;
        if (!ctx) return;

        ctx.save();
        if (retouchState.tool === 'brush') {{
            const grad = ctx.createRadialGradient(x, y, r * 0.4, x, y, r);
            grad.addColorStop(0, 'rgba(255, 255, 255, 1.0)');
            grad.addColorStop(0.85, 'rgba(255, 255, 255, 0.96)');
            grad.addColorStop(1, 'rgba(255, 255, 255, 0.0)');
            ctx.fillStyle = grad;
            ctx.beginPath();
            ctx.arc(x, y, r, 0, Math.PI * 2);
            ctx.fill();
        }} else {{
            const srcImg = getEraserSource();
            if (srcImg && retouchState.canvas) {{
                ctx.beginPath();
                ctx.arc(x, y, r, 0, Math.PI * 2);
                ctx.clip();
                ctx.drawImage(srcImg, 0, 0, retouchState.canvas.width, retouchState.canvas.height);
            }}
        }}
        ctx.restore();
    }}

    function drawSegment(p1, p2) {{
        if (!p1) {{
            drawCircleAt(p2.x, p2.y);
            return;
        }}
        const dx = p2.x - p1.x;
        const dy = p2.y - p1.y;
        const dist = Math.hypot(dx, dy);
        const step = Math.max(2, retouchState.brushRadius * 0.22);
        const steps = Math.max(1, Math.ceil(dist / step));
        for (let i = 1; i <= steps; i++) {{
            const t = i / steps;
            drawCircleAt(p1.x + dx * t, p1.y + dy * t);
        }}
    }}

    function getCanvasCoords(e) {{
        const cv = retouchState.canvas;
        const rect = cv.getBoundingClientRect();
        const scaleX = cv.width / rect.width;
        const scaleY = cv.height / rect.height;
        let clientX = e.clientX;
        let clientY = e.clientY;
        if (e.touches && e.touches.length > 0) {{
            clientX = e.touches[0].clientX;
            clientY = e.touches[0].clientY;
        }}
        return {{
            x: (clientX - rect.left) * scaleX,
            y: (clientY - rect.top) * scaleY
        }};
    }}

    function ensureCanvasListeners() {{
        const cv = document.getElementById('plepaEditorCanvas');
        if (!cv || cv.dataset.plepaBound === '1') return;
        cv.dataset.plepaBound = '1';

        const onStart = function(e) {{
            if (!retouchState.isOpen) return;
            e.preventDefault();
            retouchState.isDrawing = true;
            const pos = getCanvasCoords(e);
            retouchState.lastPos = pos;
            drawCircleAt(pos.x, pos.y);
        }};
        const onMove = function(e) {{
            if (!retouchState.isOpen || !retouchState.isDrawing) return;
            e.preventDefault();
            const pos = getCanvasCoords(e);
            drawSegment(retouchState.lastPos, pos);
            retouchState.lastPos = pos;
        }};
        const onEnd = function() {{
            if (retouchState.isDrawing) {{
                retouchState.isDrawing = false;
                retouchState.lastPos = null;
                pushUndoState();
            }}
        }};

        cv.addEventListener('mousedown', onStart);
        cv.addEventListener('mousemove', onMove);
        window.addEventListener('mouseup', onEnd);
        cv.addEventListener('touchstart', onStart, {{ passive: false }});
        cv.addEventListener('touchmove', onMove, {{ passive: false }});
        window.addEventListener('touchend', onEnd);

        window.addEventListener('keydown', function(e) {{
            if (!retouchState.isOpen) return;
            if (e.key === 'Escape') {{
                e.stopImmediatePropagation();
                e.preventDefault();
                window.closeRetouchEditor();
            }} else if (e.key === 'ArrowLeft' || e.key === 'ArrowRight' || e.key === ' ') {{
                e.stopImmediatePropagation();
            }} else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'z') {{
                e.stopImmediatePropagation();
                e.preventDefault();
                window.undoRetouchStroke();
            }}
        }}, true);
    }}

    window.setRetouchTool = function(tool) {{
        retouchState.tool = tool;
        const bBrush = document.getElementById('plepaBtnBrush');
        const bEraser = document.getElementById('plepaBtnEraser');
        if (bBrush) bBrush.classList.toggle('active', tool === 'brush');
        if (bEraser) bEraser.classList.toggle('active', tool === 'eraser');
    }};

    window.updateRetouchBrushSize = function(val) {{
        retouchState.brushRadius = parseInt(val, 10) || 28;
        const el = document.getElementById('plepaBrushSizeVal');
        if (el) el.textContent = String(retouchState.brushRadius);
    }};

    window.undoRetouchStroke = function() {{
        if (retouchState.undoStack.length > 1) {{
            retouchState.undoStack.pop();
            const prev = retouchState.undoStack[retouchState.undoStack.length - 1];
            retouchState.ctx.putImageData(prev, 0, 0);
        }}
    }};

    window.resetRetouchCanvas = function() {{
        if (retouchState.initialImgObj && retouchState.ctx && retouchState.canvas) {{
            retouchState.ctx.drawImage(
                retouchState.initialImgObj, 0, 0, retouchState.canvas.width, retouchState.canvas.height
            );
            pushUndoState();
        }}
    }};

    window.loadOriginToCanvas = function() {{
        if (!retouchState.originReady || !retouchState.originImgObj) {{
            notifyRetouch('무검열 원본(_origin) 이미지를 찾을 수 없습니다.', true);
            return;
        }}
        if (retouchState.ctx && retouchState.canvas) {{
            retouchState.ctx.drawImage(
                retouchState.originImgObj, 0, 0, retouchState.canvas.width, retouchState.canvas.height
            );
            pushUndoState();
            notifyRetouch('🧹 기존 검열을 제거하고 무검열 원본을 캔버스에 불러왔습니다.', false);
        }}
    }};

    window.closeRetouchEditor = function() {{
        const modal = document.getElementById('plepaRetouchModal');
        if (modal) {{
            modal.classList.remove('active');
            modal.setAttribute('aria-hidden', 'true');
        }}
        retouchState.isOpen = false;
        window.__plepaRetouchOpen = false;
        retouchState.isDrawing = false;
        retouchState.lastPos = null;
    }};

    window.openRetouchEditor = function(opts) {{
        ensureCanvasListeners();
        const modal = document.getElementById('plepaRetouchModal');
        const cv = document.getElementById('plepaEditorCanvas');
        if (!modal || !cv) return;

        retouchState.relPath = (opts && opts.relPath) || '';
        retouchState.roster = (opts && opts.roster) || '';
        retouchState.imageUrl = (opts && opts.imageUrl) || '';
        retouchState.originUrl = (opts && opts.originUrl) || '';
        retouchState.originReady = false;
        retouchState.originImgObj = null;
        retouchState.undoStack = [];
        retouchState.canvas = cv;
        retouchState.ctx = cv.getContext('2d');
        retouchState.isOpen = true;
        window.__plepaRetouchOpen = true;
        window.setRetouchTool('brush');

        const titleEl = document.getElementById('plepaRetouchTitle');
        if (titleEl) titleEl.textContent = (opts && opts.title) || '✏️ 수동 검열 에디터';

        const loadOriginBtn = document.getElementById('plepaBtnLoadOrigin');
        const subEl = document.getElementById('plepaRetouchSubtitle');
        if (loadOriginBtn) loadOriginBtn.disabled = true;
        if (subEl) {{
            subEl.textContent = retouchState.originUrl
                ? '무검열 원본(_origin) 연동됨 · 검열 제거 후 덧칠하거나 저장 시 파일이 즉시 교체됩니다'
                : '원본 백업(_origin) 없음 · 지우개는 초기 이미지 기준으로 동작합니다';
        }}

        const initImg = new Image();
        initImg.crossOrigin = 'anonymous';
        initImg.onload = function() {{
            retouchState.initialImgObj = initImg;
            cv.width = initImg.naturalWidth || 832;
            cv.height = initImg.naturalHeight || 1216;
            retouchState.ctx.drawImage(initImg, 0, 0, cv.width, cv.height);
            pushUndoState();
        }};
        initImg.src = cacheBustUrl(retouchState.imageUrl);

        if (retouchState.originUrl) {{
            const origImg = new Image();
            origImg.crossOrigin = 'anonymous';
            origImg.onload = function() {{
                retouchState.originImgObj = origImg;
                retouchState.originReady = true;
                if (loadOriginBtn) loadOriginBtn.disabled = false;
            }};
            origImg.src = cacheBustUrl(retouchState.originUrl);
        }}

        modal.classList.add('active');
        modal.setAttribute('aria-hidden', 'false');
    }};

    window.saveRetouchEdit = async function() {{
        if (retouchState.saving || !retouchState.canvas || !retouchState.relPath) return;
        const saveBtn = document.getElementById('plepaBtnRetouchSave');
        retouchState.saving = true;
        if (saveBtn) {{
            saveBtn.disabled = true;
            saveBtn.textContent = '⏳ 파일 교체 중...';
        }}

        try {{
            const dataUrl = retouchState.canvas.toDataURL('image/webp', 0.95);
            const resp = await fetch('/api/assets/retouch', {{
                method: 'POST',
                headers: buildAuthHeaders({{ 'Content-Type': 'application/json' }}),
                body: JSON.stringify({{
                    rel_path: retouchState.relPath,
                    image_base64: dataUrl,
                    roster: retouchState.roster || null
                }})
            }});
            const data = await resp.json();
            if (!resp.ok || !data.success) {{
                throw new Error(data.detail || data.error || '저장에 실패했습니다.');
            }}

            const ts = data.timestamp || Date.now();
            const cleanBaseUrl = (retouchState.imageUrl || '').split('?')[0];
            if (cleanBaseUrl) {{
                document.querySelectorAll('img').forEach(function(img) {{
                    const curSrc = (img.getAttribute('src') || '').split('?')[0];
                    if (curSrc === cleanBaseUrl || curSrc.endsWith('/' + retouchState.relPath)) {{
                        img.src = cleanBaseUrl + '?t=' + ts;
                    }}
                }});
            }}

            const savedPayload = {{
                rel_path: retouchState.relPath,
                timestamp: ts,
                filename: data.filename || ''
            }};
            {on_saved_js}
            notifyRetouch('✅ 수동 검열 저장 및 파일 교체 완료!', false);
            window.closeRetouchEditor();
        }} catch (err) {{
            notifyRetouch('❌ 저장 실패: ' + (err && err.message ? err.message : err), true);
        }} finally {{
            retouchState.saving = false;
            if (saveBtn) {{
                saveBtn.disabled = false;
                saveBtn.textContent = '💾 저장 (파일 교체)';
            }}
        }}
    }};
}})();
</script>
"""
