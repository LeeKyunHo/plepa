(function() {
    let retouchState = {
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
    };

    function notifyRetouch(msg, isError) {
        try {
            __ON_NOTIFY_JS__
        } catch (e) {
            console.log(msg);
        }
    }

    function buildAuthHeaders(extra) {
        const headers = Object.assign({}, extra || {});
        const tok = new URLSearchParams(window.location.search).get('token');
        if (tok) headers['X-Plepa-Token'] = tok;
        return headers;
    }

    function cacheBustUrl(url) {
        if (!url) return '';
        const base = url.split('?')[0];
        return base + '?t=' + Date.now();
    }

    function pushUndoState() {
        if (!retouchState.ctx || !retouchState.canvas) return;
        if (retouchState.undoStack.length >= 20) {
            retouchState.undoStack.shift();
        }
        retouchState.undoStack.push(
            retouchState.ctx.getImageData(0, 0, retouchState.canvas.width, retouchState.canvas.height)
        );
    }

    function getEraserSource() {
        if (retouchState.originReady && retouchState.originImgObj) {
            return retouchState.originImgObj;
        }
        return retouchState.initialImgObj;
    }

    function drawCircleAt(x, y) {
        const ctx = retouchState.ctx;
        const r = retouchState.brushRadius;
        if (!ctx) return;

        ctx.save();
        if (retouchState.tool === 'brush') {
            const grad = ctx.createRadialGradient(x, y, r * 0.4, x, y, r);
            grad.addColorStop(0, 'rgba(255, 255, 255, 1.0)');
            grad.addColorStop(0.85, 'rgba(255, 255, 255, 0.96)');
            grad.addColorStop(1, 'rgba(255, 255, 255, 0.0)');
            ctx.fillStyle = grad;
            ctx.beginPath();
            ctx.arc(x, y, r, 0, Math.PI * 2);
            ctx.fill();
        } else {
            const srcImg = getEraserSource();
            if (srcImg && retouchState.canvas) {
                ctx.beginPath();
                ctx.arc(x, y, r, 0, Math.PI * 2);
                ctx.clip();
                ctx.drawImage(srcImg, 0, 0, retouchState.canvas.width, retouchState.canvas.height);
            }
        }
        ctx.restore();
    }

    function drawSegment(p1, p2) {
        if (!p1) {
            drawCircleAt(p2.x, p2.y);
            return;
        }
        const dx = p2.x - p1.x;
        const dy = p2.y - p1.y;
        const dist = Math.hypot(dx, dy);
        const step = Math.max(2, retouchState.brushRadius * 0.22);
        const steps = Math.max(1, Math.ceil(dist / step));
        for (let i = 1; i <= steps; i++) {
            const t = i / steps;
            drawCircleAt(p1.x + dx * t, p1.y + dy * t);
        }
    }

    function getCanvasCoords(e) {
        const cv = retouchState.canvas;
        const rect = cv.getBoundingClientRect();
        const scaleX = cv.width / rect.width;
        const scaleY = cv.height / rect.height;
        let clientX = e.clientX;
        let clientY = e.clientY;
        if (e.touches && e.touches.length > 0) {
            clientX = e.touches[0].clientX;
            clientY = e.touches[0].clientY;
        }
        return {
            x: (clientX - rect.left) * scaleX,
            y: (clientY - rect.top) * scaleY
        };
    }

    function ensureCanvasListeners() {
        const cv = document.getElementById('plepaEditorCanvas');
        if (!cv || cv.dataset.plepaBound === '1') return;
        cv.dataset.plepaBound = '1';

        const onStart = function(e) {
            if (!retouchState.isOpen) return;
            e.preventDefault();
            retouchState.isDrawing = true;
            const pos = getCanvasCoords(e);
            retouchState.lastPos = pos;
            drawCircleAt(pos.x, pos.y);
        };
        const onMove = function(e) {
            if (!retouchState.isOpen || !retouchState.isDrawing) return;
            e.preventDefault();
            const pos = getCanvasCoords(e);
            drawSegment(retouchState.lastPos, pos);
            retouchState.lastPos = pos;
        };
        const onEnd = function() {
            if (retouchState.isDrawing) {
                retouchState.isDrawing = false;
                retouchState.lastPos = null;
                pushUndoState();
            }
        };

        cv.addEventListener('mousedown', onStart);
        cv.addEventListener('mousemove', onMove);
        window.addEventListener('mouseup', onEnd);
        cv.addEventListener('touchstart', onStart, { passive: false });
        cv.addEventListener('touchmove', onMove, { passive: false });
        window.addEventListener('touchend', onEnd);

        window.addEventListener('keydown', function(e) {
            if (!retouchState.isOpen) return;
            if (e.key === 'Escape') {
                e.stopImmediatePropagation();
                e.preventDefault();
                window.closeRetouchEditor();
            } else if (e.key === 'ArrowLeft' || e.key === 'ArrowRight' || e.key === ' ') {
                e.stopImmediatePropagation();
            } else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'z') {
                e.stopImmediatePropagation();
                e.preventDefault();
                window.undoRetouchStroke();
            }
        }, true);
    }

    window.setRetouchTool = function(tool) {
        retouchState.tool = tool;
        const bBrush = document.getElementById('plepaBtnBrush');
        const bEraser = document.getElementById('plepaBtnEraser');
        if (bBrush) bBrush.classList.toggle('active', tool === 'brush');
        if (bEraser) bEraser.classList.toggle('active', tool === 'eraser');
    };

    window.updateRetouchBrushSize = function(val) {
        retouchState.brushRadius = parseInt(val, 10) || 28;
        const el = document.getElementById('plepaBrushSizeVal');
        if (el) el.textContent = String(retouchState.brushRadius);
    };

    window.undoRetouchStroke = function() {
        if (retouchState.undoStack.length > 1) {
            retouchState.undoStack.pop();
            const prev = retouchState.undoStack[retouchState.undoStack.length - 1];
            retouchState.ctx.putImageData(prev, 0, 0);
        }
    };

    window.resetRetouchCanvas = function() {
        if (retouchState.initialImgObj && retouchState.ctx && retouchState.canvas) {
            retouchState.ctx.drawImage(
                retouchState.initialImgObj, 0, 0, retouchState.canvas.width, retouchState.canvas.height
            );
            pushUndoState();
        }
    };

    window.loadOriginToCanvas = function() {
        if (!retouchState.originReady || !retouchState.originImgObj) {
            notifyRetouch('무검열 원본(_origin) 이미지를 찾을 수 없습니다.', true);
            return;
        }
        if (retouchState.ctx && retouchState.canvas) {
            retouchState.ctx.drawImage(
                retouchState.originImgObj, 0, 0, retouchState.canvas.width, retouchState.canvas.height
            );
            pushUndoState();
            notifyRetouch('🧹 기존 검열을 제거하고 무검열 원본을 캔버스에 불러왔습니다.', false);
        }
    };

    window.closeRetouchEditor = function() {
        const modal = document.getElementById('plepaRetouchModal');
        if (modal) {
            modal.classList.remove('active');
            modal.setAttribute('aria-hidden', 'true');
        }
        retouchState.isOpen = false;
        window.__plepaRetouchOpen = false;
        retouchState.isDrawing = false;
        retouchState.lastPos = null;
    };

    window.openRetouchEditor = function(opts) {
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
        if (subEl) {
            subEl.textContent = retouchState.originUrl
                ? '무검열 원본(_origin) 연동됨 · 검열 제거 후 덧칠하거나 저장 시 파일이 즉시 교체됩니다'
                : '원본 백업(_origin) 없음 · 지우개는 초기 이미지 기준으로 동작합니다';
        }

        const initImg = new Image();
        initImg.crossOrigin = 'anonymous';
        initImg.onload = function() {
            retouchState.initialImgObj = initImg;
            cv.width = initImg.naturalWidth || 832;
            cv.height = initImg.naturalHeight || 1216;
            retouchState.ctx.drawImage(initImg, 0, 0, cv.width, cv.height);
            pushUndoState();
        };
        initImg.src = cacheBustUrl(retouchState.imageUrl);

        if (retouchState.originUrl) {
            const origImg = new Image();
            origImg.crossOrigin = 'anonymous';
            origImg.onload = function() {
                retouchState.originImgObj = origImg;
                retouchState.originReady = true;
                if (loadOriginBtn) loadOriginBtn.disabled = false;
            };
            origImg.src = cacheBustUrl(retouchState.originUrl);
        }

        modal.classList.add('active');
        modal.setAttribute('aria-hidden', 'false');
    };

    window.saveRetouchEdit = async function() {
        if (retouchState.saving || !retouchState.canvas || !retouchState.relPath) return;
        const saveBtn = document.getElementById('plepaBtnRetouchSave');
        retouchState.saving = true;
        if (saveBtn) {
            saveBtn.disabled = true;
            saveBtn.textContent = '⏳ 파일 교체 중...';
        }

        try {
            const dataUrl = retouchState.canvas.toDataURL('image/webp', 0.95);
            const resp = await fetch('/api/assets/retouch', {
                method: 'POST',
                headers: buildAuthHeaders({ 'Content-Type': 'application/json' }),
                body: JSON.stringify({
                    rel_path: retouchState.relPath,
                    image_base64: dataUrl,
                    roster: retouchState.roster || null
                })
            });
            const data = await resp.json();
            if (!resp.ok || !data.success) {
                throw new Error(data.detail || data.error || '저장에 실패했습니다.');
            }

            const ts = data.timestamp || Date.now();
            const cleanBaseUrl = (retouchState.imageUrl || '').split('?')[0];
            let decodedBase = cleanBaseUrl;
            try { decodedBase = decodeURIComponent(cleanBaseUrl); } catch (e) {}
            if (cleanBaseUrl) {
                document.querySelectorAll('img').forEach(function(img) {
                    const rawAttr = (img.getAttribute('src') || img.currentSrc || '').split('?')[0];
                    if (!rawAttr) return;
                    let decodedCur = rawAttr;
                    try { decodedCur = decodeURIComponent(rawAttr); } catch (e) {}
                    if (
                        rawAttr === cleanBaseUrl
                        || decodedCur === decodedBase
                        || decodedCur.endsWith('/' + retouchState.relPath)
                    ) {
                        img.src = rawAttr + '?t=' + ts;
                    }
                });
            }

            const savedPayload = {
                rel_path: retouchState.relPath,
                timestamp: ts,
                filename: data.filename || ''
            };
            __ON_SAVED_JS__
            notifyRetouch('✅ 수동 검열 저장 및 파일 교체 완료!', false);
            window.closeRetouchEditor();
        } catch (err) {
            notifyRetouch('❌ 저장 실패: ' + (err && err.message ? err.message : err), true);
        } finally {
            retouchState.saving = false;
            if (saveBtn) {
                saveBtn.disabled = false;
                saveBtn.textContent = '💾 저장 (파일 교체)';
            }
        }
    };
})();
