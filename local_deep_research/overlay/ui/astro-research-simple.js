/* The standard user form submits the question and report format only. */
(() => {
    'use strict';
    function init() {
        const form = document.getElementById('research-form');
        if (!form) return;
        const query = document.getElementById('query');
        const button = document.getElementById('start-research-btn');
        const error = document.getElementById('research-error-alert');
        const radios = [...form.querySelectorAll('[name="research_mode"]')];
        function syncMode() {
            radios.forEach(radio => {
                const label = form.querySelector(`label[for="${radio.id}"]`);
                if (label) { label.classList.toggle('active', radio.checked); label.tabIndex = radio.checked ? 0 : -1; }
            });
        }
        radios.forEach(radio => radio.addEventListener('change', syncMode));
        form.querySelectorAll('.ldr-mode-option').forEach(label => label.addEventListener('keydown', event => {
            if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); label.click(); }
            if (['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(event.key)) {
                event.preventDefault();
                const selected = radios.findIndex(r => r.checked);
                const next = radios[(selected + (['ArrowLeft','ArrowUp'].includes(event.key) ? -1 : 1) + radios.length) % radios.length];
                next.checked = true; syncMode(); form.querySelector(`label[for="${next.id}"]`)?.focus();
            }
        }));
        query.addEventListener('keydown', event => {
            if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) { event.preventDefault(); form.requestSubmit(); }
        });
        form.addEventListener('submit', async event => {
            event.preventDefault();
            if (button.disabled) return;
            error.style.display = 'none';
            const text = query.value.trim();
            if (!text) { error.textContent = '请先输入研究问题。'; error.style.display = ''; query.focus(); return; }
            button.disabled = true;
            button.textContent = '正在开始研究…';
            const mode = radios.find(r => r.checked)?.value || 'quick';
            try {
                const response = await fetch(mode === 'chat' ? '/api/chat/sessions' : '/api/start_research', {
                    method: 'POST', credentials: 'same-origin',
                    headers: {'Content-Type': 'application/json', 'X-CSRFToken': document.querySelector('meta[name="csrf-token"]').content},
                    body: JSON.stringify(mode === 'chat' ? {initial_query: text} : {query: text, mode})
                });
                if (response.status === 401) throw new Error('登录状态已失效，请重新登录后再试。');
                const result = await response.json();
                if (!response.ok) throw new Error(result.message || result.error || '研究暂时无法启动，请稍后再试。');
                const id = mode === 'chat' ? result.session_id : result.research_id;
                if (!id || typeof id !== 'string') throw new Error(result.message || result.error || '未能创建研究，请稍后再试。');
                window.location.assign(mode === 'chat' ? `/chat/${encodeURIComponent(id)}?q=${encodeURIComponent(text)}` : `/progress/${encodeURIComponent(id)}`);
            } catch (exception) {
                error.textContent = exception.message || '连接失败，请稍后再试。'; error.style.display = '';
                button.disabled = false; button.textContent = '开始研究';
            }
        });
        syncMode();
    }
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
    else init();
})();
