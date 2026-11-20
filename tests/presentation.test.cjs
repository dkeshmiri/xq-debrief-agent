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

function partFixture() {
    const f=fixture();
    f.run(`state=${JSON.stringify({...state,active:true,connected:true,completed:true,has_next_part:true,part_end_index:0,session_id:'first'})};
        online=true; joined=true; refresh=async()=>{}; var calls=[];
        frame={destroy:async()=>calls.push('destroy')};
        api=async(action,method,body)=>{calls.push([action,body]);return {conversation:{conversation_id:'second'}};};
        joinConversation=async()=>{calls.push('join-ready');joined=true;state.completed=false;state.index=1;};`);
    return f;
}

test('automatic boundary destroys old viewer, creates next session, waits, then speaks once',async()=>{
    const f=partFixture(); f.get('autoplay').checked=true;
    await f.run('poll()'); await f.run('poll()');
    assert.deepEqual(JSON.parse(f.run('JSON.stringify(calls)')),
        ['destroy',['next-part',{session_id:'first'}],'join-ready',['play',null]]);
});

test('autoplay off pauses at boundary and manual next starts the next part',async()=>{
    const f=partFixture(); f.get('autoplay').checked=false;
    await f.run('poll()'); assert.equal(f.run('calls.length'),0);
    await f.run('next()'); assert.equal(f.run('calls[1][0]'),'next-part');
    assert.equal(f.run('calls[3][0]'),'play');
});

test('failed handoff disables autoplay and never retries automatically',async()=>{
    const f=partFixture(); f.get('autoplay').checked=true;
    f.run('api=async()=>{calls.push("failed");throw new Error("Connection failed");};');
    await f.run('poll()'); await f.run('poll()');
    assert.equal(f.get('autoplay').checked,false);
    assert.equal(f.run('calls.filter(c=>c==="failed").length'),1);
});

test('turning autoplay off during reconnection holds the next part before Echo',async()=>{
    const f=partFixture(); f.get('autoplay').checked=true;
    f.run('joinConversation=async()=>{joined=true;$("autoplay").checked=false;};');
    await f.run('next(true)');
    assert.equal(f.run('calls.some(c=>c[0]==="play")'),false);
});

test('busy handoff rejects another browser action',async()=>{
    const f=partFixture();
    f.run('var release; joinConversation=()=>new Promise(resolve=>{release=resolve;});var firstRun=run(next);');
    await Promise.resolve(); await Promise.resolve(); await Promise.resolve();
    assert.equal(await f.run('run(next)'),false);
    f.run('release();'); await f.run('firstRun');
    assert.equal(f.run('calls.filter(c=>c[0]==="next-part").length'),1);
});

test('late leave or error from an old viewer cannot disconnect the new viewer',async()=>{
    const f=fixture();
    f.run(`refresh=async()=>{};waitForPresenter=async()=>{};var players=[];
        window.PresentationPlayer=class {
            constructor(){this.handlers={};players.push(this);}
            on(name,fn){this.handlers[name]=fn;}
            async join(){}
        };`);
    await f.run('joinConversation({conversation:{conversation_url:"first"}})');
    await f.run('joinConversation({conversation:{conversation_url:"second"}})');
    f.run('players[0].handlers["left-meeting"]();players[0].handlers.error();');
    assert.equal(f.run('joined && frame===players[1]'),true);
});

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
    assert.equal(f.get('mario-source').disabled,true);
    f.run(`render(${JSON.stringify(state)})`);
    assert.equal(f.get('amethyst-source').disabled,false);
    assert.equal(f.get('mario-source').disabled,false);
});

test('Mario selector requests its own prepared source',async()=>{
    const f=fixture(); f.run(`render(${JSON.stringify(state)})`);
    f.run('var requested; changeSource=async(profile,preset)=>{requested={profile,preset};}; refresh=async()=>{};');
    await f.get('mario-source').handlers.click();
    assert.equal(f.run('JSON.stringify(requested)'), JSON.stringify({profile:null,preset:'mario'}));
});

test('report wheel renders the source image with an accessible marker legend',()=>{
    const f=fixture();
    const chart={kind:'report_image',title:'People and action',note:'Behavioral styles',
        image:'/static/presentation-assets/mario-insights-wheel.png',alt:'Dot 14; star 13',
        legend:['● Natural · 14 · Persuading Promoter','★ Adapted · 13 · Promoting Persuader'],attribution:'Report page 29'};
    f.run(`renderVisual(${JSON.stringify(chart)})`);
    const figure=f.get('chapter-visual').children[2];
    assert.equal(figure.children[0].src,chart.image);
    assert.equal(figure.children[0].alt,chart.alt);
    assert.deepEqual(figure.children[1].children.map(p=>p.textContent),chart.legend);
});

test('family report galleries preserve supplied images and link to full-size pages',()=>{
    const f=fixture();
    const bundle=JSON.parse(fs.readFileSync('content/presentations/sheila-kieren.json','utf8'));
    f.run(`renderVisual(${JSON.stringify(bundle.visuals.section_1)})`);
    const gallery=f.get('chapter-visual').children[2];
    assert.equal(gallery.children.length,2);
    for(let i=0;i<2;i++){
        const link=gallery.children[i].children[1];
        assert.equal(link.href,bundle.visuals.section_1.items[i].image);
        assert.equal(link.children[0].src,link.href);
        assert.equal(link.target,'_blank');
    }
    f.run(`renderVisual(${JSON.stringify(bundle.visuals.section_8)})`);
    assert.equal(f.get('chapter-visual').dataset.kind,'discussion');
    assert.match(f.get('chapter-visual').children[2].children[4].textContent,/own 0–10 response/);
});

test('family source selects its preset and locks during playback',async()=>{
    const f=fixture();f.run(`render(${JSON.stringify(state)})`);
    f.run('var chosen;changeSource=async(p,preset)=>{chosen=preset;};refresh=async()=>{};');
    await f.get('family-source').handlers.click();
    assert.equal(f.run('chosen'),'sheila-kieren');
    f.run(`render(${JSON.stringify({...state,active:true})})`);
    assert.equal(f.get('family-source').disabled,true);
});

test('Kevin selector uses the two-part preset and locks during playback',async()=>{
    const f=fixture(); f.run(`render(${JSON.stringify(state)})`);
    f.run('var chosen;changeSource=async(profile,preset)=>{chosen=preset;};refresh=async()=>{};');
    await f.get('kevin-source').handlers.click();
    assert.equal(f.run('chosen'),'kevin');
    f.run(`render(${JSON.stringify({...state,active:true})})`);
    assert.equal(f.get('kevin-source').disabled,true);
});

test('Kevin automatically hands off from his final DISC chapter to Driving Forces',async()=>{
    const f=partFixture();
    const bundle=JSON.parse(fs.readFileSync('content/presentations/kevin.json','utf8'));
    f.run(`state.chapters=${JSON.stringify(bundle.chapters)};state.parts=${JSON.stringify(bundle.parts)};
        state.index=6;state.part_end_index=6;state.part_index=0;
        joinConversation=async()=>{calls.push('join-ready');joined=true;state.index=7;state.part_index=1;state.completed=false;};`);
    f.get('autoplay').checked=true;await f.run('poll()');await f.run('poll()');
    assert.equal(f.run('state.index'),7);
    assert.deepEqual(JSON.parse(f.run('JSON.stringify(calls)')),
        ['destroy',['next-part',{session_id:'first'}],'join-ready',['play',null]]);
});

test('family presentation advances through every chapter and ends without operator input',async()=>{
    const f=fixture();
    const bundle=JSON.parse(fs.readFileSync('content/presentations/sheila-kieren.json','utf8'));
    f.run(`state=${JSON.stringify({...state,chapters:bundle.chapters,active:true,connected:true,completed:true})};
        online=true;joined=true;var actions=[];refresh=async()=>{};
        api=async(action)=>{actions.push(action);if(action==='next')state.index++;if(action==='end')state.active=false;};`);
    f.get('autoplay').checked=true;
    for(let i=0;i<9;i++)await f.run('poll()');
    assert.deepEqual(JSON.parse(f.run('JSON.stringify(actions)')),[...Array(8).fill('next'),'end']);
});

test('priority graphics show ranks without manufacturing percentage bars',()=>{
    const f=fixture();
    f.run(`renderVisual(${JSON.stringify({kind:'force_ranks',title:'Priorities',note:'Priority order',items:[
        {label:'Receptive',rank:1,color:'methodologies'}, {label:'Harmonious',rank:5,color:'surroundings'}]})})`);
    const rows=f.get('chapter-visual').children[2].children;
    assert.equal(rows[0].children[0].textContent,'1');
    assert.equal(rows[0].children[1].textContent,'Receptive');
    assert.equal(rows[1].value,5);
    assert.equal(rows[1].children[0].dataset.color,'surroundings');
    assert.equal(rows[1].children[0].style.width,undefined);
});

test('ACI omits empty summaries without inventing blind spots or losing zero scores',()=>{
    const f=fixture();
    f.run(`renderVisual(${JSON.stringify({kind:'aci',title:'ACI',note:'Values',panels:[{
        title:'World View',clarity_average:null,emotional_bias_distortion:0,problems:[],dimensions:[
            {label:'People',context:'People',color:'intrinsic',clarity:0,bias:'mixed',valuation:'Mixed valuation',blind_spot:null}
        ]}]})})`);
    const panel=f.get('chapter-visual').children[2].children[0];
    const column=panel.children[1].children[1];
    assert.equal(column.children[2].textContent,'0');
    assert.equal(column.children.length,5);
    assert.equal(panel.children[2].textContent,'Emotional bias distortion: 0');
    assert.equal(panel.children.length,3);
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


test('workforce barometers preserve percentage widths and show both mixes',()=>{
    const f=fixture();
    const bundle=JSON.parse(fs.readFileSync('content/presentations/workforce-investor.json','utf8'));
    f.run(`renderVisual(${JSON.stringify(bundle.visuals.transformation)})`);
    const groups=f.get('chapter-visual').children[2].children;
    assert.equal(groups.length,2);
    assert.deepEqual(groups[0].children[2].children.map(segment=>segment.style.width), ['25%','50%','25%']);
    assert.deepEqual(groups[1].children[2].children.map(segment=>segment.style.width), ['40%','45%','15%']);
    assert.equal(groups[1].children[3].children[2].children[1].textContent,'At-risk');
    assert.match(groups[1].children[0].textContent,/goal/);
});

test('Persian content is RTL, human-led, and switches back to English cleanly',()=>{
    const f=fixture();
    const bundle=JSON.parse(fs.readFileSync('content/presentations/iranian-american-fa.json','utf8'));
    const persian={...state,language:'fa',narration_supported:false,chapters:bundle.chapters,visuals:bundle.visuals,revision:1};
    f.run(`render(${JSON.stringify(persian)})`);
    for (const id of ['chapter-visual','script','full-script','chapters','preview-chapter','visual-source']) {
        assert.equal(f.get(id).dir,'rtl');
        assert.equal(f.get(id).lang,'fa');
    }
    assert.equal(f.get('start').disabled,true);
    assert.equal(f.get('language-note').hidden,false);
    for(const [index,chapter] of bundle.chapters.entries()) {
        f.get('preview-chapter').value=String(index); f.get('preview-chapter').handlers.change();
        assert.equal(f.get('chapter-visual').children[0].textContent,chapter.title);
        assert.equal(f.get('script').textContent,chapter.text);
    }
    f.run(`render(${JSON.stringify({...state,revision:2})})`);
    assert.equal(f.get('chapter-visual').dir,'ltr');
    assert.equal(f.get('full-script').lang,'en');
    assert.equal(f.get('start').disabled,false);
    assert.equal(f.get('language-note').hidden,true);
});

test('both Iranian-American source buttons lock during a live presentation',()=>{
    const f=fixture(); f.run(`render(${JSON.stringify({...state,active:true})})`);
    for(const id of ['iranian-source','iranian-fa-source']) assert.equal(f.get(id).disabled,true);
    f.run(`render(${JSON.stringify(state)})`);
    for(const id of ['iranian-source','iranian-fa-source']) assert.equal(f.get(id).disabled,false);
});
