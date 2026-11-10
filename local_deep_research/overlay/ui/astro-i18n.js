/* Chinese UI presentation only. Never translate model output, user documents or input values. */
(() => {
    'use strict';
    const normalize = text => text.replace(/\s+/g, ' ').trim();
    const dictionary = window.AstroUiStrings || {};
    const patterns = new Map();
    const escape = text => text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    for (const [source, target] of Object.entries(dictionary)) {
        if (!source.includes('{{')) continue;
        const slots = [];
        const parts = source.split(/(\{\{\d+\}\})/g);
        const numeric = /^\{\{\d+\}\}/.test(source);
        const pageNumber = /^Page \{\{\d+\}\}/.test(source);
        const expression = parts.map(part => {
            if (/^\{\{\d+\}\}$/.test(part)) { const first = slots.length === 0; slots.push(part); return (numeric && first) || pageNumber ? String.raw`(\d+(?:[.,]\d+)?)` : '(.+?)'; }
            return escape(part);
        }).join('');
        // Match a fixed UI phrase before any variable; never match arbitrary prose.
        const prefix = source.split('{{')[0];
        if (!numeric && prefix.length < 4) continue;
        const bucket = numeric ? '@numeric' : prefix.slice(0, 4);
        const values = patterns.get(bucket) || [];
        values.push({regex: new RegExp('^' + expression + '$'), slots, target, length: prefix.length});
        patterns.set(bucket, values);
    }
    for (const values of patterns.values()) values.sort((a, b) => b.length - a.length);
    function t(text) {
        if (typeof text !== 'string' || !/[A-Za-z]/.test(text)) return text;
        const key = normalize(text);
        let translated = Object.prototype.hasOwnProperty.call(dictionary, key) ? dictionary[key] : undefined;
        if (!translated) {
            for (const entry of patterns.get(/^\d/.test(key) ? '@numeric' : key.slice(0, 4)) || []) {
                const match = key.match(entry.regex);
                if (match) {
                    const captured = new Map(entry.slots.map((slot, index) => [slot, match[index + 1]]));
                    translated = entry.target.replace(/\{\{\d+\}\}/g, slot => captured.get(slot) || slot);
                    break;
                }
            }
        }
        if (!translated || translated === key) return text;
        return text.match(/^\s*/)[0] + translated + text.match(/\s*$/)[0];
    }
    const contentSelector = [
        'script', 'style', 'noscript', 'pre', 'code', 'textarea', '[contenteditable="true"]',
        '[translate="no"]', '[data-astro-content]', '.notranslate',
        '#astro-report-toc', '#agent-thinking-content', '#results-content', '.ldr-results-content', '.ldr-markdown-content', '.markdown-content',
        '.ldr-chat-message-content', '#chat-title', '.ldr-chat-session-title',
        '#note-content-rendered', '#note-preview', '#ldr-ai-results-content',
        '#note-title-display', '.ldr-unified-result-title', '.ldr-unified-result-preview', '.ldr-synthesis-selected-item', '.ldr-note-card-title', '.ldr-note-card-preview', '.ldr-note-title',
        '.ldr-research-note-title', '.ldr-research-note-preview',
        '.ldr-document-title', '.ldr-doc-title', '.ldr-doc-authors', '.ldr-document-authors',
        '#ldr-document-text-content', '#text-viewer', '.ldr-chunk-text', '.ldr-chunk-content',
        '.ldr-document-abstract', '.ldr-abstract-text',
        '.ldr-history-item-title', '.ldr-history-item-snippet',
        '#result-query', '#research-query', '#current-query', '.ldr-query-text',
        '.ldr-collection-header h3', '#collection-name', '#collection-description', '.ldr-collection-name', '.ldr-collection-description',
        '.ldr-source-title', '.ldr-source-snippet', '.ldr-source-content',
        '.ldr-search-result-title', '.ldr-search-result-snippet',
        '.news-card-title', '.news-card-summary', '.ldr-news-card-title', '.ldr-news-card-summary', '.ldr-subscription-name', '.ldr-subscription-query', '.ldr-question-text', '.ldr-news-title', '.ldr-news-summary', '.ldr-log-message',
        '#model_dropdown', '#model-dropdown', '#model-options',
        '#filter-collection option[value]:not([value=""])', '#model option', 'select[data-key="llm.model"] option', 'select[name="llm.model"] option',
        '.ldr-user-info'
    ].join(',');
    const attributes = ['placeholder', 'title', 'aria-label', 'data-bs-title', 'data-original-title'];
    function protectedElement(element) {
        if (!element || element.closest(contentSelector)) return true;
        const anchor = element.closest('a[href]');
        // External source titles are data, including short titles such as "Settings".
        if (anchor && /^https?:/i.test(anchor.getAttribute('href')) &&
            !anchor.closest('.ldr-sidebar, .ldr-support-note, .ldr-community-note, .ldr-help-panel, .ldr-support-links, .ldr-input-help, .ldr-sqlcipher-link, #ldr-sources-grid')) return true;
        return false;
    }
    function translateAttributes(element) {
        // Input values are deliberately untouched. Placeholders/accessible labels are UI.
        if (element.matches('script,style,pre,code,[translate="no"],[data-astro-content]')) return;
        if (protectedElement(element) && !element.matches('input,textarea')) return;
        if (element.closest('[translate="no"],[data-astro-content]')) return;
        for (const name of attributes) {
            const value = element.getAttribute(name);
            if (value) {
                const translated = t(value);
                if (translated !== value) element.setAttribute(name, translated);
            }
        }
    }
    function translateNode(node) {
        if (node.nodeType === Node.TEXT_NODE) {
            if (!protectedElement(node.parentElement)) {
                const value = t(node.nodeValue);
                if (value !== node.nodeValue) node.nodeValue = value;
            }
            return;
        }
        if (node.nodeType !== Node.ELEMENT_NODE) return;
        translateAttributes(node);
        if (protectedElement(node)) return;
        const walker = document.createTreeWalker(node, NodeFilter.SHOW_ELEMENT | NodeFilter.SHOW_TEXT, {
            acceptNode(current) {
                if (current.nodeType === Node.ELEMENT_NODE) {
                    translateAttributes(current);
                    return protectedElement(current) ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_SKIP;
                }
                return NodeFilter.FILTER_ACCEPT;
            }
        });
        let text;
        while ((text = walker.nextNode())) {
            const translated = t(text.nodeValue);
            if (translated !== text.nodeValue) text.nodeValue = translated;
        }
    }
    window.AstroI18n = {t, translateNode};
    // Native dialogs retain synchronous behavior, return values and the user's default input.
    for (const name of ['alert', 'confirm', 'prompt']) {
        const native = window[name].bind(window);
        window[name] = (message, ...args) => native(t(message), ...args);
    }
    const chartLabels = new Set(['Input Tokens', 'Output Tokens', 'Total Tokens', 'Tokens', 'Cost', 'Total Cost', 'Duration', 'Research Count', 'Researches', 'Completed', 'Failed', 'In Progress', 'Pending', 'Success', 'Error']);
    let chartsInstalled = false;
    function installCharts() {
        if (chartsInstalled || !window.Chart?.register) return;
        chartsInstalled = true;
        const callbacks = new WeakSet();
        window.Chart.register({
            id: 'astro-chinese-ui',
            beforeUpdate(chart) {
                const options = chart.options;
                options.locale = 'zh-CN';
                for (const title of [options.plugins?.title, options.plugins?.subtitle, ...Object.values(options.scales || {}).map(scale => scale.title)]) {
                    if (title?.text) title.text = Array.isArray(title.text) ? title.text.map(t) : t(title.text);
                }
                for (const dataset of chart.data.datasets || []) {
                    if (chartLabels.has(dataset.label)) dataset.label = t(dataset.label);
                }
                // Model/provider labels are data. Only fixed status/token legend labels are UI.
                if (!/model|provider/i.test(chart.canvas.id) && chart.data.labels?.every(label => chartLabels.has(label))) {
                    chart.data.labels = chart.data.labels.map(t);
                }
                const tooltip = options.plugins?.tooltip?.callbacks;
                if (tooltip?.label && !callbacks.has(tooltip.label)) {
                    const original = tooltip.label;
                    const localized = function(...args) {
                        const result = original.apply(this, args);
                        return Array.isArray(result) ? result.map(t) : t(result);
                    };
                    callbacks.add(localized); tooltip.label = localized;
                }
            }
        });
        Object.values(window.Chart.instances || {}).forEach(chart => chart.update('none'));
    }
    const ready = () => {
        installCharts();
        if (document.readyState !== 'complete') document.addEventListener('DOMContentLoaded', installCharts, {once: true});
        document.documentElement.lang = 'zh-CN';
        document.title = t(document.title);
        translateNode(document.body);
        const pending = new Set();
        let scheduled = false;
        const flush = () => {
            scheduled = false;
            const nodes = Array.from(pending); pending.clear();
            nodes.forEach(node => { if (node.isConnected) translateNode(node); });
        };
        new MutationObserver(records => {
            for (const record of records) {
                if (record.type === 'childList') record.addedNodes.forEach(node => pending.add(node));
                else pending.add(record.target);
            }
            if (!scheduled && pending.size) { scheduled = true; queueMicrotask(flush); }
        }).observe(document.documentElement, {childList: true, subtree: true, characterData: true, attributes: true, attributeFilter: attributes});
    };
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', ready);
    else ready();
})();
