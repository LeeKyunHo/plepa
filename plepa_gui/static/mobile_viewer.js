        const MOBILE_CHUNK_SIZE = 18;
        const MAX_CONCURRENT_IMG = 3;

        let rawData = __DATA_JSON__;
        let currentMode = '__INITIAL_MODE__'; // 'all', 'recent', 'new', 'qc'
        let currentChar = 'all';
        let currentSort = 'code_asc'; // 'code_asc' or 'mtime_desc'
        let currentView = 'slide'; // 'slide' or 'grid'
        let filteredItems = [];
        let currentIndex = 0;
        let lastDeletedBundle = null;
        let toastTimeout = null;
        let immersiveMode = false;

        let renderSeq = 0;
        let slideLoadSeq = 0;
        let gridObserver = null;
        let imgLoadQueue = [];
        let activeImgLoads = 0;
        let isPollingJob = false;
        let isRefreshingGallery = false;
        let lastCompletedSig = '';
        let jobPollInitialized = false;

        function escapeHtml(str) {
            return String(str ?? '')
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;');
        }

        function formatCharSubtitle(item) {
            const cid = String(item.char || '');
            let shortNm = String(item.char_short_name || '').trim();
            if (!shortNm) {
                const fullNm = String(item.char_name || cid).trim();
                const suffix = ' (' + cid + ')';
                shortNm = (cid && fullNm.endsWith(suffix))
                    ? fullNm.slice(0, -suffix.length).trim()
                    : fullNm;
            }
            if (!cid || shortNm === cid) return shortNm || cid;
            return shortNm + ' (' + cid + ')';
        }

        function showToast(msg, canUndo = false) {
            const el = document.getElementById('toastBanner');
            document.getElementById('toastMsg').innerText = msg;
            const undoBtn = document.getElementById('toastUndoBtn');
            undoBtn.style.display = canUndo ? 'inline-block' : 'none';
            el.classList.add('show');
            if (toastTimeout) clearTimeout(toastTimeout);
            toastTimeout = setTimeout(() => {
                el.classList.remove('show');
            }, 5000);
        }

        function toggleSettingsSheet() {
            const open = !document.getElementById('settingsSheet').classList.contains('open');
            document.getElementById('settingsBackdrop').classList.toggle('open', open);
            document.getElementById('settingsSheet').classList.toggle('open', open);
            if (open) pollJobStatus();
        }

        function closeSettingsSheet() {
            document.getElementById('settingsBackdrop').classList.remove('open');
            document.getElementById('settingsSheet').classList.remove('open');
        }

        function updateModeCounts() {
            const items = rawData.items || [];
            const recentCnt = items.filter(i => i.is_recent).length;
            const qcCnt = items.filter(i => i.qc_passed === false).length;
            const recEl = document.getElementById('recentCountText');
            const qcEl = document.getElementById('qcCountText');
            const qcBtn = document.getElementById('chipQc');
            if (recEl) recEl.innerText = recentCnt;
            if (qcEl) qcEl.innerText = qcCnt;
            if (qcBtn) qcBtn.classList.toggle('has-warn', qcCnt > 0);
            const missEl = document.getElementById('missingCountBadge');
            if (missEl) missEl.innerText = rawData.total_missing || 0;
        }

        function renderRosterSelect() {
            const sel = document.getElementById('rosterSelect');
            if (!sel) return;
            const list = (rawData.rosters && rawData.rosters.length)
                ? rawData.rosters
                : [rawData.roster || 'campus'];
            sel.innerHTML = list.map(r => {
                const esc = escapeHtml(r);
                const selected = r === rawData.roster ? ' selected' : '';
                return '<option value="' + esc + '"' + selected + '>' + esc + '</option>';
            }).join('');
        }

        function renderCharChips() {
            const wrap = document.getElementById('charChipsWrap');
            if (!wrap) return;
            const items = rawData.items || [];
            const counts = {};
            items.forEach(it => {
                counts[it.char] = (counts[it.char] || 0) + 1;
            });
            const chars = (rawData.chars || []).slice().sort((a, b) => {
                const ca = counts[a.id] ?? a.count ?? 0;
                const cb = counts[b.id] ?? b.count ?? 0;
                if ((ca === 0) !== (cb === 0)) return ca === 0 ? 1 : -1;
                return 0;
            });

            let htmlStr = '<button type="button" class="btn-chip ' + (currentChar === 'all' ? 'active' : '') +
                '" id="char_all" onclick="setCharFilter(&quot;all&quot;)">전체캐릭 (' + items.length + ')</button>';

            chars.forEach(c => {
                const cid = String(c.id || '');
                const cnt = counts[cid] ?? c.count ?? 0;
                const sName = c.short_name || (c.name ? String(c.name).replace(/\s*\([^)]*\)$/, '') : cid);
                const dimStyle = cnt === 0 ? ' style="opacity:0.5;"' : '';
                const activeCls = currentChar === cid ? ' active' : '';
                htmlStr += '<button type="button" class="btn-chip' + activeCls + '" id="char_' + escapeHtml(cid) + '"' +
                    dimStyle + ' onclick="setCharFilter(' + JSON.stringify(cid).replace(/"/g, '&quot;') + ')">' +
                    escapeHtml(sName) + ' (' + cnt + ')</button>';
            });
            wrap.innerHTML = htmlStr;
        }

        function applyFilters(preserveRelPath = null) {
            const items = rawData.items || [];
            filteredItems = items.filter(item => {
                if (currentMode === 'recent' && !item.is_recent) return false;
                if (currentMode === 'new' && !item.is_new) return false;
                if (currentMode === 'qc' && item.qc_passed !== false) return false;
                if (currentChar !== 'all' && item.char !== currentChar) return false;
                return true;
            });
            if (currentSort === 'mtime_desc') {
                filteredItems.sort((a, b) => (b.mtime || 0) - (a.mtime || 0));
            }
            if (preserveRelPath) {
                const keptIdx = filteredItems.findIndex(it => it.rel_path === preserveRelPath);
                if (keptIdx >= 0) currentIndex = keptIdx;
            }
            if (currentIndex >= filteredItems.length) {
                currentIndex = Math.max(0, filteredItems.length - 1);
            }
            updateModeCounts();
            updateView();
            if (currentView === 'grid') {
                renderGrid();
            }
        }

        function toggleSortOrder() {
            currentSort = currentSort === 'mtime_desc' ? 'code_asc' : 'mtime_desc';
            const sortBtn = document.getElementById('chipSort');
            if (sortBtn) {
                sortBtn.classList.toggle('active', currentSort === 'mtime_desc');
                sortBtn.textContent = currentSort === 'mtime_desc' ? '🕒 최신생성순 ✓' : '🕒 최신생성순';
            }
            currentIndex = 0;
            applyFilters();
            if (currentSort === 'mtime_desc') {
                refreshGalleryData(true);
            }
        }

        function setMode(mode) {
            currentMode = mode;
            document.getElementById('chipAll').classList.toggle('active', mode === 'all');
            document.getElementById('chipRecent').classList.toggle('active', mode === 'recent');
            document.getElementById('chipNew').classList.toggle('active', mode === 'new');
            document.getElementById('chipQc').classList.toggle('active', mode === 'qc');
            currentIndex = 0;
            applyFilters();
        }

        function setCharFilter(charId) {
            currentChar = charId;
            const charIds = ['all'].concat((rawData.chars || []).map(c => c.id));
            charIds.forEach(c => {
                const el = document.getElementById('char_' + c);
                if (el) el.classList.toggle('active', c === charId);
            });
            currentIndex = 0;
            applyFilters();
        }

        function toggleViewMode(forceMode = null) {
            const nextView = forceMode || (currentView === 'slide' ? 'grid' : 'slide');
            currentView = nextView;
            const isGrid = currentView === 'grid';

            if (isGrid && immersiveMode) {
                immersiveMode = false;
                document.getElementById('mobileApp').classList.remove('immersive');
            }

            document.getElementById('stage').style.display = isGrid ? 'none' : 'flex';
            document.getElementById('gridView').style.display = isGrid ? 'block' : 'none';
            document.getElementById('bottomOverlay').style.display = isGrid ? 'none' : 'flex';

            const btn = document.getElementById('viewToggleBtn');
            if (btn) {
                btn.classList.toggle('active', isGrid);
                btn.textContent = isGrid ? '🖼️ 슬라이드' : '⊞ 그리드';
            }

            if (isGrid) {
                renderGrid();
            } else {
                cancelGridQueue();
                updateView();
            }
        }

        function openSlideAt(idx) {
            currentIndex = Math.max(0, Math.min(idx, Math.max(0, filteredItems.length - 1)));
            toggleViewMode('slide');
        }

        function cancelGridQueue() {
            ++renderSeq;
            imgLoadQueue = [];
            activeImgLoads = 0;
            if (gridObserver) {
                gridObserver.disconnect();
                gridObserver = null;
            }
        }

        function pumpImageQueue(expectedSeq) {
            while (activeImgLoads < MAX_CONCURRENT_IMG && imgLoadQueue.length > 0) {
                const job = imgLoadQueue.shift();
                if (!job || job.seq !== renderSeq || !job.img || !job.img.isConnected) continue;
                const src = job.img.dataset.src;
                if (!src) continue;
                activeImgLoads++;
                job.img.onload = () => {
                    activeImgLoads = Math.max(0, activeImgLoads - 1);
                    job.img.classList.add('loaded');
                    if (job.img.parentElement) job.img.parentElement.classList.remove('loading');
                    if (job.seq === renderSeq) pumpImageQueue(job.seq);
                };
                job.img.onerror = () => {
                    activeImgLoads = Math.max(0, activeImgLoads - 1);
                    job.img.classList.add('loaded');
                    if (job.img.parentElement) job.img.parentElement.classList.remove('loading');
                    if (job.seq === renderSeq) pumpImageQueue(job.seq);
                };
                job.img.src = src;
            }
        }

        function renderGrid() {
            const container = document.getElementById('gridContainer');
            const gridView = document.getElementById('gridView');
            const statusEl = document.getElementById('gridLoadStatus');
            if (!container || !gridView) return;

            cancelGridQueue();
            const mySeq = renderSeq;
            container.innerHTML = '';

            const total = filteredItems.length;
            if (total === 0) {
                container.innerHTML = '<div style="grid-column:1/-1;text-align:center;color:#64748b;padding:48px 12px;">표시할 에셋이 없습니다. 필터를 변경해보세요.</div>';
                if (statusEl) statusEl.textContent = '';
                return;
            }

            if ('IntersectionObserver' in window) {
                gridObserver = new IntersectionObserver((entries) => {
                    if (mySeq !== renderSeq) return;
                    let added = false;
                    entries.forEach(entry => {
                        if (!entry.isIntersecting) return;
                        const img = entry.target;
                        if (gridObserver) gridObserver.unobserve(img);
                        if (img.dataset.src && !img.dataset.queued) {
                            img.dataset.queued = '1';
                            imgLoadQueue.push({ img, seq: mySeq });
                            added = true;
                        }
                    });
                    if (added) pumpImageQueue(mySeq);
                }, { root: gridView, rootMargin: '240px 0px' });
            }

            let cursor = 0;
            function appendNextChunk() {
                if (mySeq !== renderSeq) return;
                const frag = document.createDocumentFragment();
                const end = Math.min(cursor + MOBILE_CHUNK_SIZE, total);

                for (let idx = cursor; idx < end; idx++) {
                    const item = filteredItems[idx];
                    const card = document.createElement('div');
                    card.className = 'grid-card' + (idx === currentIndex ? ' active-card' : '');
                    card.dataset.rel = item.rel_path;
                    card.onclick = () => openSlideAt(idx);

                    const thumbWrap = document.createElement('div');
                    thumbWrap.className = 'grid-thumb-wrap loading';

                    const img = document.createElement('img');
                    img.className = 'grid-thumb';
                    img.decoding = 'async';
                    img.dataset.src = item.url;
                    img.alt = item.filename || item.code || '';
                    thumbWrap.appendChild(img);

                    if (item.qc_passed === false) {
                        const warn = document.createElement('span');
                        warn.className = 'grid-qc-badge';
                        warn.textContent = '⚠️ QC';
                        thumbWrap.appendChild(warn);
                    }

                    const cap = document.createElement('div');
                    cap.className = 'grid-caption';
                    cap.textContent = '#' + item.code + ' ' + (item.label || item.char);

                    card.appendChild(thumbWrap);
                    card.appendChild(cap);
                    frag.appendChild(card);

                    if (gridObserver) {
                        gridObserver.observe(img);
                    } else {
                        img.dataset.queued = '1';
                        imgLoadQueue.push({ img, seq: mySeq });
                    }
                }

                container.appendChild(frag);
                if (!gridObserver) pumpImageQueue(mySeq);

                cursor = end;
                if (statusEl) {
                    statusEl.textContent = cursor < total
                        ? ('썸네일 순차 배치 중: ' + cursor + ' / ' + total + '장')
                        : ('총 ' + total + '장 (화면에 보이는 카드부터 3장씩 순차 로드)');
                }
                if (cursor < total) {
                    window.requestAnimationFrame(appendNextChunk);
                }
            }

            appendNextChunk();
        }

        function preloadNextSequential(expectedSeq) {
            if (expectedSeq !== slideLoadSeq) return;
            const total = filteredItems.length;
            if (currentIndex + 1 >= total) return;
            const p1 = new Image();
            p1.onload = p1.onerror = () => {
                if (expectedSeq !== slideLoadSeq) return;
                if (currentIndex + 2 < filteredItems.length) {
                    const p2 = new Image();
                    p2.src = filteredItems[currentIndex + 2].url;
                }
            };
            p1.src = filteredItems[currentIndex + 1].url;
        }

        function updateView() {
            const total = filteredItems.length;
            const counter = document.getElementById('counterBadge');
            const mainImg = document.getElementById('mainImg');
            const title = document.getElementById('poseTitle');
            const subtitle = document.getElementById('poseSubtitle');
            const spinner = document.getElementById('slideSpinner');

            if (total === 0) {
                counter.innerText = '0 / 0';
                title.innerText = '표시할 에셋이 없습니다';
                subtitle.innerText = '상단 필터 또는 로스터를 변경해보세요';
                mainImg.removeAttribute('src');
                if (spinner) spinner.classList.remove('visible');
                return;
            }

            const item = filteredItems[currentIndex];
            counter.innerText = (currentIndex + 1) + ' / ' + total;
            title.innerText = '#' + item.code + ' ' + (item.label || item.filename);

            subtitle.innerHTML = '';
            const subText = document.createElement('span');
            subText.textContent = formatCharSubtitle(item);
            subtitle.appendChild(subText);
            if (item.qc_passed === false) {
                const qcTag = document.createElement('span');
                qcTag.className = 'qc-inline-badge';
                qcTag.textContent = '⚠️ ' + (item.qc_reason || 'QC 경고');
                subtitle.appendChild(qcTag);
            }

            if (currentView !== 'slide') return;

            const mySlideSeq = ++slideLoadSeq;
            mainImg.style.opacity = '0.35';
            if (spinner) spinner.classList.add('visible');
            mainImg.onload = () => {
                if (mySlideSeq !== slideLoadSeq) return;
                mainImg.style.opacity = '1';
                if (spinner) spinner.classList.remove('visible');
                preloadNextSequential(mySlideSeq);
            };
            mainImg.onerror = () => {
                if (mySlideSeq !== slideLoadSeq) return;
                mainImg.style.opacity = '1';
                if (spinner) spinner.classList.remove('visible');
            };
            mainImg.src = item.url;
        }

        function prev(e) {
            if (e) e.stopPropagation();
            if (filteredItems.length === 0) return;
            currentIndex = (currentIndex - 1 + filteredItems.length) % filteredItems.length;
            updateView();
        }

        function next(e) {
            if (e) e.stopPropagation();
            if (filteredItems.length === 0) return;
            currentIndex = (currentIndex + 1) % filteredItems.length;
            updateView();
        }

        function getPlepaAuthHeaders(extra = {}) {
            const headers = Object.assign({}, extra || {});
            const tok = new URLSearchParams(window.location.search).get('token');
            if (tok) headers['X-Plepa-Token'] = tok;
            return headers;
        }

        function getSelectedCensorOptions() {
            const styleEl = document.getElementById('censorStyleSelect');
            return {
                censor_style: styleEl ? styleEl.value : 'white_silhouette',
                censor_targets: 'penis',
                min_confidence: 0.16,
                enable_anchor_fallback: false
            };
        }

        // 로스터 즉시 전환 (페이지 리로드 없이 부드럽게 전환)
        async function switchRoster(newRoster) {
            if (!newRoster || newRoster === rawData.roster) return;
            const sel = document.getElementById('rosterSelect');
            if (sel) sel.disabled = true;
            showToast('🔄 [' + newRoster + '] 로스터 불러오는 중...');
            try {
                const res = await fetch('/api/mobile/gallery?roster=' + encodeURIComponent(newRoster), {
                    headers: getPlepaAuthHeaders()
                });
                const nextData = await res.json();
                if (!res.ok) throw new Error(nextData.detail || ('HTTP ' + res.status));

                rawData = nextData;
                currentChar = 'all';
                currentIndex = 0;

                const hasRecent = (rawData.items || []).some(i => i.is_recent);
                const nextMode = (currentMode === 'recent' && !hasRecent)
                    ? 'all'
                    : (currentMode === 'all' && hasRecent ? 'recent' : currentMode);

                renderRosterSelect();
                renderCharChips();
                updateModeCounts();
                setMode(nextMode);

                try {
                    const u = new URL(window.location.href);
                    u.searchParams.set('roster', rawData.roster);
                    window.history.replaceState(null, '', u.toString());
                } catch (err) {}

                showToast('✅ [' + rawData.roster + '] ' + (rawData.items || []).length + '장 로드 완료');
            } catch (err) {
                showToast('❌ 로스터 전환 실패: ' + err.message);
                renderRosterSelect();
            } finally {
                if (sel) sel.disabled = false;
            }
        }

        function onPlepaMobileRetouchSaved(savedPayload) {
            if (!savedPayload) return;
            const targetItem = (rawData.items || []).find(it => it.rel_path === savedPayload.rel_path);
            if (targetItem) {
                targetItem.url = targetItem.url.split('?')[0] + '?t=' + savedPayload.timestamp;
            }
            updateView();
            if (currentView === 'grid') renderGrid();
        }

        // 에셋 삭제 (휴지통 안전 이동)
        async function triggerDelete(e) {
            if (e) e.stopPropagation();
            if (filteredItems.length === 0) return;

            const item = filteredItems[currentIndex];
            const targetName = '#' + item.code + ' ' + formatCharSubtitle(item);

            try {
                const res = await fetch('/api/assets/delete', {
                    method: 'POST',
                    headers: getPlepaAuthHeaders({ 'Content-Type': 'application/json' }),
                    body: JSON.stringify({ rel_path: item.rel_path, roster: rawData.roster })
                });
                const data = await res.json();
                if (data.success) {
                    lastDeletedBundle = { item: item, moved: data.data.moved };
                    rawData.items = rawData.items.filter(x => x.rel_path !== item.rel_path);
                    rawData.total_missing = (rawData.total_missing || 0) + 1;
                    renderCharChips();
                    applyFilters();
                    showToast('🗑️ ' + targetName + ' 휴지통 이동됨', true);
                } else {
                    showToast('❌ 삭제 실패');
                }
            } catch (err) {
                showToast('❌ 오류: ' + err.message);
            }
        }

        // 삭제 실행 취소 (Undo)
        async function triggerUndo() {
            if (!lastDeletedBundle) return;
            try {
                const res = await fetch('/api/assets/undo', {
                    method: 'POST',
                    headers: getPlepaAuthHeaders({ 'Content-Type': 'application/json' }),
                    body: JSON.stringify({ moved: lastDeletedBundle.moved })
                });
                const data = await res.json();
                if (data.success) {
                    rawData.items.push(lastDeletedBundle.item);
                    rawData.total_missing = Math.max(0, (rawData.total_missing || 1) - 1);
                    renderCharChips();
                    applyFilters();
                    showToast('✅ 원상 복원 완료!');
                    lastDeletedBundle = null;
                } else {
                    showToast('❌ 복원 실패');
                }
            } catch (err) {
                showToast('❌ 오류: ' + err.message);
            }
        }

        // 무검열 원본(_origin) 즉시 복원
        async function triggerRestoreOrigin(e) {
            if (e) e.stopPropagation();
            if (filteredItems.length === 0) return;
            const item = filteredItems[currentIndex];
            if (!confirm('#' + item.code + ' [' + item.char + '] 이미지를 무검열 원본(_origin)으로 복원하시겠습니까?')) return;

            try {
                const res = await fetch('/api/assets/restore-origin', {
                    method: 'POST',
                    headers: getPlepaAuthHeaders({ 'Content-Type': 'application/json' }),
                    body: JSON.stringify({ rel_path: item.rel_path, roster: rawData.roster })
                });
                const data = await res.json();
                if (res.ok && data.success) {
                    item.url = item.url.split('?')[0] + '?t=' + Date.now();
                    updateView();
                    showToast('✅ 원본 이미지로 복원 완료!');
                } else {
                    showToast('❌ 원본 복원 실패: ' + (data.detail || '알 수 없는 오류'));
                }
            } catch (err) {
                showToast('❌ 요청 오류: ' + err.message);
            }
        }

        // 0.2초 즉시 재검열
        async function triggerReapplyCensor(e) {
            if (e) e.stopPropagation();
            if (filteredItems.length === 0) return;
            const item = filteredItems[currentIndex];
            const opts = getSelectedCensorOptions();

            showToast('⚡ #' + item.code + ' ' + opts.censor_style + ' 재검열 중...');
            try {
                const res = await fetch('/api/assets/reapply-censor', {
                    method: 'POST',
                    headers: getPlepaAuthHeaders({ 'Content-Type': 'application/json' }),
                    body: JSON.stringify({
                        rel_path: item.rel_path,
                        roster: rawData.roster,
                        pose_code: item.code,
                        censor_style: opts.censor_style,
                        censor_targets: opts.censor_targets,
                        min_confidence: opts.min_confidence,
                        enable_anchor_fallback: opts.enable_anchor_fallback
                    })
                });
                const data = await res.json();
                if (res.ok && data.success) {
                    item.url = item.url.split('?')[0] + '?t=' + Date.now();
                    updateView();
                    showToast('⚡ 재검열 완료 (' + opts.censor_style + ', 탐지 ' + (data.detected_count ?? 0) + '건)');
                } else {
                    showToast('❌ 재검열 실패: ' + (data.detail || '알 수 없는 오류'));
                }
            } catch (err) {
                showToast('❌ 요청 오류: ' + err.message);
            }
        }

        // 수동 캔버스 직접 검열/덧칠 에디터 열기
        function triggerRetouch(e) {
            if (e) e.stopPropagation();
            if (filteredItems.length === 0) return;
            const item = filteredItems[currentIndex];
            if (typeof openRetouchEditor === 'function') {
                openRetouchEditor({
                    relPath: item.rel_path,
                    roster: rawData.roster,
                    title: '✏️ #' + item.code + ' ' + (item.label || item.filename),
                    imageUrl: item.url,
                    originUrl: item.origin_url || ''
                });
            }
        }

        // 현재 포즈 단독 리롤 (실수 클릭 방지 확인 팝업 포함)
        async function triggerReroll(e) {
            if (e) e.stopPropagation();
            if (filteredItems.length === 0) return;
            const item = filteredItems[currentIndex];
            if (!confirm('#' + item.code + ' [' + formatCharSubtitle(item) + '] 이미지를 새 시드로 리롤 대기열에 등록하시겠습니까?')) return;
            const opts = getSelectedCensorOptions();

            showToast('🎲 #' + item.code + ' [' + item.char + '] 리롤 대기열 등록 중...');
            try {
                const res = await fetch('/api/assets/reroll', {
                    method: 'POST',
                    headers: getPlepaAuthHeaders({ 'Content-Type': 'application/json' }),
                    body: JSON.stringify({
                        char: item.char,
                        code: item.code,
                        roster: rawData.roster,
                        reuse_seed: false,
                        censor_style: opts.censor_style,
                        censor_targets: opts.censor_targets,
                        auto_qc: true
                    })
                });
                const data = await res.json();
                if (res.ok && data.success) {
                    showToast('🎲 ' + (data.message || ('#' + item.code + ' 리롤 대기열 등록 완료')));
                    pollJobStatus();
                } else {
                    showToast('❌ 리롤 실패: ' + (data.detail || '알 수 없는 오류'));
                }
            } catch (err) {
                showToast('❌ 리롤 요청 오류: ' + err.message);
            }
        }

        // 누락 포즈 전체 일괄 생성
        async function triggerFillMissing() {
            const count = document.getElementById('missingCountBadge').innerText;
            if (count === '0') {
                showToast('✨ 누락된 포즈가 없습니다. 모든 포즈 완비!');
                return;
            }
            if (!confirm('현재 로스터의 비어있는 포즈 ' + count + '개를 모두 백그라운드로 자동 생성하시겠습니까?')) return;

            closeSettingsSheet();
            const opts = getSelectedCensorOptions();
            showToast('⚡ 누락 포즈 ' + count + '개 백그라운드 생성 시작...');
            try {
                const res = await fetch('/api/assets/fill-missing', {
                    method: 'POST',
                    headers: getPlepaAuthHeaders({ 'Content-Type': 'application/json' }),
                    body: JSON.stringify({
                        roster: rawData.roster,
                        censor_style: opts.censor_style,
                        censor_targets: opts.censor_targets,
                        auto_qc: true
                    })
                });
                const data = await res.json();
                showToast('🚀 ' + data.message);
                pollJobStatus();
            } catch (err) {
                showToast('❌ 요청 오류: ' + err.message);
            }
        }

        // 백그라운드 생성 완료 시 최신 mtime·이미지 즉시 동기화
        async function refreshGalleryData(silent = true) {
            if (isRefreshingGallery) return;
            isRefreshingGallery = true;
            const prevRelPath = (filteredItems[currentIndex] && filteredItems[currentIndex].rel_path)
                ? filteredItems[currentIndex].rel_path
                : null;
            try {
                const res = await fetch('/api/mobile/gallery?roster=' + encodeURIComponent(rawData.roster), {
                    headers: getPlepaAuthHeaders()
                });
                if (!res.ok) return;
                const nextData = await res.json();
                rawData = nextData;
                renderRosterSelect();
                renderCharChips();
                updateModeCounts();
                if (currentSort === 'mtime_desc') {
                    currentIndex = 0;
                    applyFilters(null);
                } else {
                    applyFilters(prevRelPath);
                }
            } catch (err) {
                if (!silent) showToast('❌ 목록 갱신 실패: ' + err.message);
            } finally {
                isRefreshingGallery = false;
            }
        }

        // 원터치 최신 목록 + 대기열 강제 동기화 (외부 CLI 생성분 포함)
        async function manualRefreshGallery() {
            await refreshGalleryData(false);
            await pollJobStatus();
            showToast('🔄 최신 에셋 목록 동기화 완료');
        }

        // 대기열 · 진행 현황 패널 렌더링
        function renderQueuePanel(status) {
            const panel = document.getElementById('queueStatusPanel');
            const summaryEl = document.getElementById('queueSummaryText');
            if (!panel || !status) return;

            const isRunning = !!status.is_running;
            const queued = Array.isArray(status.queued_jobs) ? status.queued_jobs : [];
            const completed = Array.isArray(status.completed_items) ? status.completed_items : [];
            const active = status.active_job || null;

            if (summaryEl) {
                if (isRunning || queued.length > 0) {
                    summaryEl.textContent = (isRunning ? '진행 1' : '진행 0') + ' · 대기 ' + queued.length;
                    summaryEl.style.color = '#fbbf24';
                } else {
                    summaryEl.textContent = '대기 없음';
                    summaryEl.style.color = '#94a3b8';
                }
            }

            const chunks = [];
            if (isRunning && active) {
                const cur = Number(status.current || 0);
                const tot = Math.max(1, Number(status.total || 1));
                const pct = Math.min(100, Math.max(0, Number(status.percentage || Math.round((cur / tot) * 100))));
                const msg = status.current_msg ? escapeHtml(status.current_msg) : '이미지 생성 중...';
                chunks.push(
                    '<div class="q-item running">' +
                    '<div class="q-item-top"><span>⚡ 진행중: ' + escapeHtml(active.label || '') + '</span><span>' + cur + '/' + tot + ' (' + pct + '%)</span></div>' +
                    '<div class="q-bar-bg"><div class="q-bar-fill" style="width:' + pct + '%;"></div></div>' +
                    '<div class="q-item-sub">' + msg + '</div>' +
                    '</div>'
                );
            }

            queued.forEach((job, idx) => {
                chunks.push(
                    '<div class="q-item queued">' +
                    '<div class="q-item-top"><span>⏳ 대기 #' + (idx + 1) + ': ' + escapeHtml(job.label || '') + '</span><span style="color:#94a3b8;">' + escapeHtml(job.queued_at || '') + '</span></div>' +
                    '</div>'
                );
            });

            completed.slice(0, 5).forEach(done => {
                const icon = done.qc_passed === false ? '⚠️' : '✅';
                const dur = done.duration_sec !== undefined && done.duration_sec !== null ? (done.duration_sec + '초') : '';
                chunks.push(
                    '<div class="q-item">' +
                    '<div class="q-item-top"><span>' + icon + ' #' + escapeHtml(done.code || '?') + ' [' + escapeHtml(done.char || '') + ']</span><span style="color:#94a3b8;">' + escapeHtml(dur) + '</span></div>' +
                    '</div>'
                );
            });

            if (chunks.length === 0) {
                panel.innerHTML = '<div style="text-align:center;color:#64748b;font-size:11px;padding:12px 0;">진행 중이거나 대기 중인 생성 작업이 없습니다.</div>';
            } else {
                panel.innerHTML = chunks.join('');
            }
        }

        // 대기열 상태 폴링 + 1장 완료 즉시 이미지·정렬 자동 반영
        async function pollJobStatus() {
            if (isPollingJob) return;
            isPollingJob = true;
            try {
                const res = await fetch('/api/assets/job-status', {
                    headers: getPlepaAuthHeaders()
                });
                if (!res.ok) return;
                const status = await res.json();
                renderQueuePanel(status);
                const badge = document.getElementById('jobQueueBadge');
                const isRunning = !!status.is_running;
                const qLen = Number(status.queue_length || 0);

                if (badge) {
                    if (isRunning || qLen > 0) {
                        const totalActive = qLen + (isRunning ? 1 : 0);
                        badge.textContent = qLen > 0 ? ('🎲 진행+대기 ' + totalActive) : '🎲 생성중';
                        badge.style.display = 'inline-flex';
                    } else {
                        badge.style.display = 'none';
                    }
                }

                const completed = Array.isArray(status.completed_items) ? status.completed_items : [];
                const top = completed[0] || {};
                const latestTs = status.latest_result ? (status.latest_result.timestamp || '') : '';
                const curSig = completed.length + '|' + (top.job_id || '') + '|' + (top.timestamp || '') + '|' + (top.filename || '') + '|' + latestTs;

                if (!jobPollInitialized) {
                    lastCompletedSig = curSig;
                    jobPollInitialized = true;
                } else if (curSig !== lastCompletedSig) {
                    lastCompletedSig = curSig;
                    await refreshGalleryData(true);
                    if (top && top.code) {
                        showToast('✅ #' + top.code + ' [' + (top.char || '') + '] 재생성 반영됨');
                    }
                }
            } catch (err) {
                // 일시적 네트워크 단절 시 다음 주기에 자동 재시도
            } finally {
                isPollingJob = false;
            }
        }

        function onStageClick(e) {
            if (currentView !== 'slide') return;
            const rect = e.currentTarget.getBoundingClientRect();
            const x = e.clientX - rect.left;
            const w = rect.width;
            if (x < w * 0.24 || x > w * 0.76) return;

            immersiveMode = !immersiveMode;
            document.getElementById('mobileApp').classList.toggle('immersive', immersiveMode);
        }

        // 터치 스와이프 제스처
        let touchStartX = 0;
        let touchStartY = 0;
        const stage = document.getElementById('stage');

        stage.addEventListener('touchstart', (e) => {
            touchStartX = e.changedTouches[0].screenX;
            touchStartY = e.changedTouches[0].screenY;
        }, { passive: true });

        stage.addEventListener('touchend', (e) => {
            if (currentView !== 'slide') return;
            const touchEndX = e.changedTouches[0].screenX;
            const touchEndY = e.changedTouches[0].screenY;
            const diffX = touchEndX - touchStartX;
            const diffY = touchEndY - touchStartY;

            if (Math.abs(diffX) > Math.abs(diffY) && Math.abs(diffX) > 40) {
                if (diffX > 0) prev();
                else next();
            }
        }, { passive: true });

        // PC 키보드 화살표 & ESC
        window.addEventListener('keydown', (e) => {
            if (window.__plepaRetouchOpen) return;
            if (e.key === 'Escape') closeSettingsSheet();
            if (currentView === 'slide') {
                if (e.key === 'ArrowLeft') prev();
                if (e.key === 'ArrowRight' || e.key === ' ') next();
                if (e.key === 'Delete') triggerDelete();
                if (e.key === 'r' || e.key === 'R') triggerReroll();
            }
        });

        // 초기화
        renderRosterSelect();
        renderCharChips();
        updateModeCounts();
        setCharFilter('all');
        pollJobStatus();
        setInterval(() => {
            if (!document.hidden) pollJobStatus();
        }, 2500);
        document.addEventListener('visibilitychange', () => {
            if (!document.hidden) pollJobStatus();
        });
