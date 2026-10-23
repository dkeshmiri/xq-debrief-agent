const {test} = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');

const members = [
    {person_id:'a', display_name:'First', family_role:'Parent'},
    {person_id:'b', display_name:'Second', family_role:'Parent'},
    {person_id:'c', display_name:'Third', family_role:'Son'},
    {person_id:'d', display_name:'Fourth', family_role:'Daughter'},
    {person_id:'e', display_name:'Fifth', family_role:'Relative'}
];
function comparison(ids) {
    const people=ids.map(id=>members.find(p=>p.person_id===id));
    const scores={D:Object.fromEntries(ids.map((id,i)=>[id,70-i*10]))};
    return {members:people, assessments:{disc_natural:scores,disc_adapted:scores,
        driving_forces:scores,eq_dimensions:scores,eq_composites:scores}};
}
function fixture(roster = members, business = false) {
    const elements = new Map(), calls=[];
    function element() {
        return {value:'',textContent:'',hidden:false,disabled:false,children:[],handlers:{},
            setAttribute(){}, focus(){this.focused=true;},
            addEventListener(name,fn){this.handlers[name]=fn;},
            appendChild(child){this.children.push(child);if(!this.value)this.value=child.value;},
            replaceChildren(){this.children=[];this.value='';}};
    }
    const get=id=>{if(!elements.has(id))elements.set(id,element());return elements.get(id);};
    let handler=async (url,options)=>url==='/api/family' ? {family_name:'Example family', members:roster}
        : url==='/api/family/group/compare' ? {comparison:comparison(JSON.parse(options.body).person_ids)} : {answer:'A cautious answer.'};
    vm.runInNewContext(fs.readFileSync('static/family.js','utf8'), {
        document:{body:{dataset:business ? {experience:'business',apiBase:'/business'} : {}},getElementById:get,createElement:element}, AbortSignal,
        fetch:async(url,options)=>{
            calls.push([url,options]);
            const result=await handler(business ? url.replace(/^\/business/,'') : url,options);
            return {ok:result.ok!==false,json:async()=>result};
        }
    });
    return {get,calls,respond:fn=>handler=fn};
}
const settle=()=>new Promise(resolve=>setImmediate(resolve));
const submit=(f,id)=>f.get(id).handlers.submit({preventDefault(){}});
const inputs=f=>f.get('member-choices').children.map(label=>label.children[0]);
const toggle=(f,index,checked)=>{const input=inputs(f)[index];input.checked=checked;input.handlers.change();};

test('roster selects two distinct people and only uses family endpoints',async()=>{
    const f=fixture();await settle();
    assert.deepEqual(inputs(f).filter(input=>input.checked).map(input=>input.value),['a','b']);
    assert.equal(f.get('compare-button').disabled,false);
    assert.equal(f.get('family-ask-button').disabled,true);
    assert.deepEqual(f.calls.map(([url])=>url),['/api/family']);
});
test('fewer than two profiles and insufficient selection cannot be compared',async()=>{
    const empty=fixture([]);await settle();
    assert.equal(empty.get('pair-fields').disabled,true);
    assert.match(empty.get('family-status').textContent,/at least two/);
    const f=fixture();await settle();
    toggle(f,1,false);
    assert.equal(f.get('compare-button').disabled,true);
    submit(f,'compare-form');await settle();
    assert.equal(f.calls.length,1);
});
test('comparison shows factual tables and binds questions to the compared pair',async()=>{
    const f=fixture();await settle();
    submit(f,'compare-form');await settle();
    assert.equal(f.get('comparison-card').hidden,false);
    assert.equal(f.get('comparison-tables').children.length,5);
    assert.equal(f.get('comparison-title').focused,true);
    f.get('family-question').value='Compare our DISC';
    f.get('family-question').handlers.input();
    submit(f,'family-question-form');await settle();
    const [,options]=f.calls.find(([url])=>url==='/api/family/group/question');
    assert.deepEqual(JSON.parse(options.body),{person_ids:['a','b'],question:'Compare our DISC'});
    assert.equal(f.get('family-answer').textContent,'A cautious answer.');
    assert.equal(f.get('family-answer-card').hidden,false);
    assert.ok(f.calls.every(([url])=>url.startsWith('/api/family')));
});
test('changing either person clears the old comparison and answer',async()=>{
    const f=fixture();await settle();
    submit(f,'compare-form');await settle();
    f.get('family-question').value='Compare DISC';
    submit(f,'family-question-form');await settle();
    toggle(f,2,true);
    assert.equal(f.get('comparison-card').hidden,true);
    assert.equal(f.get('family-answer-card').hidden,true);
    assert.equal(f.get('family-question-card').hidden,true);
    assert.equal(f.get('family-question').value,'');
    assert.equal(f.get('family-ask-button').disabled,true);
});
test('failed reasoning preserves the comparison and prevents duplicate requests',async()=>{
    const f=fixture();await settle();
    submit(f,'compare-form');await settle();
    let finish;
    f.respond(async()=>new Promise(resolve=>finish=resolve));
    f.get('family-question').value='Compare DISC';
    submit(f,'family-question-form');
    submit(f,'family-question-form');
    assert.equal(f.get('pair-fields').disabled,true);
    finish({ok:false,error:'Try the question again.'});await settle();
    assert.equal(f.calls.filter(([url])=>url==='/api/family/group/question').length,1);
    assert.equal(f.get('comparison-card').hidden,false);
    assert.equal(f.get('family-answer-card').hidden,true);
    assert.equal(f.get('family-error').hidden,false);
    assert.equal(f.get('family-ask-button').disabled,false);
});

test('up to four selections produce five-column tables and fifth selection is disabled',async()=>{
    const f=fixture();await settle();
    toggle(f,2,true);toggle(f,3,true);
    assert.equal(inputs(f)[4].disabled,true);
    assert.equal(inputs(f)[3].disabled,false);
    assert.equal(f.get('selection-count').textContent,'4 of 4 members selected');
    submit(f,'compare-form');await settle();
    const request=f.calls.find(([url])=>url==='/api/family/group/compare');
    assert.deepEqual(JSON.parse(request[1].body).person_ids,['a','b','c','d']);
    const firstTable=f.get('comparison-tables').children[0].children[0];
    assert.equal(firstTable.children[1].children[0].children.length,5);
    assert.equal(firstTable.children[2].children[0].children.length,5);
    toggle(f,3,false);
    assert.equal(inputs(f)[4].disabled,false);
    assert.equal(f.get('comparison-card').hidden,true);
});
test('an over-limit selection cannot be submitted even if controls are bypassed',async()=>{
    const f=fixture();await settle();
    inputs(f).forEach(input=>{input.checked=true;});
    submit(f,'compare-form');await settle();
    assert.equal(f.calls.length,1);
});

test('business team workspace uses only business endpoints and workplace empty-state wording',async()=>{
    const f=fixture(members,true);await settle();
    toggle(f,2,true);toggle(f,3,true);
    submit(f,'compare-form');await settle();
    f.get('family-question').value='How can our team improve feedback?';
    submit(f,'family-question-form');await settle();
    assert.ok(f.calls.every(([url])=>url.startsWith('/business/api/')));
    assert.equal(f.get('family-status').textContent,'Your team comparison answer is ready.');
    const empty=fixture([],true);await settle();
    assert.match(empty.get('family-status').textContent,/workplace profiles/);
    assert.doesNotMatch(empty.get('family-status').textContent,/family/);
});
