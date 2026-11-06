// Isolated preview only: registers disposable users and exercises root approval.
const {chromium}=require('playwright');
const fs=require('fs'); const assert=require('assert');
process.umask(0o077);
const dir=process.env.UI_ARTIFACT_DIR;
if (!dir || !process.env.UI_ROOT_USER_FILE) throw new Error('Set private UI_ARTIFACT_DIR and UI_ROOT_USER_FILE; isolated preview only');
fs.mkdirSync(dir,{recursive:true,mode:0o700});
const root=JSON.parse(fs.readFileSync(process.env.UI_ROOT_USER_FILE,'utf8')); const base=process.env.UI_BASE_URL || 'http://127.0.0.1:15002';
(async()=>{
const browser=await chromium.launch({headless:true,args:['--no-sandbox']});
const contexts=[];const errors=[];const forbidden=[];
async function page(){const c=await browser.newContext({viewport:{width:1440,height:1000}});contexts.push(c);const p=await c.newPage();p.on('pageerror',e=>errors.push(e.message));p.on('response',r=>{if(r.status()>=400)forbidden.push({status:r.status(),path:new URL(r.url()).pathname});});return p;}
async function login(p,creds){await p.goto(base+'/auth/login');await p.fill('#username',creds.username);await p.fill('#password',creds.password);await p.check('#remember');await Promise.all([p.waitForURL(base+'/'),p.click('button[type=submit]')]);await p.waitForSelector('#query');}
async function register(p,name,type){await p.goto(base+'/auth/register');await p.selectOption('#account_type',type);await p.fill('#username',name);await p.fill('#password',root.password);await p.fill('#confirm_password',root.password);await p.check('#acknowledge');await Promise.all([p.waitForURL(base+'/'),p.click('button[type=submit]')]);await p.waitForSelector('#query');}
async function api(p,path,method='GET',body){return await p.evaluate(async({path,method,body})=>{const headers={'X-CSRFToken':document.querySelector('meta[name=csrf-token]')?.content};if(body)headers['Content-Type']='application/json';const r=await fetch(path,{method,headers,body:body?JSON.stringify(body):undefined});const t=await r.text();let data;try{data=JSON.parse(t)}catch{}return {status:r.status,data,containsSecret:t.includes('isolated-test-only')};},{path,method,body});}
const stamp=Date.now(); const userName='test_user_'+stamp, applicantName='test_admin_'+stamp;
try {
const u=await page();await register(u,userName,'user');
assert.equal(await u.locator('#model_provider').count(),0);assert.equal(await u.locator('#policy_egress_scope').count(),0);
assert.equal(await u.locator('#sidebar-settings-label').count(),0);assert.equal(await u.locator('#sidebar-analytics-label').count(),0);
assert.equal(await u.locator('#astro-sidebar nav a').count(),11);
for (const path of ['/settings/','/settings','/metrics/','/benchmark/','/library/embedding-settings','/admin/accounts','/settings/api','/research/api/settings/current-config','/settings/api/llm.openai_endpoint.api_key','/settings/api/bulk?keys[]=llm.model']) {
 const r=await api(u,path);assert.equal(r.status,403,'ordinary must not access '+path+' got '+r.status);assert(!r.containsSecret);
}
for (const path of ['/chat/','/history/','/library/','/library/collections','/library/download-manager','/notes/','/library/search/','/library/zotero','/news/','/news/subscriptions']) {
 const r=await api(u,path);assert.equal(r.status,200,'ordinary page '+path+' got '+r.status);
}
for (const body of [{query:'test',model:'forged'},{query:'test',metadata:{settings_snapshot:{'llm.model':'forged'}}},{query:'test',policy_egress_scope:'unprotected'}]) assert.equal((await api(u,'/api/start_research','POST',body)).status,403);
assert.equal((await api(u,'/settings/api/llm.model','PUT',{value:'forged'})).status,403);
assert.equal((await api(u,'/settings/api/app.theme','PUT',{value:'light'})).status,200);
assert.equal((await api(u,'/settings/save_all_settings','POST',{'zotero.import_annotations':true})).status,200);
assert.equal((await api(u,'/settings/save_all_settings','POST',{'zotero.import_annotations':true,'llm.model':'forged'})).status,403);
const a=await page();await register(a,applicantName,'admin');assert.equal((await api(a,'/account/access')).data.role,'user');assert.equal((await api(a,'/account/access')).data.review_state,'pending');
const r=await page();await login(r,root);await r.goto(base+'/admin/accounts');
const row=r.locator('tr[data-account="'+applicantName+'"]');const href=await row.locator('form').first().getAttribute('action');
const target=href.split('/')[3];assert.equal((await api(a,href,'POST',{})).status,403);
assert.equal(await r.evaluate(async path=>(await fetch(path,{method:'POST'})).status,href),400);
await row.getByRole('button',{name:'批准',exact:true}).click();await r.waitForURL(base+'/admin/accounts');
await a.reload();assert.equal((await api(a,'/account/access')).data.role,'admin');assert.equal(await a.locator('#model_provider').count(),1);assert.equal((await api(a,'/settings/api')).status,200);assert.equal((await api(a,'/admin/accounts')).status,403);
assert.equal((await api(r,'/admin/accounts/'+target+'/revoke','POST',{})).status,200);
await a.reload();assert.equal((await api(a,'/account/access')).data.role,'user');assert.equal(await a.locator('#model_provider').count(),0);
await u.goto(base+'/news/subscriptions/new');assert.equal(await u.locator('#subscription-provider').count(),0);
await u.fill('#simple-subscription-query','A general subscription fixture');await u.uncheck('#simple-subscription-active');
await Promise.all([u.waitForURL(base+'/news/subscriptions'),u.click('#astro-subscription-form button[type=submit]')]);
assert.equal((await api(u,'/api/news/subscriptions','POST',{query:'forged',model:'forged',is_active:false})).status,403);
assert.equal((await api(u,'/news/api/subscribe','POST',{query:'forged',model:'forged',is_active:false})).status,403);
await u.goto(base+'/');
let submitted;await u.route('**/api/start_research',async route=>{submitted=route.request().postDataJSON();await route.fulfill({status:400,contentType:'application/json',body:JSON.stringify({message:'测试提交已捕获'})});});
await u.fill('#query','测试通用研究问题');await u.click('#start-research-btn');await u.getByText('测试提交已捕获',{exact:true}).waitFor();assert.deepEqual(submitted,{query:'测试通用研究问题',mode:'quick'});assert(!await u.locator('#start-research-btn').isDisabled());
await u.setViewportSize({width:390,height:844});await u.locator('.ldr-mobile-nav-tab[data-tab-id=more]').click();assert.equal(await u.locator('.ldr-mobile-sheet-item[data-item-id=settings]').count(),0);assert.equal(await u.locator('.ldr-mobile-sheet-item[data-item-id=metrics]').count(),0);assert(await u.locator('.ldr-mobile-sheet-item[data-item-id=zotero]').count());
await u.screenshot({path:dir+'/ordinary-mobile.png',fullPage:true});
await r.screenshot({path:dir+'/root-accounts.png',fullPage:true});
await u.setViewportSize({width:1440,height:1000});await u.goto(base+'/');await u.screenshot({path:dir+'/ordinary-home.png',fullPage:true});
const navPaths=await u.locator('#astro-sidebar nav a').evaluateAll(items=>items.map(item=>new URL(item.href).pathname));
for (const path of navPaths) { await u.goto(base+path);await u.waitForTimeout(450); }
assert.deepEqual(errors,[],'browser errors');
fs.writeFileSync(dir+'/test-users.json',JSON.stringify({user:{username:userName,password:root.password},applicant:{username:applicantName,password:root.password}}),{mode:0o600});
fs.writeFileSync(dir+'/browser-result.json',JSON.stringify({passed:true,errors,requestObservations:forbidden,ordinaryNavigationCount:11,approvalAndRevocation:true,csrfEnforced:true,formPayload:submitted},null,2));
console.log(JSON.stringify({passed:true,browserErrors:errors.length,ordinaryNavigationCount:11,approvalAndRevocation:true,csrfEnforced:true}));
}finally{await browser.close();}
})().catch(e=>{console.error(e.stack);process.exitCode=1;});
