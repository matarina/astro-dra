// Isolated preview account only; report data is intercepted and no research is created.
const {chromium}=require('playwright');
const fs=require('node:fs');
const assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({headless:true,args:['--no-sandbox']});
 try{
  const context=await browser.newContext({viewport:{width:1440,height:1000},locale:'zh-CN'});context.setDefaultTimeout(20000);
  const page=await context.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
  const base=process.env.UI_BASE_URL||'http://127.0.0.1:15002';const user=JSON.parse(fs.readFileSync(process.env.UI_TEST_USER_FILE));const key='astro-sidebar-collapsed-'+user.username;
  await page.goto(base+'/auth/login');await page.locator('#username').fill(user.username);await page.locator('#password').fill(user.password);await page.locator('button[type=submit]').click();await page.locator('#query').waitFor();
  await page.evaluate(key=>localStorage.removeItem(key),key);await page.reload();
  const toggle=()=>page.locator('#astro-menu-toggle');const menu=()=>page.locator('#astro-sidebar');
  async function state(open){await page.waitForFunction(open=>document.querySelector('#astro-menu-toggle').getAttribute('aria-expanded')===String(open),open);assert.equal(await menu().evaluate(e=>e.inert),!open);assert.equal(await menu().isVisible(),open);if(open){assert.equal(await menu().evaluate(e=>getComputedStyle(e).opacity),'1');assert.notEqual(await menu().evaluate(e=>getComputedStyle(e).pointerEvents),'none')}}
  await state(true);const expandedWidth=await page.locator('#main-content').evaluate(e=>e.getBoundingClientRect().width);
  assert.equal(await menu().locator('.ldr-sidebar-links a,.ldr-sidebar-version-link').count(),0);assert.equal(await menu().locator('a[href*="discord"],a[href*="reddit"],a[href*="/issues"],a[href*="/releases/"]').count(),0);
  await toggle().click();await state(false);assert.equal(await page.evaluate(key=>localStorage.getItem(key),key),'true');assert((await page.locator('#main-content').evaluate(e=>e.getBoundingClientRect().width))>expandedWidth+200);assert(await page.locator('#astro-nav-scrim').evaluate(e=>e.hidden));
  if(process.env.UI_ARTIFACT_DIR)await page.screenshot({path:process.env.UI_ARTIFACT_DIR+'/sidebar-collapsed.png'});
  await page.reload();await state(false);await page.goto(base+'/history/');await state(false);
  await toggle().focus();await page.keyboard.press('Enter');await state(true);await page.locator('.ldr-sidebar-nav a[href="/"]').click();await page.locator('#query').waitFor();await state(true);
  await menu().locator('a').first().focus();await toggle().evaluate(e=>e.click());await state(false);assert.equal(await toggle().evaluate(e=>document.activeElement===e),true);
  await page.setViewportSize({width:390,height:844});await page.waitForTimeout(350);await state(false);await toggle().click();await state(true);assert(!(await page.locator('#astro-nav-scrim').evaluate(e=>e.hidden)));
  await page.keyboard.press('Escape');await state(false);assert.equal(await toggle().evaluate(e=>document.activeElement===e),true);
  await toggle().click();await state(true);await page.locator('#astro-nav-scrim').click({position:{x:380,y:300}});await state(false);
  await toggle().click();await state(true);await page.locator('#astro-menu-close').click();await state(false);assert.equal(await page.evaluate(key=>localStorage.getItem(key),key),'true');
  await toggle().click();await menu().locator('a[href="/history/"]').click();await page.waitForURL('**/history/');await state(false);assert(!await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth));
  await page.setViewportSize({width:1440,height:1000});await page.waitForTimeout(350);await state(false);
  await context.route('**/api/report/sidebar-preview',r=>r.fulfill({json:{content:'# Sidebar preview\n\n## Research\n\nSettings [1].\n\n[1] Synthetic UI fixture.',metadata:{query:'Sidebar preview',mode:'detailed'}}}));
  await page.goto(base+'/results/sidebar-preview');await page.locator('#results-content h1').waitFor();await state(false);
  const original=await page.locator('#results-content').innerText();await page.locator('#astro-reading-toggle').click();await page.waitForFunction(()=>document.body.classList.contains('astro-reading-mode'));await state(false);
  const center=await page.locator('#main-content').evaluate(e=>{const r=e.getBoundingClientRect();return Math.abs(r.left-(innerWidth-r.width)/2)});assert(center<2);
  await toggle().click();await state(true);assert(!await page.evaluate(()=>document.body.classList.contains('astro-reading-mode')));assert.equal(await page.locator('#results-content').innerText(),original);
  await page.goto(base+'/');await page.evaluate(key=>{localStorage.removeItem(key);localStorage.setItem('astro-sidebar-collapsed-unrelated-user','true')},key);await page.reload();await state(true);
  for(const width of [768,1024]){await page.setViewportSize({width,height:1000});await page.waitForTimeout(350);await state(true);assert(!await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),'tablet overflow '+width)}
  await page.setViewportSize({width:1440,height:1000});await page.waitForTimeout(350);
  if(process.env.UI_ARTIFACT_DIR)await page.screenshot({path:process.env.UI_ARTIFACT_DIR+'/sidebar-expanded.png'});
  assert.deepEqual(errors,[]);console.log(JSON.stringify({desktopToggle:true,persistence:true,keyboardFocus:true,mobileDrawer:true,resizePreference:true,readingMode:true,contentUnchanged:true,footerHidden:true,userScoped:true,pageErrors:errors}));
 }finally{await browser.close()}
})().catch(error=>{console.error(error.stack);process.exitCode=1});
