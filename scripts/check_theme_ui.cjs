// Use only an isolated preview account. Theme persistence requests are intercepted.
const {chromium} = require('playwright');
const fs = require('node:fs');
const assert = require('node:assert/strict');
(async () => {
    const user = JSON.parse(fs.readFileSync(process.env.UI_TEST_USER_FILE));
    const base = process.env.UI_BASE_URL || 'http://127.0.0.1:15002';
    const browser = await chromium.launch({headless: true, args: ['--no-sandbox']});
    try {
        const context = await browser.newContext({colorScheme: 'light'});
        context.setDefaultTimeout(20000);
        let saved = 'sepia';
        await context.route('**/settings/api/app.theme', async route => {
            if (route.request().method() === 'PUT') saved = route.request().postDataJSON().value;
            await route.fulfill({json: {value: saved, status: 'success'}});
        });
        const page = await context.newPage();
        const errors = [];
        page.on('pageerror', error => errors.push(error.message));
        await page.goto(base + '/auth/login');
        await page.locator('#username').fill(user.username);
        await page.locator('#password').fill(user.password);
        await page.locator('button[type=submit]').click();
        await page.locator('#query').waitFor();
        await page.waitForFunction(() => window.themeService && document.querySelector('#theme-dropdown').options.length === 3);
        assert.deepEqual(await page.locator('#theme-dropdown option').allTextContents(), ['浅色', '深色', '跟随系统']);
        await page.waitForFunction(() => document.documentElement.dataset.theme === 'light');
        async function choose(value) {
            await Promise.all([page.waitForResponse(r => r.url().endsWith('/settings/api/app.theme') && r.request().method() === 'PUT'), page.selectOption('#theme-dropdown', value)]);
            assert.equal(saved, value);
        }
        await choose('hashed');
        assert.equal(await page.getAttribute('html', 'data-theme'), 'hashed');
        await page.emulateMedia({colorScheme: 'light'});
        assert.equal(await page.getAttribute('html', 'data-theme'), 'hashed');
        await choose('system');
        await page.waitForFunction(() => document.documentElement.dataset.theme === 'light');
        await page.emulateMedia({colorScheme: 'dark'});
        await page.waitForFunction(() => document.documentElement.dataset.theme === 'hashed');
        await page.reload();
        await page.waitForFunction(() => window.themeService && document.querySelector('#theme-dropdown').value === 'system');
        assert.equal(await page.getAttribute('html', 'data-theme'), 'hashed');
        await choose('light');
        await page.emulateMedia({colorScheme: 'dark'});
        assert.equal(await page.getAttribute('html', 'data-theme'), 'light');
        // A legacy server-side theme and stale local value must not restore hidden palettes.
        saved = 'dracula';
        await page.evaluate(username => localStorage.setItem('ldr-theme-' + username, 'nord'), user.username);
        await page.reload();
        await page.waitForFunction(() => window.themeService && document.querySelector('#theme-dropdown').value === 'system');
        assert.equal(await page.getAttribute('html', 'data-theme'), 'hashed');
        await page.goto(base + '/settings/');
        await page.waitForFunction(() => window.themeService);
        // Native settings may insert the appearance select after initialization.
        await page.evaluate(() => {
            const select = document.createElement('select');
            select.id = 'theme-select';
            select.innerHTML = '<option value="nord">Nord</option>';
            document.body.append(select);
        });
        await page.waitForFunction(() => document.querySelector('#theme-select').options.length === 3);
        assert.deepEqual(await page.locator('#theme-select option').allTextContents(), ['浅色', '深色', '跟随系统']);
        assert.deepEqual(errors, []);
        console.log(JSON.stringify({options: 3, explicitModes: true, systemChanges: true, reload: true, legacyPreference: true, dynamicSettings: true, pageErrors: errors}));
    } finally {
        await browser.close();
    }
})().catch(error => {console.error(error.message); process.exitCode = 1;});
