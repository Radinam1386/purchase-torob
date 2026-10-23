// Run: APP_URL=http://127.0.0.1:3003 node web/scripts/landing-chat.check.cjs
const assert=require('node:assert/strict');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'C:/Users/Lenovo/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const base=process.env.APP_URL||'http://127.0.0.1:3003',key='torob-in-person.workspace.v1';
(async()=>{
 const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});
 try{
  const context=await browser.newContext(),page=await context.newPage(),calls=[];
  await page.route('**/api/health',r=>r.fulfill({json:{databaseReady:true,llmConfigured:true}}));
  await page.route('**/api/chat/stream',r=>{
   calls.push(r.request().postDataJSON());
   const question='برای این محصول چه بودجه‌ای داری؟';
   return r.fulfill({contentType:'text/event-stream',body:'data: '+JSON.stringify({type:'response',response:{text:question,cards:[],clarificationQuestion:question}})+'\n\n'});
  });
  await page.goto(base);
  await page.evaluate(key=>{
   localStorage.setItem(key,JSON.stringify({userId:'old-user',conversation:{budget:7000000,radiusKm:4,filters:{installment:true,express:false,openNow:false},selectedProductId:'old-product',selectedShopIds:['old-shop'],selectedOfferIds:['old-offer'],preferences:{_advisor:{category:'جاروبرقی'}}},filters:{location:'مرکز تهران',budget:'7000000',radiusKm:4,installment:true,express:false,openNow:false},messages:[{id:'old',role:'user',content:'گفتگوی قبلی جاروبرقی'}],history:[{role:'user',content:'گفتگوی قبلی جاروبرقی'}]}));
   localStorage.setItem('torob-last-results-url','/products?q=جاروبرقی&max_price=7000000');
  },key);
  await page.locator('.hero-search input[name=q]').fill('یخچال');
  await page.locator('.hero-search button').click();
  await page.waitForURL(url=>url.pathname==='/chat');
  await page.waitForFunction(()=>!document.body.innerText.includes('گفتگوی قبلی جاروبرقی'),null,{timeout:7000});
  await page.locator('.message-assistant').filter({hasText:'چه بودجه‌ای داری؟'}).waitFor({timeout:10000});
  assert.equal(calls.length,1);assert.equal(calls[0].message,'یخچال');assert.deepEqual(calls[0].history,[]);
  assert.equal(calls[0].conversation.budget,null);assert.equal(calls[0].conversation.selectedProductId,null);
  assert.equal(calls[0].conversation.filters.installment,false);assert.deepEqual(calls[0].conversation.preferences,{});
  assert.equal(new URL(page.url()).search,'');
  await page.reload();await page.locator('.message-assistant').filter({hasText:'چه بودجه‌ای داری؟'}).waitFor();assert.equal(calls.length,1);
  await page.goto(base+'/chat');await page.locator('.message-user').filter({hasText:'یخچال'}).waitFor();assert.equal(calls.length,1);
  await page.goto(base);await page.locator('.idea-row a').filter({hasText:'هدفون'}).click();
  await page.locator('.message-user').filter({hasText:'هدفون'}).waitFor();await page.locator('.message-assistant').waitFor();
  assert.equal(calls.length,2);assert.equal(calls[1].message,'هدفون');assert.deepEqual(calls[1].history,[]);
  await page.evaluate(key=>{const saved=JSON.parse(localStorage.getItem(key));saved.conversation.budget=9000000;saved.filters.budget='9000000';saved.filters.installment=true;localStorage.setItem(key,JSON.stringify(saved));},key);
  await page.reload();await page.getByRole('button',{name:'گفتگوی جدید',exact:true}).click();
  await page.getByRole('textbox',{name:'جستجوی کالا یا پیام به راهنمای خرید'}).fill('لپ‌تاپ');
  await page.getByRole('button',{name:'شروع جستجو',exact:true}).click();
  await page.locator('.message-assistant').filter({hasText:'چه بودجه‌ای داری؟'}).waitFor();
  assert.equal(calls.length,3);assert.equal(calls[2].conversation.budget,null);assert.equal(calls[2].conversation.filters.installment,false);assert.deepEqual(calls[2].history,[]);
  console.log('PASS fresh landing chat, automatic send once, cleared old preferences, refresh, resume and suggestions');
 }finally{await Promise.race([browser.close(),new Promise(r=>setTimeout(r,5000))]);}
})().then(()=>process.exit(0)).catch(e=>{console.error(e);process.exit(1)});
