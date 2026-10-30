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
    vm.runInContext(fs.readFileSync('static/investor-visuals.js', 'utf8'), context);
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


test('ACI renders clarity, valuation, blind spots and summaries without treating missing as zero',()=>{
    const f=fixture();
    f.run(`renderVisual(${JSON.stringify({kind:'aci',title:'ACI',note:'Scores',panels:[{
        title:'World View',clarity_average:85,emotional_bias_distortion:15,
        dimensions:[{label:'Understanding Others',context:'People',color:'intrinsic',clarity:92,blind_spot:8,bias:'mixed',valuation:'Mixed valuation'},
            {label:'Practical Thinking',context:'Tasks',color:'extrinsic',clarity:0,blind_spot:0,bias:'under',valuation:'Undervaluation'},
            {label:'Systems Judgment',context:'Systems',color:'systemic',clarity:null,blind_spot:null,bias:null,valuation:'Not reported'}],
        problems:[{label:'People',value:84,reference:86}]}]})})`);
    const panel=f.get('chapter-visual').children[2].children[0];
    assert.equal(panel.children[1].children[1].textContent,'85');
    const grid=panel.children[2];
    assert.equal(grid.children[1].children[1].children[0].style.height,'92%');
    assert.equal(grid.children[1].children[4].textContent,'↕ Mixed valuation');
    assert.equal(grid.children[1].children[5].textContent,'Blind spot: 8');
    assert.equal(grid.children[2].children[2].textContent,'0');
    assert.equal(grid.children[3].children[2].textContent,'Not reported');
    assert.equal(panel.children[3].textContent,'Emotional bias distortion: 15');
    assert.equal(panel.children[4].children[2].children[1].textContent,'84');
});

test('prepared presentation selector is locked during a live session',()=>{
    const f=fixture(); f.run(`render(${JSON.stringify({...state,active:true})})`);
    assert.equal(f.get('amethyst-source').disabled,true);
    f.run(`render(${JSON.stringify(state)})`);
    assert.equal(f.get('amethyst-source').disabled,false);
});


test('investor graphics use business units and a zero baseline rather than assessment scales',()=>{
    const f=fixture();
    f.run(`renderVisual(${JSON.stringify({kind:'investor',layout:'bars',title:'ROI',note:'Illustrative',takeaway:'Subscription only',source:'Deck',items:[{
        label:'Annual cost',unit:'USD',bars:[{label:'Cost',value:588000},{label:'Value',value:600000},{label:'Zero',value:0}]}]})})`);
    const group=f.get('chapter-visual').children[2].children[0];
    assert.equal(group.children[1].children[1].textContent,'600,000 USD');
    assert.equal(group.children[2].children[2].children[0].style.width,'98%');
    assert.equal(group.children[3].children[2].children[0].style.width,'100%');
    assert.equal(group.children[4].children[2].children[0].style.width,'0%');
    assert.equal(group.children[4].children[1].textContent,'0');
});

test('investor source locks in session and chapter preview supports each prepared graphic',()=>{
    const f=fixture(); f.run(`render(${JSON.stringify({...state,active:true})})`);
    assert.equal(f.get('workforce-source').disabled,true);
    const bundle=JSON.parse(fs.readFileSync('content/presentations/workforce-investor.json','utf8'));
    f.run(`render(${JSON.stringify({...state,chapters:bundle.chapters,visuals:bundle.visuals,revision:1})})`);
    assert.equal(f.get('workforce-source').disabled,false);
    for (const [index,chapter] of bundle.chapters.entries()) {
        f.get('preview-chapter').value=String(index); f.get('preview-chapter').handlers.change();
        assert.equal(f.get('chapter-visual').dataset.kind,'investor');
        assert.equal(f.get('chapter-visual').children[0].textContent,bundle.visuals[chapter.visual].title);
    }
});
