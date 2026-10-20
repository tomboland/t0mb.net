// Exercise the delivered script with a minimal DOM fixture, without network access.
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');
function element(extra={}) { return {value:'', hidden:true, listeners:{}, addEventListener(k,f){this.listeners[k]=f;}, ...extra}; }
const rows=[
  element({textContent:'Alien Arrow 4K UHD',dataset:{label:'Arrow',format:'4K UHD, Blu-ray'}}),
  element({textContent:'Amélie DVD',dataset:{label:'',format:'DVD'}}),
  element({textContent:'Unknown release',dataset:{label:'',format:''}})
];
const elems={
 '#collection-table':{querySelectorAll:()=>rows},
 '#collection-search':element(), '#collection-format':element(),
 '#collection-label':element({add(){}}), '#collection-count':element(), '#collection-controls':element()
};
const location={href:'https://example.test/films/collection/'};
const context={URL,Option:function(t,v){this.text=t;this.value=v;},location,
 history:{replaceState(_s,_t,u){location.href=String(u);}},
 document:{querySelector:q=>elems[q]},window:{addEventListener(){}}};
vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../js/collection.js'),'utf8'),context);
assert.equal(elems['#collection-count'].textContent,'3 of 3 releases');
elems['#collection-search'].value='amelie';elems['#collection-search'].listeners.input();
assert.deepEqual(rows.map(r=>Boolean(r.hidden)),[true,false,true]);
assert.equal(new URL(location.href).searchParams.get('q'),'amelie');
elems['#collection-search'].value='';elems['#collection-format'].value='Blu-ray';elems['#collection-format'].listeners.change();
assert.deepEqual(rows.map(r=>Boolean(r.hidden)),[false,true,true]);
elems['#collection-label'].value='Other';elems['#collection-label'].listeners.change();
assert.equal(elems['#collection-count'].textContent,'0 of 3 releases');
console.log('Collection filters: accent folding, format, label, empty metadata and URL persistence passed');
