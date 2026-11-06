/* Progressive UI enhancements only. Research requests and source data stay with native components. */
(() => {
    'use strict';
    const ready = () => {
        const byId = id => document.getElementById(id);
        const page = document.querySelector('.ldr-page.active');
        const names = {'new-research': '新建研究', 'research-progress': '研究进度', 'research-results': '研究报告', history: '研究记录', 'chat-page': '对话研究'};
        const breadcrumb = byId('astro-page-label');
        if (breadcrumb && page) breadcrumb.textContent = names[page.id] || document.title.split(/ - | · /)[0];

        const menu = byId('astro-sidebar');
        const toggle = byId('astro-menu-toggle');
        const scrim = byId('astro-nav-scrim');
        const desktop = window.matchMedia('(min-width: 768px)');
        const userId = document.querySelector('meta[name="user-id"]')?.content || 'anonymous';
        const sidebarKey = 'astro-sidebar-collapsed-' + userId;
        let desktopCollapsed = document.documentElement.classList.contains('astro-sidebar-collapsed');
        let mobileOpen = false;
        const syncMenu = () => {
            if (!menu || !toggle || !scrim) return;
            const reading = document.body.classList.contains('astro-reading-mode');
            const open = !reading && (desktop.matches ? !desktopCollapsed : mobileOpen);
            document.documentElement.classList.toggle('astro-sidebar-collapsed', desktop.matches && desktopCollapsed);
            menu.classList.toggle('active', !desktop.matches && mobileOpen && !reading);
            menu.inert = !open;
            menu.setAttribute('aria-hidden', String(!open));
            toggle.setAttribute('aria-expanded', String(open));
            const label = open ? '收起侧边栏' : '展开侧边栏';
            toggle.setAttribute('aria-label', label); toggle.title = label;
            const icon = toggle.querySelector('i');
            if (icon) icon.className = 'fas ' + (desktop.matches ? (open ? 'fa-outdent' : 'fa-indent') : (open ? 'fa-times' : 'fa-bars'));
            const text = toggle.querySelector('.astro-menu-toggle-label');
            if (text) text.textContent = open ? '收起侧栏' : '展开侧栏';
            scrim.hidden = desktop.matches || !open;
        };
        const setMenu = (open, restoreFocus = false) => {
            const focusInside = menu?.contains(document.activeElement);
            if (desktop.matches) {
                desktopCollapsed = !open;
                try { localStorage.setItem(sidebarKey, String(desktopCollapsed)); } catch (_) { /* Optional preference. */ }
            } else mobileOpen = open;
            syncMenu();
            if (open && !desktop.matches) menu?.querySelector('a')?.focus();
            else if (restoreFocus || (!open && focusInside)) toggle?.focus();
        };
        toggle?.addEventListener('click', () => {
            if (document.body.classList.contains('astro-reading-mode')) {
                byId('astro-reading-toggle')?.click(); setMenu(true); return;
            }
            setMenu(!(desktop.matches ? !desktopCollapsed : mobileOpen));
        });
        byId('astro-menu-close')?.addEventListener('click', () => setMenu(false, true));
        scrim?.addEventListener('click', () => setMenu(false, true));
        menu?.addEventListener('click', event => { if (!desktop.matches && event.target.closest('a')) setMenu(false); });
        document.addEventListener('keydown', event => {
            if (event.key === 'Escape' && !desktop.matches && mobileOpen) {
                event.preventDefault(); event.stopImmediatePropagation(); setMenu(false, true);
            }
        }, true);
        desktop.addEventListener('change', () => { mobileOpen = false; syncMenu(); });
        window.addEventListener('storage', event => {
            if (event.key === sidebarKey) { desktopCollapsed = event.newValue === 'true'; syncMenu(); }
        });
        window.addEventListener('pageshow', event => {
            if (!event.persisted) return;
            try { desktopCollapsed = localStorage.getItem(sidebarKey) === 'true'; } catch (_) { /* Keep current preference. */ }
            mobileOpen = false; syncMenu();
        });
        syncMenu();

        const query = byId('query');
        const counter = byId('astro-query-count');
        const countQuery = () => { if (counter && query) counter.textContent = `${Array.from(query.value).length} 字`; };
        query?.addEventListener('input', countQuery);
        countQuery();
        const templates = {
            progress: '请整理【研究主题】近五年的主要研究进展，按主题归纳代表性研究、主要结论及参考文献。',
            methods: '请比较【方法或技术】的适用场景、分析流程、优势与局限，以表格归纳，并引用对应研究。',
            evidence: '请围绕【具体问题】梳理研究证据，区分研究对象、数据类型、分析方法和结论，并列出参考文献。'
        };
        document.querySelectorAll('[data-astro-template]').forEach(button => {
            button.title = '填入问题模板；已有内容会保留';
            button.addEventListener('click', () => {
                if (!query) return;
                const content = templates[button.dataset.astroTemplate];
                if (!content) return;
                query.value = query.value.trim() ? `${query.value}\n\n${content}` : content;
                query.dispatchEvent(new Event('input', {bubbles: true}));
                query.focus();
            });
        });
        const model = byId('model');
        const summary = byId('astro-model-summary');
        let providerChanged = false;
        const showModel = () => {
            if (!summary || !model) return;
            const current = model.value || (!providerChanged && model.dataset.initialValue) || '';
            summary.textContent = current || '请选择模型'; summary.title = current;
        };
        byId('model_provider')?.addEventListener('change', () => { providerChanged = true; setTimeout(showModel, 0); });
        model?.addEventListener('input', showModel);
        model?.addEventListener('change', showModel);
        if (model) new MutationObserver(showModel).observe(model, {attributes: true, attributeFilter: ['value']});
        showModel();
        byId('astro-open-config')?.addEventListener('click', () => {
            const button = byId('advanced-options-toggle');
            if (button?.getAttribute('aria-expanded') === 'false') button.click();
            button?.scrollIntoView({behavior: 'smooth', block: 'start'});
            button?.focus({preventScroll: true});
        });

        const reader = byId('astro-reading-toggle');
        reader?.addEventListener('click', () => {
            const active = document.body.classList.toggle('astro-reading-mode');
            reader.setAttribute('aria-pressed', String(active));
            reader.querySelector('span').textContent = active ? '退出专注' : '专注阅读';
            if (active) mobileOpen = false;
            syncMenu();
        });
        byId('astro-back-to-top')?.addEventListener('click', () => {
            document.querySelector('#research-results .ldr-page-header')?.scrollIntoView({behavior: 'smooth', block: 'start'});
        });
        const article = byId('results-content');
        const toc = byId('astro-report-toc');
        if (article && toc) {
            let observer;
            let scheduled;
            let lastHeadings = [];
            const update = () => {
                const headings = Array.from(article.querySelectorAll('h1,h2,h3')).filter(node => node.textContent.trim());
                if (headings.length === lastHeadings.length && headings.every((node, i) => node === lastHeadings[i] && node.textContent === lastHeadings[i].dataset.astroTocText)) return;
                lastHeadings = headings;
                observer?.disconnect();
                const fragment = document.createDocumentFragment();
                headings.forEach((heading, index) => {
                    if (!heading.id) {
                        let id = `astro-section-${index}`;
                        while (byId(id)) id += '-section';
                        heading.id = id;
                    }
                    heading.dataset.astroTocText = heading.textContent;
                    const anchor = document.createElement('a');
                    anchor.href = `#${encodeURIComponent(heading.id)}`;
                    anchor.dataset.level = heading.tagName.slice(1);
                    anchor.textContent = heading.textContent;
                    fragment.append(anchor);
                });
                if (!headings.length) { toc.textContent = '暂无可导航的章节'; return; }
                toc.replaceChildren(fragment);
                const links = Array.from(toc.querySelectorAll('a'));
                observer = new IntersectionObserver(entries => {
                    const visible = entries.filter(entry => entry.isIntersecting).sort((a,b) => a.boundingClientRect.top-b.boundingClientRect.top)[0];
                    if (!visible) return;
                    links.forEach((link, index) => {
                        if (headings[index] === visible.target) link.setAttribute('aria-current', 'location');
                        else link.removeAttribute('aria-current');
                    });
                }, {rootMargin: '-5% 0px -60% 0px', threshold: 0});
                headings.forEach(heading => observer.observe(heading));
            };
            new MutationObserver(() => { clearTimeout(scheduled); scheduled = setTimeout(update, 100); }).observe(article, {childList: true, subtree: true, characterData: true});
            update();
        }
        document.querySelectorAll('input[type="password"][autocomplete="current-password"]').forEach(input => {
            const wrapper = document.createElement('div');
            wrapper.className = 'astro-password-wrap';
            input.before(wrapper); wrapper.append(input);
            const button = document.createElement('button');
            button.type = 'button'; button.className = 'astro-password-toggle';
            button.setAttribute('aria-label', '显示密码'); button.setAttribute('aria-pressed', 'false');
            const icon = document.createElement('i'); icon.className = 'far fa-eye'; icon.setAttribute('aria-hidden', 'true');
            button.append(icon); wrapper.append(button);
            button.addEventListener('click', () => {
                const visible = input.type === 'password'; input.type = visible ? 'text' : 'password';
                button.setAttribute('aria-label', visible ? '隐藏密码' : '显示密码'); button.setAttribute('aria-pressed', String(visible));
                icon.className = visible ? 'far fa-eye-slash' : 'far fa-eye';
            });
        });
    };
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', ready);
    else ready();
})();
