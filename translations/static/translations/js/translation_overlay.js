(function() {
    // Only initialize if we see editable elements or markers
    let activeElement = null;

    // Create the modal HTML with updated UI
    const modalHtml = `
        <div id="studio-modal" style="display:none; position:fixed; z-index:9999999; left:0; top:0; width:100%; height:100%; background:rgba(0,0,0,0.4); backdrop-filter:blur(8px); font-family: 'Inter', system-ui, -apple-system, sans-serif;">
            <div style="position:relative; background: #fff; margin: 8% auto; padding: 24px; width: 550px; border-radius: 20px; box-shadow: 0 25px 50px -12px rgba(0,0,0,0.25); border: 1px solid rgba(0,0,0,0.05);">
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:16px;">
                    <h3 style="margin:0; font-size:1.25rem; font-weight:700; color:#1e293b;">Edit Translation</h3>
                    <a id="studio-jump" href="#" target="_blank" style="font-size:0.8rem; color:#6366f1; text-decoration:none; font-weight:600; display:flex; align-items:center; gap:4px; padding:4px 8px; border-radius:6px; background:rgba(99,102,241,0.1);">
                        🔎 Open in Studio Dashboard
                    </a>
                </div>
                
                <p id="studio-msgid" style="font-family:ui-monospace, monospace; font-size:0.75rem; color:#64748b; word-break:break-all; background:#f8fafc; padding:12px; border-radius:10px; border:1px solid #e2e8f0; margin-bottom:20px; max-height:60px; overflow-y:auto;"></p>
                
                <div style="display:grid; gap:16px;">
                    <div class="lang-field">
                        <label style="display:block; font-size:0.75rem; font-weight:700; color:#475569; text-transform:uppercase; letter-spacing:0.025em; margin-bottom:6px;">RU - Russian</label>
                        <textarea id="studio-ru" placeholder="Russian translation..." style="width:100%; height:70px; padding:12px; border:1px solid #e2e8f0; border-radius:10px; font-size:0.925rem; transition:border-color 0.2s; resize:vertical;"></textarea>
                    </div>
                    <div class="lang-field">
                        <label style="display:block; font-size:0.75rem; font-weight:700; color:#475569; text-transform:uppercase; letter-spacing:0.025em; margin-bottom:6px;">EN - English</label>
                        <textarea id="studio-en" placeholder="English translation..." style="width:100%; height:70px; padding:12px; border:1px solid #e2e8f0; border-radius:10px; font-size:0.925rem; transition:border-color 0.2s; resize:vertical;"></textarea>
                    </div>
                    <div class="lang-field">
                        <label style="display:block; font-size:0.75rem; font-weight:700; color:#475569; text-transform:uppercase; letter-spacing:0.025em; margin-bottom:6px;">PL - Polish</label>
                        <textarea id="studio-pl" placeholder="Polish translation..." style="width:100%; height:70px; padding:12px; border:1px solid #e2e8f0; border-radius:10px; font-size:0.925rem; transition:border-color 0.2s; resize:vertical;"></textarea>
                    </div>
                </div>
                
                <div style="margin-top:24px; display:flex; justify-content:flex-end; gap:12px;">
                    <button id="studio-cancel" style="padding:10px 20px; border:1px solid #e2e8f0; background:#fff; color:#64748b; border-radius:10px; cursor:pointer; font-weight:600; font-size:0.9rem;">Cancel</button>
                    <button id="studio-save" style="padding:10px 24px; border:none; background:#6366f1; color:#fff; border-radius:10px; cursor:pointer; font-weight:600; font-size:0.9rem; box-shadow:0 4px 6px -1px rgba(99,102,241,0.2);">Save & Compile</button>
                </div>
            </div>
        </div>
    `;

    document.body.insertAdjacentHTML('beforeend', modalHtml);

    const modal = document.getElementById('studio-modal');
    const msgidEl = document.getElementById('studio-msgid');
    const jumpLink = document.getElementById('studio-jump');
    const ruInput = document.getElementById('studio-ru');
    const enInput = document.getElementById('studio-en');
    const plInput = document.getElementById('studio-pl');

    // Small runtime state
    let scanMap = null; // translated string -> msgid mapping (fetched from server)
    let lastStudioOpenAt = 0;

    // Intercept modifier + mousedown early to prevent browser opening links
    // (some browsers trigger new-tab navigation on modifier+click). We handle
    // mousedown in capture phase and open the studio there to avoid navigation.
    document.addEventListener('mousedown', function(e) {
        if ((e.ctrlKey && e.shiftKey) || (e.altKey && e.shiftKey)) {
            const x = e.clientX, y = e.clientY;
            // Quick nearest-element search using elementFromPoint first
            try {
                let node = document.elementFromPoint(x, y);
                if (node) {
                    const direct = node.closest && node.closest('.studio-editable');
                    if (direct) {
                        try { e.preventDefault(); e.stopPropagation(); } catch(_) {}
                        lastStudioOpenAt = Date.now();
                        try { console.debug('studio overlay open triggered (mousedown)', {ctrl: e.ctrlKey, alt: e.altKey, shift: e.shiftKey, clientX: x, clientY: y}); } catch(_) {}
                        openStudio(direct);
                        return;
                    }
                }

                // Fallback: search for the nearest .studio-editable on the page
                const candidates = Array.from(document.querySelectorAll('.studio-editable'));
                if (candidates.length) {
                    // Prefer candidate that contains the point
                    for (const c of candidates) {
                        try {
                            const r = c.getBoundingClientRect();
                            if (x >= r.left && x <= r.right && y >= r.top && y <= r.bottom) {
                                try { e.preventDefault(); e.stopPropagation(); } catch(_) {}
                                lastStudioOpenAt = Date.now();
                                try { console.debug('studio overlay open triggered (mousedown)', {ctrl: e.ctrlKey, alt: e.altKey, shift: e.shiftKey, clientX: x, clientY: y}); } catch(_) {}
                                openStudio(c);
                                return;
                            }
                        } catch(_) {}
                    }
                    // Otherwise pick nearest center
                    let best=null, bestDist=Infinity;
                    for (const c of candidates) {
                        try {
                            const r = c.getBoundingClientRect();
                            const cx = (r.left + r.right)/2, cy = (r.top + r.bottom)/2;
                            const dx = cx - x, dy = cy - y, d = dx*dx + dy*dy;
                            if (d < bestDist) { bestDist = d; best = c; }
                        } catch(_) {}
                    }
                    if (best) {
                        try { e.preventDefault(); e.stopPropagation(); } catch(_) {}
                        lastStudioOpenAt = Date.now();
                        try { console.debug('studio overlay open triggered (mousedown)', {ctrl: e.ctrlKey, alt: e.altKey, shift: e.shiftKey, clientX: x, clientY: y}); } catch(_) {}
                        openStudio(best);
                        return;
                    }
                }
            } catch (e) {
                // swallow
            }
        }
    }, true);

    // Handle Ctrl+Shift or Alt+Shift + Click (Alt+Shift added for convenience)
    document.addEventListener('click', function(e) {
        if ((e.ctrlKey && e.shiftKey) || (e.altKey && e.shiftKey)) {
            // If we just opened the studio on mousedown, ignore the subsequent click
            if (Date.now() - lastStudioOpenAt < 500) {
                try { e.preventDefault(); } catch(_) {}
                try { e.stopPropagation(); } catch(_) {}
                return;
            }
            // Find the most relevant .studio-editable near the click.
            function findStudioTarget(node, clientX, clientY) {
                if (!node) return null;
                let el = (node.nodeType === 3) ? node.parentElement : node;
                if (!el) return null;

                // 1) If the clicked node or an ancestor is itself a studio-editable, prefer it.
                try {
                    const direct = el.closest && el.closest('.studio-editable');
                    if (direct) return direct;
                } catch (_) {}

                // Helper: choose best candidate from a NodeList of elements using click coords
                function chooseBest(candidates) {
                    if (!candidates || !candidates.length) return null;
                    // Prefer any element whose bounding rect contains the click point
                    for (const c of candidates) {
                        try {
                            const r = c.getBoundingClientRect();
                            if (clientX >= r.left && clientX <= r.right && clientY >= r.top && clientY <= r.bottom) return c;
                        } catch (_) {}
                    }
                    // Otherwise pick the element whose center is nearest to the click
                    let best = null; let bestDist = Infinity;
                    for (const c of candidates) {
                        try {
                            const r = c.getBoundingClientRect();
                            const cx = (r.left + r.right) / 2; const cy = (r.top + r.bottom) / 2;
                            const dx = cx - clientX; const dy = cy - clientY; const d = dx*dx + dy*dy;
                            if (d < bestDist) { bestDist = d; best = c; }
                        } catch (_) {}
                    }
                    return best || candidates[0] || null;
                }

                // 2) Look for descendants of the clicked element first
                try {
                    const desc = Array.from(el.querySelectorAll && el.querySelectorAll('.studio-editable') || []);
                    const found = chooseBest(desc);
                    if (found) return found;
                } catch (_) {}

                // 3) Walk up ancestors and look for candidates in their subtrees
                let ancestor = el.parentElement;
                while (ancestor && ancestor !== document.documentElement) {
                    try {
                        const inside = Array.from(ancestor.querySelectorAll('.studio-editable') || []);
                        const found = chooseBest(inside);
                        if (found) return found;
                    } catch (_) {}
                    ancestor = ancestor.parentElement;
                }

                return null;
            }

            const target = findStudioTarget(e.target, e.clientX, e.clientY);
            if (target) {
                // Prevent default link behavior (open in new tab) and stop propagation
                // so browser doesn't follow the href when Ctrl/Cmd is pressed.
                try { e.preventDefault(); } catch(_) {}
                try { e.stopPropagation(); } catch(_) {}
                try { console.debug('studio overlay open triggered', {ctrl: e.ctrlKey, alt: e.altKey, shift: e.shiftKey, clientX: e.clientX, clientY: e.clientY}); } catch(_) {}
                openStudio(target);
            }
        }
    }, true);

    // Load mapping of translated text -> msgid for the current language.
    // This allows the overlay to find and wrap translations that the server
    // missed (for example when partials are included in a way that bypasses
    // our gettext wrapper).
    (async function loadScanMap(){
        try {
            const res = await fetch('/studio/scan-api/');
            const json = await res.json();
            if (json && json.status === 'ok') scanMap = json.data || {};
            else scanMap = {};
            // We've just loaded the mapping from server — run a scan pass
            // to wrap any matching elements that are already present in DOM.
            try { scanAndWrap(); } catch(_) {}
        } catch (e) {
            console.error('Studio scan map load failed', e);
            scanMap = {};
            try { scanAndWrap(); } catch(_) {}
        }
    })();

    async function openStudio(el) {
        // remove previous highlight if any, then highlight this element
        try { if (activeElement && activeElement.classList) activeElement.classList.remove('studio-highlight'); } catch(_) {}
        activeElement = el;
        try { if (activeElement && activeElement.classList) activeElement.classList.add('studio-highlight'); } catch(_) {}
        
        const normalizeText = (s) => (s || "").replace(/\s+/g, ' ').trim();

        // 1. Initial ID from data-msgid or text content.
        // IMPORTANT: keep the original key untouched for API round-trips.
        // Normalization is only used for fuzzy lookup in scanMap.
        let rawId = el.dataset.msgid || el.innerText || "";
        let msgid = rawId;
        const normalizedId = normalizeText(rawId);
        
        // 2. Try to resolve via scanMap (contains all languages -> msgid)
        if (scanMap) {
            const normContent = normalizeText(el.innerText);
            // Check direct msgid first, then contents
            if (scanMap[msgid]) {
                msgid = scanMap[msgid];
            } else if (scanMap[normalizedId]) {
                msgid = scanMap[normalizedId];
            } else if (scanMap[normContent]) {
                msgid = scanMap[normContent];
            }
        }
        
        msgidEl.innerText = msgid;
        jumpLink.href = `/studio/dashboard/?query=${encodeURIComponent(msgid)}`;
        
        // Show loading state
        ruInput.value = "Loading...";
        enInput.value = "Loading...";
        plInput.value = "Loading...";
        modal.style.display = 'block';

        // Fetch current translations from server
        try {
            const response = await fetch(`/studio/get-api/?msgid=${encodeURIComponent(msgid)}`);
            const result = await response.json();
            if (result.status === 'ok') {
                ruInput.value = result.data.ru || "";
                enInput.value = result.data.en || "";
                plInput.value = result.data.pl || "";
            } else {
                // Return a default if fetch failed (e.g. still not found)
                ruInput.value = msgid;
            }
        } catch (e) {
            console.error("Studio Load Error:", e);
        }
    }

    document.getElementById('studio-cancel').onclick = () => {
        modal.style.display = 'none';
        try { if (activeElement && activeElement.classList) activeElement.classList.remove('studio-highlight'); } catch(_) {}
    };

    function resolveCurrentLanguage() {
        const fromHtml = (document.documentElement.lang || '').split('-')[0];
        if (fromHtml) return fromHtml;

        try {
            const cookieLang = (getCookie('django_language') || '').split('-')[0];
            if (cookieLang) return cookieLang;
        } catch (_) {}

        const pathLang = (window.location.pathname || '').split('/').filter(Boolean)[0];
        if (['ru', 'en', 'pl'].includes(pathLang)) return pathLang;

        return 'pl';
    }

    document.getElementById('studio-save').onclick = async () => {
        const msgid = msgidEl.innerText;
        const data = {
            msgid: msgid,
            ru: ruInput.value,
            en: enInput.value,
            pl: plInput.value
        };

        const btn = document.getElementById('studio-save');
        const oldText = btn.innerText;
        btn.innerText = "Processing...";
        btn.disabled = true;

        try {
            const response = await fetch('/studio/update/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCookie('csrftoken')
                },
                body: JSON.stringify(data)
            });

            let result = null;
            try {
                result = await response.json();
            } catch (_) {
                result = null;
            }

            if (response.ok && result && result.status === 'ok') {
                if (activeElement) {
                    var currentLang = resolveCurrentLanguage();
                    const translatedText = (currentLang === 'ru') ? ruInput.value : (currentLang === 'en' ? enInput.value : plInput.value);
                    // Update all elements that carry this msgid (editable spans and clickable containers)
                    const selector = `[data-msgid="${CSS.escape(msgid)}"]`;
                    const sameKeyElements = document.querySelectorAll(selector);
                    sameKeyElements.forEach(el => {
                        try {
                            el.innerText = translatedText;
                        } catch (_) {}
                    });
                    // Keep the currently selected node in sync even if selector misses
                    // because of provisional or transformed data-msgid values.
                    try { activeElement.innerText = translatedText; } catch (_) {}
                }
                if (scanMap) {
                    scanMap[msgid] = msgid;
                    if (ruInput.value) scanMap[normalizeText(ruInput.value)] = msgid;
                    if (enInput.value) scanMap[normalizeText(enInput.value)] = msgid;
                    if (plInput.value) scanMap[normalizeText(plInput.value)] = msgid;
                }
                modal.style.display = 'none';
                try { if (activeElement && activeElement.classList) activeElement.classList.remove('studio-highlight'); } catch(_) {}
            } else {
                alert((result && result.message) ? `Error saving translation: ${result.message}` : 'Error saving translation');
            }
        } catch (e) {
            console.error(e);
            alert('Error saving translation');
        } finally {
            btn.innerText = oldText;
            btn.disabled = false;
        }
    };

    function getCookie(name) {
        let cookieValue = null;
        if (document.cookie && document.cookie !== '') {
            const cookies = document.cookie.split(';');
            for (let i = 0; i < cookies.length; i++) {
                const cookie = cookies[i].trim();
                if (cookie.substring(0, name.length + 1) === (name + '=')) {
                    cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                    break;
                }
            }
        }
        return cookieValue;
    }

    // Modern Lavender/Blue Highlight Styling
    const style = document.createElement('style');
    style.innerHTML = `
        .studio-editable {
            transition: all 0.3s ease;
            position: relative;
        }
        .studio-editable:hover {
            background-color: rgba(99, 102, 241, 0.08);
            box-shadow: 0 0 0 4px rgba(99, 102, 241, 0.12);
            border-radius: 4px;
            cursor: pointer;
            color: #4f46e5;
        }
        .studio-editable::after {
            content: '✎';
            position: absolute;
            top: -12px;
            right: -12px;
            font-size: 10px;
            background: #6366f1;
            color: white;
            width: 16px;
            height: 16px;
            display: flex;
            align-items: center;
            justify-content: center;
            border-radius: 50%;
            opacity: 0;
            transition: opacity 0.2s;
            pointer-events: none;
        }
        .studio-editable:hover::after {
            opacity: 1;
        }
        .studio-highlight {
            box-shadow: 0 0 0 8px rgba(99, 102, 241, 0.14) !important;
            outline: 2px solid rgba(99,102,241,0.18) !important;
            border-radius: 6px !important;
            transition: box-shadow 0.15s ease, outline 0.15s ease;
        }
        .studio-clickable-container {
            cursor: pointer;
        }
        .studio-clickable-container:hover {
            outline: 1px dashed #6366f1;
        }
        textarea:focus {
            outline: none;
            border-color: #6366f1 !important;
            box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.1);
        }
    `;
    document.head.appendChild(style);

    // Deep Fix: Convert [[i18n:...]] to Spans on the fly if middleware missed them
    // or if they are loaded dynamically via partials
    /**
     * Restore and improve the DOM scanning logic for the Translation Studio.
     * This version is comprehensive (wraps all visible text) but safe (no innerHTML).
     */
    function scanAndWrap(root = document.body) {
        if (!root || root.id === 'studio-modal' || (root.closest && root.closest('#studio-modal'))) return;

        // Skip non-visible or technical elements
        const skipTags = ['SCRIPT', 'STYLE', 'TEXTAREA', 'INPUT', 'NOSCRIPT', 'CODE', 'PRE', 'OPTION', 'SELECT', 'SVG', 'CANVAS', 'IFRAME'];
        
        const isSafeToWrap = (node) => {
            if (!node || !node.parentNode) return false;
            const parent = (node.nodeType === 3) ? node.parentNode : node;
            if (parent.closest && (parent.closest('.studio-editable') || parent.closest('#studio-modal'))) return false;
            if (skipTags.includes(parent.nodeName)) return false;
            // Prevent wrapping nodes that are too long or clearly data-like
            if (node.nodeType === 3 && node.nodeValue.length > 500) return false;
            return true;
        };

        // 1) First Pass: Map explicit server-side markers [[i18n:...]]
        const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, null, false);
        let tnode;
        const markerNodes = [];
        while(tnode = walker.nextNode()) {
            if (tnode.nodeValue && tnode.nodeValue.includes('[[i18n:')) {
                if (isSafeToWrap(tnode)) markerNodes.push(tnode);
            }
        }

        markerNodes.forEach(textNode => {
            const content = textNode.nodeValue;
            const parent = textNode.parentNode;
            if (!parent) return;

            const regex = /\[\[i18n:(?<msgid>.*?)\]\](?<text>.*?)\[\[\/i18n\]\]/gs;
            let lastIndex = 0;
            const fragment = document.createDocumentFragment();
            let match;
            let found = false;
            
            while ((match = regex.exec(content)) !== null) {
                found = true;
                fragment.appendChild(document.createTextNode(content.substring(lastIndex, match.index)));
                
                const span = document.createElement('span');
                span.className = 'studio-editable';
                span.dataset.msgid = match[1]; // msgid
                span.innerText = match[2]; // text content
                fragment.appendChild(span);
                lastIndex = regex.lastIndex;
            }
            
            if (found) {
                fragment.appendChild(document.createTextNode(content.substring(lastIndex)));
                parent.replaceChild(fragment, textNode);
            }
        });

        // 2) Second Pass: Exact matching of keys from the scanMap (for templates and standard text)
        // We do this by searching for known translations in text nodes.
        if (scanMap && Object.keys(scanMap).length) {
            const sortedKeys = Object.keys(scanMap)
                .filter(k => k && k.trim().length > 1)
                .sort((a,b) => b.length - a.length);
            
            if (sortedKeys.length) {
                // Focus on plain text keys (for safety)
                const plainKeys = sortedKeys.filter(k => !k.includes('<'));
                if (plainKeys.length) {
                    const escapedKeys = plainKeys.map(k => k.replace(/[.*+?^${}()|[\\]\\]/g, "\\$&"));
                    const mapRegex = new RegExp(escapedKeys.join('|'), 'g');

                    const walker2 = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, null, false);
                    let mnode;
                    const plainMatches = [];
                    while(mnode = walker2.nextNode()) {
                        if (mnode.nodeValue && mapRegex.test(mnode.nodeValue)) {
                            if (isSafeToWrap(mnode)) plainMatches.push(mnode);
                        }
                        mapRegex.lastIndex = 0;
                    }

                    plainMatches.forEach(textNode => {
                        const content = textNode.nodeValue;
                        const parent = textNode.parentNode;
                        if (!parent) return;

                        let lastIndex = 0;
                        const fragment = document.createDocumentFragment();
                        let match;
                        let found = false;
                        mapRegex.lastIndex = 0;
                        
                        while ((match = mapRegex.exec(content)) !== null) {
                            found = true;
                            fragment.appendChild(document.createTextNode(content.substring(lastIndex, match.index)));
                            
                            const matchedText = match[0];
                            const msgid = scanMap[matchedText];
                            
                            const span = document.createElement('span');
                            span.className = 'studio-editable';
                            span.dataset.msgid = msgid || matchedText;
                            span.innerText = matchedText;
                            fragment.appendChild(span);
                            lastIndex = mapRegex.lastIndex;
                        }
                        
                        if (found) {
                            fragment.appendChild(document.createTextNode(content.substring(lastIndex)));
                            parent.replaceChild(fragment, textNode);
                        }
                    });
                }
            }
        }

        // 3) Third Pass: Catch-all visible text wrapping (The "Aggressive" coverage requester by user)
        // This ensures that strings NOT in the PO file yet are still clickable.
        const walker3 = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, null, false);
        let anyNode;
        const finalPass = [];
        while(anyNode = walker3.nextNode()) {
            if (anyNode.nodeValue && anyNode.nodeValue.trim().length > 1) {
                if (isSafeToWrap(anyNode)) finalPass.push(anyNode);
            }
        }

        finalPass.forEach(textNode => {
            const parent = textNode.parentNode;
            if (!parent) return;
            const text = textNode.nodeValue;
            
            const span = document.createElement('span');
            span.className = 'studio-editable';
            // Use the text itself as a provisional msgid if no other is found
            span.dataset.msgid = text.trim();
            span.innerText = text;
            parent.replaceChild(span, textNode);
        });

        // 4) Final Pass: Element-level metadata for interactivity (Buttons, Links)
        const interactives = root.querySelectorAll('a, button, [role="button"], label, .nav-link, .btn');
        interactives.forEach(el => {
            if (el.closest('#studio-modal')) return;
            const text = (el.innerText || "").trim();
            if (text && scanMap && scanMap[text]) {
                // If it contains a single studio-editable child, mark the whole button as editable too
                // for easier clicking near edges/icons.
                el.classList.add('studio-clickable-container');
                if (!el.dataset.msgid) el.dataset.msgid = scanMap[text];
            }
        });

        // 5) Cleanup: Ensure no nested editables or duplicated visual labels
        try { dedupeStudioEditables(root); } catch(_) {}
    }

    /**
     * Prevent nesting and duplication of labels.
     * Guaranteed to only perform DOM node removal/replacement, never innerHTML.
     */
    function dedupeStudioEditables(root = document.body) {
        // 1) Remove nested editables (prefer outer ones for simple containers, inner for complex ones)
        // Generally, we want to avoid <span><span>Text</span></span>
        const all = Array.from(root.querySelectorAll('.studio-editable'));
        all.forEach(el => {
            let anc = el.parentElement;
            while (anc && anc !== document.documentElement) {
                if (anc.classList && anc.classList.contains('studio-editable')) {
                    // This is nested. Just unwrap the inner one by replacing with a text node.
                    const text = el.innerText || "";
                    const txtNode = document.createTextNode(text);
                    if (el.parentNode) el.parentNode.replaceChild(txtNode, el);
                    return;
                }
                anc = anc.parentElement;
            }
        });

        // 2) Multi-sibling deduplication: if an element has multiple .studio-editable children
        // with the exact same normalized text content, keep only the first one.
        const parents = new Set();
        Array.from(root.querySelectorAll('.studio-editable')).forEach(el => parents.add(el.parentNode));
        parents.forEach(parent => {
            if (!parent) return;
            const seen = new Set();
            const children = Array.from(parent.querySelectorAll(':scope > .studio-editable'));
            children.forEach(ch => {
                const txt = (ch.innerText || "").trim();
                if (!txt) return;
                if (seen.has(txt)) {
                    // Duplicate text content in the same container. Unwrap it.
                    const txtNode = document.createTextNode(ch.innerText);
                    parent.replaceChild(txtNode, ch);
                } else {
                    seen.add(txt);
                }
            });
        });
    }

    // Run initial scan
    scanAndWrap();

    // MutationObserver for infinite scroll / AJAX content
    const observer = new MutationObserver((mutations) => {
        for(const m of mutations) {
            for(const node of m.addedNodes) {
                if (node.nodeType === 1) scanAndWrap(node);
                else if (node.nodeType === 3 && node.parentNode) scanAndWrap(node.parentNode);
            }
        }
    });

    observer.observe(document.body, { childList: true, subtree: true });

})();
