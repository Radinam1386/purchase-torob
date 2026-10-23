// Run with node web/scripts/acceptance.cjs; PLAYWRIGHT_MODULE can point to a cached installation.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'C:/Users/Lenovo/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const origin = process.env.APP_URL || 'http://127.0.0.1:3000';
const output = path.resolve(__dirname, '../../output/acceptance');
const checks = [], errors = [];
const check = (name, extra = {}) => { checks.push({name, ...extra}); console.log('PASS', name, JSON.stringify(extra)); };
(async () => {
  fs.mkdirSync(output, {recursive:true});
  const browser = await chromium.launch({executablePath:process.env.CHROME_PATH || 'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});
  const page = await browser.newPage({viewport:{width:1440,height:1000}});
  page.on('pageerror', error => errors.push(error.message));
  try {
    await page.goto(origin + '/chat');
    await page.evaluate(() => localStorage.clear()); await page.reload();
    const composer = page.getByRole('textbox', {name:'جستجوی کالا یا پیام به راهنمای خرید'});
    async function say(message) {
      await composer.fill(message); await page.getByRole('button',{name:'شروع جستجو',exact:true}).click();
      await page.waitForFunction(() => !document.querySelector('textarea')?.disabled || location.pathname !== '/chat',undefined,{timeout:100000});
    }
    await say('هدفون می‌خوام');
    assert.equal(new URL(page.url()).pathname,'/chat');
    assert.match(await page.locator('.message-assistant').last().innerText(),/بودجه/);
    check('initial product request asks relevant questions');
    await say('برای گوش دادن به موسیقی');
    assert.equal(new URL(page.url()).pathname,'/chat');
    assert.match(await page.locator('.message-assistant').last().innerText(),/بودجه/);
    assert.equal(await page.locator('.product-tile').count(),0);
    check('usage without budget keeps consultation and does not search');
    await say('تا ۵ میلیون تومان');
    assert.equal(new URL(page.url()).pathname,'/chat');
    assert.match(await page.locator('.message-assistant').last().innerText(),/۵|5/);
    check('known preferences summarized before search');
    await page.screenshot({path:path.join(output,'chat-desktop.png'),fullPage:true});
    await say('بله');
    await page.waitForURL('**/products?**',{timeout:100000});
    await page.locator('[data-testid="product-results"]').waitFor({timeout:60000});
    const resultUrl = page.url();
    const query = new URL(resultUrl).searchParams;
    assert.equal(query.get('max_price'),'5000000');
    const saved = await page.evaluate(() => JSON.parse(localStorage.getItem('torob-in-person.workspace.v1')));
    assert.equal(saved.conversation.budget,5000000);
    assert.equal(saved.history.at(-2).content,'بله');
    async function verifyResults() {
      await page.locator('[data-testid="product-results"]').waitFor();
      const params = new URL(page.url()).searchParams; params.set('page_size','24');
      const response = await page.request.get(origin + '/api/products?' + params);
      assert(response.ok(), await response.text()); const data = await response.json();
      await page.waitForFunction(expected=>Number(document.querySelector('[data-testid="result-count"]')?.getAttribute('data-total'))===expected.total
        && JSON.stringify([...document.querySelectorAll('[data-product-id]')].map(element=>element.getAttribute('data-product-id')))===JSON.stringify(expected.ids),
        {total:data.total,ids:data.data.map(item=>item.id)});
      assert.equal(Number(await page.getByTestId('result-count').getAttribute('data-total')),data.total);
      assert.deepEqual(await page.locator('[data-product-id]').evaluateAll(elements=>elements.map(e=>e.dataset.productId)),data.data.map(item=>item.id));
      return data;
    }
    const initial = await verifyResults(); assert(initial.total>24);
    check('real search opens independent route with exact API count',{total:initial.total,page:initial.data.length});
    await page.reload(); await verifyResults(); check('results refresh preserves budget and query');
    await page.getByRole('checkbox').nth(0).check(); await page.getByRole('checkbox').nth(1).check();
    await page.getByRole('link',{name:'صفحه بعد',exact:true}).click();
    await page.waitForURL('**page=2**'); const second = await verifyResults();
    assert(!second.data.some(item=>item.id===initial.data[0].id));
    check('real pagination reaches additional products');
    await page.getByRole('link',{name:'مقایسه کالاها',exact:true}).click();
    await page.locator('.compare-products-grid article').nth(1).waitFor();
    assert.equal(await page.locator('.compare-products-grid article').count(),2);
    await page.reload(); await page.locator('.compare-products-grid article').nth(1).waitFor();
    check('comparison and refresh retain selected products');
    await page.goto(resultUrl); await verifyResults();
    await page.getByRole('combobox',{name:'مرتب‌سازی',exact:true}).selectOption('price_asc');
    await page.getByRole('button',{name:'اعمال فیلترها',exact:true}).click();
    await page.waitForURL('**sort=price_asc**'); const sorted = await verifyResults();
    const prices = sorted.data.map(item=>item.minPrice).filter(price=>price!==null);
    assert(prices.every((price,index)=>index===0||price>=prices[index-1]));
    check('price sorting changes actual API order');
    await page.getByRole('textbox',{name:'حداکثر قیمت',exact:true}).fill('1000000');
    await page.getByRole('button',{name:'اعمال فیلترها',exact:true}).click();
    await page.waitForURL('**max_price=1000000**'); const filtered=await verifyResults();
    assert(filtered.total<initial.total); assert(filtered.data.every(item=>item.minPrice<=1000000));
    check('budget filter changes actual results',{total:filtered.total});
    await page.screenshot({path:path.join(output,'results-desktop.png'),fullPage:true});
    await page.getByRole('link',{name:'بازگشت به چت',exact:true}).click();
    await composer.waitFor(); assert.match(await page.locator('.message-list').innerText(),/موسیقی/);
    assert.equal(await page.locator('.product-tile').count(),0);
    await page.waitForFunction(()=>JSON.parse(localStorage.getItem('torob-in-person.workspace.v1')).conversation.budget===1000000);
    check('return to chat restores conversation without inline product cards');
    await say('بودجه رو به ۲ میلیون تومان تغییر بده، همین الان جست‌وجو کن');
    await page.waitForURL(url=>url.pathname==='/products'&&url.searchParams.get('max_price')==='2000000',{timeout:100000});
    const revised=await verifyResults(); assert(revised.data.every(item=>item.minPrice<=2000000));
    check('later conversational budget correction updates actual results');
    await page.goto(origin+'/chat'); await composer.waitFor();
    await page.setViewportSize({width:390,height:844});
    await page.screenshot({path:path.join(output,'chat-mobile.png'),fullPage:true});
    assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
    await page.goto(resultUrl); await verifyResults();
    await page.screenshot({path:path.join(output,'results-mobile.png'),fullPage:true});
    assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
    check('chat and results fit mobile viewport');
    let failCatalog=true;
    await page.route('**/api/products?**',route=>failCatalog?route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({detail:'خطای آزمایشی اتصال'})}):route.continue());
    await page.reload(); await page.getByRole('alert').filter({hasText:'خطای آزمایشی اتصال'}).waitFor();
    failCatalog=false; await page.getByRole('button',{name:'تلاش دوباره',exact:true}).click(); await verifyResults();
    await page.unroute('**/api/products?**');
    check('results API error and retry recover');
    await page.goto(origin+'/products?q=NONEXISTENTZXQ654332');
    await page.getByText('محصولی با این فیلترها پیدا نشد.',{exact:true}).waitFor();
    check('empty results provide actionable recovery');
    const missingId=initial.data[0].id;
    await page.route(`**/api/products/${missingId}`,async route=>{
      const response=await route.fetch(); const body=await response.json();
      // Test-only removal of real fields; the production dataset is never changed.
      body.product.images=['/acceptance-missing-image.jpg']; body.product.specs={}; body.minPrice=null;
      await route.fulfill({json:body});
    });
    await page.goto(origin+'/products/'+missingId);
    await page.getByText('تصویر موجود نیست',{exact:true}).waitFor();
    assert.match(await page.locator('.detail-price').innerText(),/قیمت نامشخص/);
    await page.getByText('مشخصات ساختاریافته ثبت نشده است.',{exact:true}).waitFor();
    assert.equal(await page.evaluate(()=>JSON.parse(localStorage.getItem('torob-in-person.workspace.v1')).conversation.selectedProductId),missingId);
    check('broken image and absent price or specs have honest fallbacks');
    assert.deepEqual(errors,[]); check('no uncaught browser errors');
  } catch (error) {
    console.error(error.stack); await page.screenshot({path:path.join(output,'acceptance-failure.png'),fullPage:true});
    fs.writeFileSync(path.join(output,'acceptance-failure.txt'),await page.locator('body').innerText()); process.exitCode=1;
  } finally {
    fs.writeFileSync(path.join(output,'browser-results.json'),JSON.stringify({checks,errors},null,2));
    await Promise.race([browser.close(),new Promise(resolve=>setTimeout(resolve,5000))]);
    process.exit(process.exitCode || 0);
  }
})();
