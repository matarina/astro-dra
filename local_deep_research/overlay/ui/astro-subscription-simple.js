(() => {
    'use strict';
    function init() {
        const form = document.getElementById('astro-subscription-form');
        if (!form) return;
        const field = id => document.getElementById('simple-subscription-' + id);
        const folder = field('folder');
        fetch('/news/api/subscription/folders').then(response => response.json()).then(data => {
            const folders = Array.isArray(data) ? data : data.folders || [];
            folders.forEach(item => { const option = document.createElement('option'); option.value = item.id; option.textContent = item.name; folder.append(option); });
            folder.value = folder.dataset.initial || '';
        }).catch(() => { folder.disabled = true; });
        form.addEventListener('submit', async event => {
            event.preventDefault();
            const button = form.querySelector('button[type="submit"]');
            if (button.disabled) return;
            const error = field('error'); error.hidden = true; button.disabled = true;
            const id = form.dataset.id;
            const query = field('query').value.trim();
            const body = {name: field('name').value.trim() || query.slice(0,50),
                          is_active: field('active').checked};
            if (!folder.disabled) body.folder_id = folder.value || null;
            if (id) { body.query_or_topic = query; body.refresh_interval_minutes = Number(field('interval').value); }
            else { body.query = query; body.type = 'search'; body.refresh_minutes = Number(field('interval').value); }
            try {
                const response = await fetch('/api/news/subscriptions' + (id ? '/' + encodeURIComponent(id) : ''), {
                    method: id ? 'PUT' : 'POST', headers: {'Content-Type': 'application/json', 'X-CSRFToken': document.querySelector('meta[name="csrf-token"]').content},
                    body: JSON.stringify(body)
                });
                const result = await response.json();
                if (!response.ok) throw new Error(result.error || result.message || '保存失败，请稍后再试。');
                location.assign('/news/subscriptions');
            } catch (exception) { error.textContent = exception.message; error.hidden = false; button.disabled = false; }
        });
    }
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
