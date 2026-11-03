const {test} = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');

async function fixture(initial=false) {
    const elements = new Map();
    const get = id => {
        if(!elements.has(id)) elements.set(id,{disabled:id==='presentation-mode',value:'',textContent:'',handlers:{},
            addEventListener(name,fn){this.handlers[name]=fn;}});
        return elements.get(id);
    };
    const requests=[];
    let failure=false;
    const location={href:'/'};
    const context=vm.createContext({document:{getElementById:get},window:{location},
        fetch:async(url,options)=>{
            requests.push({url,options});
            if(failure)throw new Error('Service unavailable.');
            if(url.endsWith('/access'))return {ok:true,json:async()=>({unlocked:initial})};
            const correct=JSON.parse(options.body).pin==='2020';
            return {ok:correct,json:async()=>correct?{unlocked:true}:{error:'Incorrect operator PIN.'}};
        }});
    vm.runInContext(fs.readFileSync('static/presentation-access.js','utf8'),context);
    await new Promise(resolve=>setImmediate(resolve));
    return {get,requests,location,fail(){failure=true;},submit:()=>get('presentation-unlock').handlers.submit({preventDefault(){}})};
}

test('locked Presentation Mode cannot navigate and wrong PIN stays locked',async()=>{
    const f=await fixture();
    assert.equal(f.get('presentation-mode').disabled,true);
    f.get('presentation-mode').handlers.click();
    assert.equal(f.location.href,'/');
    f.get('presentation-pin').value='wrong';
    await f.submit();
    assert.equal(f.get('presentation-mode').disabled,true);
    assert.equal(f.get('presentation-access-status').textContent,'Incorrect operator PIN.');
    assert.equal(f.get('presentation-pin').value,'');
});

test('successful server unlock enables the button without automatic navigation',async()=>{
    const f=await fixture();
    f.get('presentation-pin').value='2020';
    await f.submit();
    assert.equal(f.get('presentation-mode').disabled,false);
    assert.equal(f.location.href,'/');
    assert.equal(f.get('presentation-pin').value,'');
    assert.equal(f.requests[1].options.method,'POST');
    f.get('presentation-mode').handlers.click();
    assert.equal(f.location.href,'/presentation');
});

test('existing browser grant is restored and failed requests cannot unlock',async()=>{
    const allowed=await fixture(true);
    assert.equal(allowed.get('presentation-mode').disabled,false);
    const f=await fixture();f.fail();
    f.get('presentation-pin').value='2020';
    await f.submit();
    assert.equal(f.get('presentation-mode').disabled,true);
    assert.equal(f.get('presentation-unlock-button').disabled,false);
    assert.equal(f.get('presentation-access-status').textContent,'Service unavailable.');
});
