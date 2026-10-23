// Run from web: node app/products/search-state.check.cjs
const assert = require('node:assert/strict');
const fs = require('node:fs');
const ts = require('typescript');
const path = require('node:path');
const vm = require('node:vm');
const filename = path.resolve(__dirname, '../../lib/search-state.ts');
const code = ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
}).outputText;
const exportsObject = {};
vm.runInNewContext(code, { exports: exportsObject, URLSearchParams, Number });
const { readSearchState, searchParams, resultsUrl } = exportsObject;
const input = new URLSearchParams('q=هدفون&label=موسیقی&max_price=3000000&min_price=1000000&brand=sony&category=هدفون&sort=price_asc&page=3&lat=35.7&radius_km=4');
const state = readSearchState(input);
assert.equal(state.page, 3);
assert.equal(state.maxPrice, 3000000);
const output = searchParams(state);
assert.equal(output.get('q'), 'هدفون');
assert.equal(output.get('brand'), 'sony');
assert.equal(output.get('category'), 'هدفون');
assert.equal(output.get('sort'), 'price_asc');
assert.equal(output.get('page'), '3');
assert.equal(output.get('radius_km'), '4', 'geographic filters must survive navigation');
assert.equal(readSearchState(new URLSearchParams('page=-4&max_price=nope&sort=invalid')).page, 1);
assert.equal(readSearchState(new URLSearchParams('page=Infinity')).page, 1);
assert.equal(readSearchState(new URLSearchParams('max_price=-1')).maxPrice, null);
assert.equal(resultsUrl(state).startsWith('/products?'), true);
console.log('Search URL round-trip, pagination validation, and geographic context passed.');
