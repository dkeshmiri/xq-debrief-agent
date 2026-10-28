const {test} = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');

function fixture() {
    function element() {
        return {children:[], textContent:'', value:'', dataset:{}, style:{}, handlers:{},
            classList:{add(){},toggle(){}}, setAttribute(){}, removeAttribute(){},
            append(...items){this.children.push(...items);}, appendChild(item){this.children.push(item);},
            replaceChildren(){this.children=[];}, addEventListener(name, fn){this.handlers[name]=fn;}};
    }
    const elements = new Map();
    const get = id => {if (!elements.has(id)) elements.set(id, element()); return elements.get(id);};
    const context = vm.createContext({document:{getElementById:get, createElement:element, querySelectorAll:()=>[]},
        window:{addEventListener(){}}, fetch:()=>new Promise(()=>{}), AbortSignal, setTimeout(){}});
    vm.runInContext(fs.readFileSync('static/presentation.js', 'utf8'), context);
    return {get, run:code=>vm.runInContext(code, context)};
}
const state = {active:false, connected:false, busy:false, index:0, completed:false,
    chapters:[{title:'Overview',text:'Welcome',visual:'overview'}, {title:'Scores',text:'Results',visual:'scores'}],
    visuals:{overview:{title:'Overview',note:'Context',cards:[]},scores:{title:'Scores',note:'Reported',rows:[
        {label:'Force',series:[{label:'Zero',value:0,color:'force'}, {label:'Unknown',value:null,color:'force'}]}]}},
    word_count:2, remaining_seconds:900, revision:0, source:'Recorded'};

test('preview follows chapter selection, distinguishes zero from missing, and live chapter takes over',()=>{
    const f=fixture(); f.run(`render(${JSON.stringify(state)})`);
    f.get('preview-chapter').value='1'; f.get('preview-chapter').handlers.change();
    const chart=f.get('chapter-visual');
    assert.equal(chart.children[0].textContent,'Scores');
    const group=chart.children[3];
    assert.equal(group.children[1].children[1].textContent,'0');
    assert.equal(group.children[2].children[1].textContent,'Not reported');
    assert.equal(group.children[1].children[2].children[0].style.width,'0%');
    f.run(`render(${JSON.stringify({...state,active:true,index:0})})`);
    assert.equal(f.get('chapter-visual').children[0].textContent,'Overview');
    assert.equal(f.get('preview-chapter').disabled,true);
    assert.equal(f.get('profile-upload').disabled,true);
});

test('changing source replaces script and charts without duplicate chapters',()=>{
    const f=fixture(); f.run(`render(${JSON.stringify(state)})`);
    const updated={...state,revision:1,chapters:[{title:'New profile',text:'New speech',visual:'overview'}]};
    f.run(`render(${JSON.stringify(updated)})`);
    assert.equal(f.get('chapters').children.length,1);
    assert.equal(f.get('full-script').children.length,2);
    assert.equal(f.get('script').textContent,'New speech');
});

test('showcase switches layout without replacing the existing player or changing playback state',()=>{
    const f=fixture(); f.run(`render(${JSON.stringify({...state,active:true})})`);
    f.run('frame={sentinel:true}; joined=true;');
    const player=f.get('video-container');
    f.get('showcase-toggle').handlers.click();
    assert.equal(f.get('showcase-toggle').textContent,'Return to split view');
    assert.equal(f.run('frame.sentinel && joined && state.active'),true);
    assert.equal(f.get('video-container'),player);
    f.get('showcase-toggle').handlers.click();
    assert.equal(f.get('showcase-toggle').textContent,'Showcase view');
});

test('DISC plots keep all four exact scores and show missing as a dash',()=>{
    const f=fixture();
    f.run(`renderVisual(${JSON.stringify({kind:'disc',title:'DISC',note:'Scores',focus:['D','I'],profiles:[
        {label:'Natural',scores:[{key:'D',label:'Dominance',value:93},{key:'I',label:'Influence',value:72},
        {key:'S',label:'Steadiness',value:0},{key:'C',label:'Compliance',value:null}]}]})})`);
    const grid=f.get('chapter-visual').children[2].children[0].children[1];
    assert.equal(grid.children.length,5);
    assert.equal(grid.children[1].children[1].children[0].style.height,'93%');
    assert.equal(grid.children[3].children[0].textContent,'0');
    assert.equal(grid.children[4].children[0].textContent,'—');
    assert.equal(grid.children[1].dataset.focus,'true');
    assert.equal(grid.children[4].dataset.focus,'false');
});


test('startup waits for replica presence and video, then five seconds of readiness', async()=>{
    const f=fixture();
    f.run(`
        var clock=0, observations=0;
        Date.now=()=>clock;
        setTimeout=fn=>{clock+=1000; fn();};
        joined=true; frame={video:{srcObject:null}};
        refresh=async()=>{
            observations++;
            online=true;
            state={active:true,connected:true,replica_participant_ids:observations>=3?['replica']:[]};
            if(observations>=4) frame.video.srcObject={};
        };
    `);
    await f.run('waitForPresenter()');
    assert.equal(f.run('clock'),8000);
});

test('startup times out without a replica and never sends Echo', async()=>{
    const f=fixture();
    f.run(`
        var clock=0, sends=0;
        Date.now=()=>clock;
        setTimeout=fn=>{clock+=1000; fn();};
        joined=true; frame={video:{srcObject:null}};
        api=async()=>{sends++;};
        refresh=async()=>{online=true;state={active:true,connected:true,replica_participant_ids:[]};};
    `);
    await assert.rejects(f.run('waitForPresenter()'),/did not become ready/);
    assert.equal(f.run('sends'),0);
});

test('startup restarts its warm-up after a connection interruption', async()=>{
    const f=fixture();
    f.run(`
        var clock=0;
        Date.now=()=>clock;
        setTimeout=fn=>{clock+=1000; fn();};
        joined=true; frame={video:{srcObject:{}}};
        refresh=async()=>{
            online=clock!==3000;
            state={active:true,connected:true,replica_participant_ids:['replica']};
        };
    `);
    await f.run('waitForPresenter()');
    assert.equal(f.run('clock'),9000);
});
