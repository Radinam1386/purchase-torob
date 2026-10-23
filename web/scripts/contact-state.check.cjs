const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const ts=require('../node_modules/typescript');
const saved=new Map([['torob-in-person.workspace.v1',JSON.stringify({conversation:{budget:5000000,selectedProductId:'old',selectedOfferIds:['old-offer'],selectedShopIds:['old-shop'],preferences:{searchProfile:{use:'موسیقی'},_advisor:{category:'هدفون'}}},history:[{role:'user',content:'هدفون میخوام'}]})]]);
const exported={};
vm.runInNewContext(ts.transpileModule(fs.readFileSync(path.resolve(__dirname,'../lib/contact.ts'),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}}).outputText,
 {exports:exported,process:{env:{}},window:{localStorage:{getItem:key=>saved.get(key)||null,setItem:(key,value)=>saved.set(key,value)}}});
exported.rememberContactSelection({product:{id:'p1',titleFa:'هدفون واقعی'},shop:{id:'s1'},offer:{id:'o1',productId:'p1',shopId:'s1',price:100}});
const result=JSON.parse(saved.get('torob-in-person.workspace.v1'));
assert.equal(result.conversation.budget,5000000);
assert.equal(result.conversation.selectedProductId,'p1');
assert.deepEqual(result.conversation.selectedShopIds,['s1']);assert.deepEqual(result.conversation.selectedOfferIds,['o1']);
assert.equal(result.conversation.preferences._advisor.status,'preparing_contact');
assert.equal(result.conversation.preferences.searchProfile.stage,'preparing_contact');
assert.equal(result.history[0].content,'هدفون میخوام');
exported.rememberContactStage('contact_result');
assert.equal(JSON.parse(saved.get('torob-in-person.workspace.v1')).conversation.preferences._advisor.status,'contact_result');
console.log('Offer selection, conversation continuity and contact stages passed');
