// Real app/dataset acceptance. APP_URL defaults to the isolated local integration server.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'C:/Users/Lenovo/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const base=process.env.APP_URL||'http://127.0.0.1:3001',output=process.env.ACCEPTANCE_OUTPUT||path.resolve(__dirname,'../../output/contact-acceptance');
const checks=[],errors=[],externalDuringMock=[];
const pass=(name,values={})=>{checks.push({name,...values});console.log('PASS',name,JSON.stringify(values));};
(async()=>{
 fs.mkdirSync(output,{recursive:true});
 const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});
 const context=await browser.newContext({viewport:{width:1440,height:1050}}),page=await context.newPage();
 page.setDefaultTimeout(45000);page.setDefaultNavigationTimeout(60000);
 let watchMock=false;
 page.on('pageerror',error=>errors.push(error.message));
 page.on('request',request=>{if(watchMock&&new URL(request.url()).origin!==new URL(base).origin)externalDuringMock.push(request.url());});
 try{
  await page.goto(base+'/chat',{waitUntil:'domcontentloaded'});
  await page.locator('.service-status.status-ready').waitFor();
  const composer=page.getByRole('textbox',{name:'جستجوی کالا یا پیام به راهنمای خرید'});
  async function say(text){await composer.fill(text);await page.getByRole('button',{name:'شروع جستجو',exact:true}).click();await page.waitForFunction(()=>location.pathname!='/chat'||!document.querySelector('textarea')?.disabled,undefined,{timeout:100000});}
  await say('هدفون می‌خوام');assert.equal(new URL(page.url()).pathname,'/chat');
  await say('برای گوش دادن به موسیقی');assert.equal(new URL(page.url()).pathname,'/chat');assert.match(await page.locator('.message-assistant').last().innerText(),/بودجه/);
  await say('تا ۵ میلیون تومان');assert.match(await page.locator('.message-assistant').last().innerText(),/خلاصه ترجیحات/);
  await say('بله');await page.waitForURL(url=>url.pathname==='/products',{timeout:100000});
  await page.getByTestId('product-results').waitFor();await page.locator('.catalog-map-pane .leaflet-container').waitFor();
  const gridBox=await page.locator('.catalog-products-pane').boundingBox(),mapBox=await page.locator('.catalog-map-pane').boundingBox();
  assert(gridBox&&mapBox);assert(gridBox.x+gridBox.width<=mapBox.x+2||mapBox.x+mapBox.width<=gridBox.x+2);
  const params=new URL(page.url()).searchParams;params.delete('page');params.delete('page_size');
  const grid=await(await page.request.get(base+'/api/products?'+params)).json(),map=await(await page.request.get(base+'/api/map/offers?'+params)).json();
  assert.equal(grid.total,map.product_count);assert(grid.total>24);
  pass('multi-turn consultation reaches simultaneous real products and map',{products:grid.total,shops:map.shop_count});
  await page.screenshot({path:path.join(output,'purchase-desktop.png'),fullPage:false,timeout:20000});
  const action=page.locator('.catalog-map-pane .map-shop-card .offer-contact-action').first();
  const chosenOffer=new URL(await action.getAttribute('href'),base).searchParams.get('offer_id');assert(chosenOffer);
  await action.click();await page.waitForURL(url=>url.pathname==='/contact');await page.getByTestId('contact-selection').waitFor();
  const original=await(await page.request.get(base+'/api/contact/selection?offer_id='+encodeURIComponent(chosenOffer))).json();
  assert.equal(await page.getByTestId('contact-selection').getAttribute('data-offer-id'),original.offer.id);
  assert.equal(await page.getByTestId('contact-selection').getAttribute('data-product-id'),original.product.id);
  assert.equal(await page.getByTestId('contact-selection').getAttribute('data-shop-id'),original.shop.id);
  const stored=await page.evaluate(()=>JSON.parse(localStorage.getItem('torob-in-person.workspace.v1')));
  assert.equal(stored.conversation.selectedOfferIds[0],original.offer.id);assert.equal(stored.conversation.selectedShopIds[0],original.shop.id);
  pass('exact dataset product shop and offer reach explicit contact preparation');
  assert.equal((await(await page.request.get(base+'/api/mock-calls')).json()).total,0);
  await page.reload({waitUntil:'domcontentloaded'});await page.getByTestId('contact-selection').waitFor();
  watchMock=true;
  const scenarios=['confirmed','price_changed','out_of_stock','needs_review','no_answer','alternative'],runs=[];
  for(const scenario of scenarios){
   if(runs.length){await page.getByRole('button',{name:'اجرای مجدد با سناریوی دیگر',exact:true}).click();await page.getByRole('combobox',{name:'سناریوی تماس Mock'}).waitFor();}
   await page.getByRole('combobox',{name:'سناریوی تماس Mock'}).selectOption(scenario);
   const changed=(original.offer.price||100000)+12345;
   if(scenario==='price_changed')await page.getByRole('textbox',{name:'قیمت جدید Mock'}).fill(String(changed));
   await page.getByRole('button',{name:'شروع شبیه‌سازی تماس',exact:true}).click();
   await page.waitForURL(url=>url.searchParams.has('run_id'));await page.getByTestId('mock-result').waitFor();
   const id=await page.getByTestId('mock-result').getAttribute('data-run-id');
   const result=await(await page.request.get(base+'/api/mock-calls/'+id)).json(),run=result.run;
   assert.equal(run.scenario,scenario);assert.equal(run.datasetOffer.id,original.offer.id);assert.equal(run.product.id,original.product.id);assert.equal(run.shop.id,original.shop.id);
   assert.equal(run.source,'simulated');assert.equal(run.provider,'mock');assert.equal(run.stages.length,6);assert(run.limitation);assert.equal(run.datasetOffer.stock,'unverified');
   if(scenario==='confirmed'){assert.equal(run.simulatedPrice,original.offer.price);assert.equal(run.simulatedInStock,true);assert.equal(run.priceDifference,0);}
   if(scenario==='price_changed'){assert.equal(run.simulatedPrice,changed);assert.equal(run.priceDifference,12345);}
   if(scenario==='out_of_stock'){assert.equal(run.simulatedInStock,false);assert.equal(run.simulatedPrice,null);}
   if(scenario==='needs_review'){assert.equal(run.status,'needs_review');assert.equal(run.simulatedInStock,null);}
   if(scenario==='no_answer'){assert.equal(run.status,'no_answer');assert.equal(run.simulatedInStock,null);assert.equal(run.simulatedPrice,null);}
   if(scenario==='alternative')for(const item of run.alternatives){const checked=await(await page.request.get(base+'/api/contact/selection?offer_id='+encodeURIComponent(item.offer.id))).json();assert.equal(checked.offer.productId,item.offer.productId);}
   assert.match(await page.getByTestId('mock-analysis').innerText(),/Mock|شبیه|سناریو/);runs.push(run);
   pass('Mock scenario '+scenario,{id});
  }
  await page.reload({waitUntil:'domcontentloaded'});await page.getByTestId('mock-result').waitFor();assert.equal(await page.getByTestId('mock-result').getAttribute('data-run-id'),runs.at(-1).id);
  await page.screenshot({path:path.join(output,'contact-desktop.png'),fullPage:true,timeout:20000});
  await page.getByRole('textbox',{name:'قیمت گزارش‌شده توسط کاربر'}).fill(String(original.offer.price+777));
  await page.getByRole('combobox',{name:'موجودی گزارش‌شده'}).selectOption('in_stock');
  await page.getByRole('combobox',{name:'روش تماس واقعی'}).selectOption('visit');
  const yesterday=new Date(Date.now()-86400000),local=new Date(yesterday.getTime()-yesterday.getTimezoneOffset()*60000).toISOString().slice(0,16);
  await page.getByLabel('زمان تماس واقعی',{exact:true}).fill(local);
  await page.getByRole('textbox',{name:'توضیحات گزارش کاربر'}).fill('گزارش آزمایشی پذیرش؛ تماس یا مراجعه واقعی انجام نشده است.');
  await page.getByRole('button',{name:'ثبت گزارش کاربر',exact:true}).click();await page.getByTestId('buyer-reports').locator('article').waitFor();
  const reports=await(await page.request.get(base+'/api/price-checks')).json();assert.equal(reports.checks.length,1);assert.equal(reports.checks[0].source,'buyer_report');assert.equal(reports.checks[0].inStock,true);assert(reports.checks[0].observedAt);assert.notEqual(reports.checks[0].observedAt,reports.checks[0].checkedAt);
  const after=await(await page.request.get(base+'/api/contact/selection?offer_id='+encodeURIComponent(chosenOffer))).json();assert.deepEqual(after.offer,original.offer);
  pass('buyer report stores source stock and actual observation time separately without changing dataset');
  await page.setViewportSize({width:390,height:844});await page.screenshot({path:path.join(output,'contact-mobile.png'),fullPage:true,timeout:20000});assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
  await page.getByRole('link',{name:'تاریخچه تماس‌های Mock',exact:true}).click();await page.getByTestId('mock-history').locator('article').nth(5).waitFor();
  assert.equal(await page.getByTestId('mock-history').locator('article').count(),6);await page.reload({waitUntil:'domcontentloaded'});await page.getByTestId('mock-history').locator('article').nth(5).waitFor();
  await page.getByRole('link',{name:'مشاهده گزارش و گفتگو',exact:true}).first().click();await page.getByTestId('mock-result').waitFor();
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
  pass('Mock history and selected result survive navigation refresh and mobile');
  const stranger=await browser.newContext(),privateRequest=stranger.request;
  assert.equal((await(await privateRequest.get(base+'/api/mock-calls')).json()).total,0);
  assert.equal((await privateRequest.get(base+'/api/mock-calls/'+runs[0].id)).status(),404);
  assert.equal((await(await privateRequest.get(base+'/api/price-checks')).json()).checks.length,0);await stranger.close();
  pass('other browser session cannot access Mock history or buyer reports');
  let failing=true;
  await page.route('**/api/mock-calls/*',route=>failing?route.fulfill({status:503,json:{detail:'خطای آزمایشی دریافت Mock'}}):route.continue());
  await page.reload({waitUntil:'domcontentloaded'});await page.getByRole('alert').filter({hasText:'خطای آزمایشی دریافت Mock'}).waitFor();failing=false;await page.getByRole('button',{name:'تلاش دوباره',exact:true}).click();await page.getByTestId('mock-result').waitFor();await page.unroute('**/api/mock-calls/*');
  pass('Mock retrieval error and retry recover saved result');
  await page.goto(base+'/contact?offer_id=does-not-exist',{waitUntil:'domcontentloaded'});await page.getByRole('alert').filter({hasText:'آفر در دیتاست پیدا نشد'}).waitFor();assert.equal(await page.getByTestId('mock-result').count(),0);
  pass('invalid dataset selection shows actionable error');
  assert.deepEqual(externalDuringMock,[]);assert.deepEqual(errors,[]);pass('no external request during Mock and no uncaught JavaScript errors');
 }catch(error){console.error(error.stack);process.exitCode=1;await page.screenshot({path:path.join(output,'contact-failure.png'),fullPage:true,timeout:10000}).catch(()=>{});fs.writeFileSync(path.join(output,'contact-failure.txt'),await page.locator('body').innerText().catch(()=>''));}
 finally{fs.writeFileSync(path.join(output,'purchase-contact-report.json'),JSON.stringify({checks,errors,externalDuringMock},null,2));await Promise.race([browser.close(),new Promise(resolve=>setTimeout(resolve,5000))]);process.exit(process.exitCode||0);}
})();
