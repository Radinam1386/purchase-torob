const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const {chromium} = require('C:/Users/Lenovo/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const base = process.env.ACCEPTANCE_URL || 'http://127.0.0.1:3000';
const output = path.resolve(__dirname, '../../output/acceptance');
fs.mkdirSync(output,{recursive:true});
(async()=>{
 const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});
 const page=await browser.newPage({viewport:{width:1440,height:1050}});
 page.setDefaultTimeout(30000); page.setDefaultNavigationTimeout(45000); console.log('Map acceptance: browser ready');
 const errors=[];page.on('pageerror',e=>{errors.push(e.message);console.log(e.stack)});
 const query='product_ids=product_cd11d18cd252d39ecf2331f5&lat=35.7219&lng=51.4097&radius_km=30';
 const actual=await (await fetch('http://127.0.0.1:8000/api/map/offers?'+query)).json();
 assert(actual.shop_count>0);
 console.log('Map acceptance: real API loaded',actual.shop_count);
 await page.goto(base+'/map?'+query,{waitUntil:'domcontentloaded',timeout:90000});await page.locator('.map-shop-card').first().waitFor({timeout:90000});
 assert.equal(await page.locator('.map-shop-card').count(),actual.shop_count);
 await page.locator('.leaflet-container').waitFor();
 console.log('Map acceptance: Leaflet loaded');
 const firstShop=actual.results[0].shop.id;
 const card=page.locator(`[data-shop-id="${firstShop}"]`);
 const firstName=await card.locator('b').first().innerText();
 await card.locator('.map-shop-select').click();
 await page.waitForFunction(name=>document.querySelector('.leaflet-popup-content strong')?.textContent===name,firstName,{timeout:15000});
 assert.equal(await card.locator('.map-shop-select').getAttribute('aria-pressed'),'true');
 await page.waitForFunction(()=>document.querySelectorAll('.leaflet-tile-loaded').length>0 || !!document.querySelector('.map-tile-error'),undefined,{timeout:30000});
 await page.screenshot({path:path.join(output,'map-desktop.png'),timeout:15000});
 console.log('Map acceptance: selection and desktop passed');
 const loadedTiles=await page.locator('.leaflet-tile-loaded').count();
 const tileFailure=await page.locator('.map-tile-error').count();
 await page.reload({waitUntil:"domcontentloaded",timeout:90000});await page.locator('.map-shop-card').first().waitFor();
 assert.equal(await page.locator('.map-shop-card').count(),actual.shop_count);
 await page.getByRole('slider',{name:'شعاع جستجو'}).focus();await page.getByRole('slider').press('Home');
 await page.getByRole('button',{name:'اعمال محدوده',exact:true}).click();
 await page.getByText('فروشگاه مرتبطی در این محدوده و با فیلترهای فعلی پیدا نشد.',{exact:true}).waitFor({timeout:60000});
 assert(new URL(page.url()).searchParams.get('radius_km')==='0');
 const manyQuery='q='+encodeURIComponent('هدفون')+'&lat=35.7219&lng=51.4097&radius_km=4';
 const many=await(await fetch('http://127.0.0.1:8000/api/map/offers?'+manyQuery)).json();
 console.log('Map acceptance: multi-product API loaded',many.shop_count);
 await page.goto(base+'/map?'+manyQuery,{waitUntil:'domcontentloaded',timeout:90000});await page.locator('.map-shop-card').first().waitFor({timeout:60000});
 assert.equal(await page.locator('.map-shop-card').count(),Math.min(30,many.shop_count));
 let renderedOffers=await page.locator('.map-list-offer').count(); const nextShopPage=page.getByRole('button',{name:'صفحه بعد فروشگاه‌ها',exact:true});while(await nextShopPage.count() && await nextShopPage.isEnabled()){await nextShopPage.click();renderedOffers+=await page.locator('.map-list-offer').count();}assert.equal(renderedOffers,many.offer_count);
 assert(many.product_count>1);
 await page.locator('.leaflet-interactive').first().click({force:true});
 await page.locator('.leaflet-popup-content').waitFor();if(await page.getByRole('button',{name:'بزرگ‌نمایی این گروه'}).count()){await page.locator('.leaflet-popup-content button').nth(1).click();await page.locator('.map-shop-card.selected').waitFor();await page.locator('.map-popup-offer').first().waitFor();}
 const clusters=await page.locator('.leaflet-interactive[aria-label^="گروه"]').count();
 if(clusters) assert(await page.getByRole('button',{name:'بزرگ‌نمایی این گروه'}).count()>0 || await page.locator('.map-popup-offer').count()>0);
 await page.setViewportSize({width:390,height:844});await page.goto(base+'/map?'+query,{waitUntil:'domcontentloaded',timeout:90000});await page.locator('.map-shop-card').first().waitFor();
 const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>window.innerWidth+1);assert.equal(overflow,false);
 await page.screenshot({path:path.join(output,'map-mobile.png')});
 await page.goto(base+'/map?product_ids=product_cd11d18cd252d39ecf2331f5&lat=0&lng=0&radius_km=30',{waitUntil:'domcontentloaded'});
 await page.getByText('فروشگاه مرتبطی در این محدوده و با فیلترهای فعلی پیدا نشد.',{exact:true}).waitFor();
 await page.goto(base+'/map?q=',{waitUntil:'domcontentloaded'});
 await page.getByText('ابتدا در صفحه محصولات جستجو کن یا یک محصول را انتخاب کن.',{exact:true}).waitFor();
 const fixture=structuredClone(actual); fixture.results=fixture.results.slice(0,1);
 const unknown=structuredClone(fixture.results[0]);unknown.shop.id='acceptance-unlocated';unknown.shop.lat=null;unknown.shop.lng=null;unknown.distanceKm=null;unknown.offer.id='acceptance-missing-price';unknown.offer.price=null;
 fixture.results.push(unknown);fixture.shop_count=2;fixture.offer_count=2;fixture.product_count=1;fixture.missing_coordinates_count=1;
 await page.route('**/api/map/offers?**',route=>route.fulfill({json:fixture}));
 await page.route('**/*.tile.openstreetmap.org/**',route=>route.abort());
 await page.goto(base+'/map?'+query,{waitUntil:'domcontentloaded',timeout:90000});await page.locator('.map-shop-card').first().waitFor();
 assert.equal(await page.locator('.map-shop-card').count(),2);
 await page.locator('.leaflet-interactive').first().waitFor();assert.equal(await page.locator('.leaflet-interactive').count(),1);
 await page.getByRole('button',{name:'بدون مختصات',exact:true}).click();
 assert.equal(await page.locator('.map-shop-card').count(),1);
 assert.equal(await page.locator('.map-shop-card').getAttribute('data-shop-id'),'acceptance-unlocated');
 assert.match(await page.locator('.map-shop-card').innerText(),/قیمت نامشخص/);
 await page.locator('.map-tile-error').waitFor({timeout:15000});
 await page.screenshot({path:path.join(output,'map-missing-coordinates-error.png')});
 await page.unroute('**/api/map/offers?**');
 await page.route('**/api/map/offers?**',route=>route.fulfill({status:503,json:{detail:'خطای پذیرش آزمایشی'}}));
 await page.reload({waitUntil:"domcontentloaded",timeout:90000});await page.getByRole('button',{name:'تلاش دوباره',exact:true}).waitFor();
 await page.unroute('**/api/map/offers?**');await page.getByRole('button',{name:'تلاش دوباره',exact:true}).click();
 await page.locator('.map-shop-card').first().waitFor();
 const report={singleProduct:{shops:actual.shop_count,offers:actual.offer_count,products:actual.product_count},multiProduct:{shops:many.shop_count,offers:many.offer_count,products:many.product_count,renderedOffers,clusterMarkers:clusters},loadedTiles,tileFailure,desktop:true,mobile:true,horizontalOverflow:overflow,refresh:true,markerSelection:true,radiusChange:true,centerChange:true,unscopedSearchPrompt:true,missingCoordinates:true,missingPrice:true,tileError:true,apiErrorRetry:true,pageErrors:errors};
 assert.deepEqual(errors,[]);fs.writeFileSync(path.join(output,'map-report.json'),JSON.stringify(report,null,2));console.log(JSON.stringify(report));await Promise.race([browser.close(),new Promise(resolve=>setTimeout(resolve,5000))]);process.exit(0);
})().catch(e=>{console.error(e);process.exit(1)});









