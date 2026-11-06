// Isolated preview only: interface translation must not rewrite research or user data.
const {chromium}=require('playwright');
const fs=require('node:fs');
const assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({headless:true,args:['--no-sandbox']});
 try{
  const context=await browser.newContext({locale:'zh-CN',viewport:{width:1440,height:1000}});context.setDefaultTimeout(20000);
  const page=await context.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
  const base=process.env.UI_BASE_URL||'http://127.0.0.1:15002';const user=JSON.parse(fs.readFileSync(process.env.UI_TEST_USER_FILE));
  await page.goto(base+'/auth/login');await page.locator('#username').fill(user.username);await page.locator('#password').fill(user.password);await page.locator('button[type=submit]').click();await page.locator('#query').waitFor();await page.waitForFunction(()=>window.AstroI18n);
  const fixtures=await page.evaluate(async()=>{
   const host=document.createElement('section');host.id='locale-fixture';host.innerHTML=`
    <button id="locale-action" data-action="delete" type="button">Delete</button>
    <label id="locale-count">12 documents</label>
    <input id="locale-value" name="secret" value="Settings" placeholder="Search settings by name, description or category...">
    <select id="locale-select"><option value="in_progress">In Progress</option><option value="completed" selected>Completed</option></select>
    <select id="filter-collection"><option value="">All Collections</option><option value="user-defined">Settings</option></select>
    <div id="results-content" title="Settings"><h2>Research</h2><p>Settings</p><p>Delete</p><a href="#source-1">[1]</a></div>
    <div class="ldr-chat-message-content">Settings</div><div class="ldr-history-item-title">Delete</div>
    <div class="ldr-document-title" title="Delete">Research</div><div class="ldr-note-card-title">Library</div>
    <div class="ldr-collection-header"><h3>Settings</h3></div><div class="ldr-collection-description">Delete</div>
    <div class="ldr-unified-result-title">Settings</div><div class="ldr-log-message">Research</div>
    <pre>Settings</pre><div contenteditable="true">Delete</div><a href="https://example.org/paper">Research</a>`;
   document.body.append(host);const button=document.querySelector('#locale-action');let clicked=false;button.addEventListener('click',()=>{clicked=true});
   await new Promise(resolve=>setTimeout(resolve,150));button.click();
   const protectedTexts=Array.from(host.querySelectorAll('#results-content h2,#results-content p,.ldr-chat-message-content,.ldr-history-item-title,.ldr-document-title,.ldr-note-card-title,.ldr-collection-header h3,.ldr-collection-description,.ldr-unified-result-title,.ldr-log-message,pre,[contenteditable],a[href^="https"]'),node=>node.textContent);
   return{button:button.textContent,clicked,action:button.dataset.action,count:host.querySelector('#locale-count').textContent,value:host.querySelector('#locale-value').value,placeholder:host.querySelector('#locale-value').placeholder,selected:host.querySelector('#locale-select').value,selectedLabel:host.querySelector('#locale-select').selectedOptions[0].textContent,collection:host.querySelector('#filter-collection').options[1].textContent,protectedTexts,title:host.querySelector('#results-content').title,documentTitle:host.querySelector('.ldr-document-title').title};
  });
  assert.equal(fixtures.button,'删除');assert(fixtures.clicked);assert.equal(fixtures.action,'delete');assert.equal(fixtures.count,'12 篇文档');assert.equal(fixtures.value,'Settings');assert(/设置/.test(fixtures.placeholder));assert.equal(fixtures.selected,'completed');assert.equal(fixtures.selectedLabel,'已完成');assert.equal(fixtures.collection,'Settings');assert.equal(fixtures.title,'Settings');assert.equal(fixtures.documentTitle,'Delete');
  assert.deepEqual(fixtures.protectedTexts,['Research','Settings','Delete','Settings','Delete','Research','Library','Settings','Delete','Settings','Research','Settings','Delete','Research']);
  const chartState=await page.evaluate(()=>{
   const canvas=document.createElement('canvas');canvas.id='model-locale-fixture';document.body.append(canvas);
   const chart=new Chart(canvas,{type:'bar',data:{labels:['Settings','DeepSeek'],datasets:[{label:'Input Tokens',data:[1,2]}]},options:{animation:false,plugins:{title:{display:true,text:'Total Tokens'}}}});
   const result={labels:Array.from(chart.data.labels),values:Array.from(chart.data.datasets[0].data),dataset:chart.data.datasets[0].label,title:chart.options.plugins.title.text,locale:chart.options.locale};chart.destroy();canvas.remove();return result;
  });
  assert.deepEqual(chartState.labels,['Settings','DeepSeek']);assert.deepEqual(chartState.values,[1,2]);assert(/[\u3400-\u9fff]/.test(chartState.dataset));assert(/[\u3400-\u9fff]/.test(chartState.title));assert.equal(chartState.locale,'zh-CN');
  let dialogMessage;page.once('dialog',async dialog=>{dialogMessage=dialog.message();await dialog.dismiss()});assert.equal(await page.evaluate(()=>confirm('Delete')),false);assert.equal(dialogMessage,'删除');
  await page.evaluate(()=>document.querySelector('#locale-fixture').remove());
  for(const path of ['/library/','/library/collections','/library/download-manager','/notes/','/library/search/','/news/','/news/subscriptions','/metrics/','/benchmark/','/benchmark/results','/metrics/journals','/library/embedding-settings','/settings/']){
   const response=await page.goto(base+path);assert.equal(response.status(),200,path);await page.waitForTimeout(path.includes('settings')?1200:300);const heading=await page.locator('h1').first().innerText();assert(/[\u3400-\u9fff]/.test(heading),path+': '+heading);
  }
  await page.locator('#settings-search').fill('通知');await page.waitForTimeout(450);assert(/通知/.test(await page.locator('#settings-content').innerText()));await page.locator('#settings-search').fill('');
  await context.route('**/api/research/ui-l10n/status',r=>r.fulfill({json:{status:'in_progress',progress:42,query:'Settings',current_task:'Analyzing gathered information...'}}));
  await context.route('**/api/research/ui-l10n/logs*',r=>r.fulfill({json:{logs:[]}}));
  await page.goto(base+'/progress/ui-l10n');await page.waitForFunction(()=>document.querySelector('#current-task')?.textContent.includes('分析'));
  await page.locator('#log-panel-toggle').click();await page.waitForTimeout(400);
  await page.evaluate(()=>{const container=document.querySelector('#console-log-container');container.innerHTML='<div id="locale-info" class="ldr-console-log-entry" data-log-type="info"><span class="ldr-log-message">Research</span></div><div id="locale-error" class="ldr-console-log-entry" data-log-type="error"><span class="ldr-log-message">Settings</span></div>'});
  await page.locator('[data-filter-type=error]').click();assert.equal(await page.locator('#locale-info').evaluate(e=>e.style.display),'none');assert.notEqual(await page.locator('#locale-error').evaluate(e=>e.style.display),'none');await page.locator('[data-filter-type=all]').click();assert.notEqual(await page.locator('#locale-info').evaluate(e=>e.style.display),'none');assert.equal(await page.locator('#locale-info .ldr-log-message').innerText(),'Research');
  await page.goto(base+'/chat/');assert.equal(await page.locator('#chat-title').innerText(),'新建对话');
  await page.setViewportSize({width:390,height:844});await page.goto(base+'/');await page.waitForTimeout(400);assert(!await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth));
  assert.deepEqual(errors,[]);console.log(JSON.stringify({protectedContent:true,formValuesUnchanged:true,actions:true,numericPlaceholders:true,pages:13,chineseSettingsSearch:true,progressStatus:true,logFilters:true,charts:true,nativeDialogs:true,mobile:true,pageErrors:errors}));
 }finally{await browser.close()}
})().catch(error=>{console.error(error.stack);process.exitCode=1});
