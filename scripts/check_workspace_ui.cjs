// Browser checks; all research submissions and report data below are intercepted fixtures.
const {chromium}=require('playwright');const fs=require('fs');const assert=require('node:assert/strict');
process.umask(0o077);
// Run only against an isolated preview with its own data volume and disposable account.
const root=process.env.UI_ARTIFACT_DIR;
const userFile=process.env.UI_TEST_USER_FILE;
const base=process.env.UI_BASE_URL || 'http://127.0.0.1:15002';
if (!root || !userFile) throw new Error('Set UI_ARTIFACT_DIR and UI_TEST_USER_FILE (private JSON: username/password)');
fs.mkdirSync(root,{recursive:true,mode:0o700});
(async()=>{const browser=await chromium.launch({headless:true,args:['--no-sandbox']});try{
const context=await browser.newContext({viewport:{width:1440,height:1000},locale:'zh-CN'});const page=await context.newPage();page.setDefaultTimeout(20000);const errors=[];page.on('pageerror',e=>errors.push(e.message));

await page.goto(base+'/auth/login');const user=JSON.parse(fs.readFileSync(userFile));await page.locator('#username').fill(user.username);await page.locator('#password').fill(user.password);await page.locator('button[type=submit]').click();await page.locator('#query').waitFor();await page.waitForTimeout(1400);
await page.evaluate(username=>{document.documentElement.dataset.theme='light';localStorage.setItem('ldr-theme-'+username,'light')},user.username);
const expectedModel=await page.locator('#model_hidden').inputValue();assert(expectedModel);
await page.locator('#query').fill('界面验证问题');await page.locator('[data-astro-template=methods]').click();assert((await page.locator('#query').inputValue()).startsWith('界面验证问题\n\n'));assert((await page.locator('#astro-query-count').textContent()).includes('字'));
await page.locator('label[for=mode-detailed]').click();assert(await page.locator('#mode-detailed').isChecked());
await page.evaluate(()=>window.scrollTo(0,0));await page.screenshot({path:root+'/ui-home-desktop.png'});
console.log(JSON.stringify({home:true,model:await page.locator('#astro-model-summary').textContent(),overflow:await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth)}));
await page.setViewportSize({width:390,height:844});await page.evaluate(()=>window.scrollTo(0,0));await page.screenshot({path:root+'/ui-home-mobile.png'});assert(!await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth));await page.locator('#astro-menu-toggle').click();assert.equal(await page.locator('#astro-menu-toggle').getAttribute('aria-expanded'),'true');await page.keyboard.press('Escape');assert.equal(await page.locator('#astro-menu-toggle').getAttribute('aria-expanded'),'false');
await page.setViewportSize({width:1440,height:1000});await page.evaluate(()=>document.documentElement.dataset.theme='hashed');await page.screenshot({path:root+'/ui-home-dark.png'});
let submitted;await context.route('**/api/start_research',async r=>{submitted=r.request().postDataJSON();await r.fulfill({json:{status:'error',message:'仅验证界面提交，未创建任务'}})});await Promise.all([page.waitForResponse('**/api/start_research'),page.locator('#start-research-btn').click()]);assert.equal(submitted.model,expectedModel);assert.equal(submitted.mode,'detailed');assert(submitted.query.startsWith('界面验证问题'));
const fixture={content:'# 界面测试报告\n\n以下为界面验证用的模拟内容，不是研究结果。\n\n## 一、主要发现\n\n这是测试段落，包含参考文献 [1]。\n\n| 方法 | 场景 |\n|---|---|\n| 示例方法 | 界面测试 |\n\n## 二、证据与局限\n\n此处仅用于验证阅读排版。\n\n### 后续方向\n\n保持原始报告内容。\n\n## 参考文献\n\n[1] 示例文献（模拟）。',metadata:{query:'界面测试报告',mode:'detailed',created_at:'2026-10-28T03:00:00'}};
await context.route('**/api/report/ui-preview',r=>r.fulfill({json:fixture}));
await page.goto(base+'/results/ui-preview');await page.locator('#results-content h1').waitFor();await page.waitForTimeout(1200);await page.evaluate(()=>document.documentElement.dataset.theme='light');
assert.equal(await page.locator('#astro-report-toc a').count(),5);assert.equal(await page.locator('#results-content table').count(),1);await page.screenshot({path:root+'/ui-report-desktop.png'});
const before=await page.locator('#results-content').innerText();await page.locator('#astro-reading-toggle').click();assert.equal(await page.locator('#astro-reading-toggle').getAttribute('aria-pressed'),'true');assert.equal(before,await page.locator('#results-content').innerText());await page.screenshot({path:root+'/ui-report-focus.png'});await page.locator('#astro-reading-toggle').click();
await page.locator('#export-dropdown-btn').click();assert(await page.locator('#export-markdown-btn').isVisible());await page.locator('#export-dropdown-btn').click();
await page.locator('.astro-report-more summary').click();assert(await page.locator('#back-to-history').isVisible());await page.locator('.astro-report-more summary').click();
await page.setViewportSize({width:390,height:844});await page.screenshot({path:root+'/ui-report-mobile.png'});assert(!await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth));
await page.goto(base+'/history/');await page.waitForTimeout(1000);await page.screenshot({path:root+'/ui-history-mobile.png'});assert(!await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth));
const auth=await browser.newPage({viewport:{width:1440,height:1000}});await auth.goto(base+'/auth/login');await auth.locator('.astro-password-toggle').click();assert.equal(await auth.locator('#password').getAttribute('type'),'text');await auth.screenshot({path:root+'/ui-login-desktop.png'});await auth.setViewportSize({width:390,height:844});await auth.screenshot({path:root+'/ui-login-mobile.png'});assert(!await auth.evaluate(()=>document.documentElement.scrollWidth>innerWidth));
await auth.goto(base+'/auth/register');assert(await auth.locator('[name=acknowledge]').isVisible());assert(await auth.locator('[name=acknowledge]').getAttribute('required')!==null);
console.log(JSON.stringify({report:true,mobile:true,auth:true,errors}));assert.deepEqual(errors,[]);
}finally{await browser.close()}})().catch(e=>{console.error(e.stack);process.exitCode=1});
