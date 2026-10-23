const {test} = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');

function fixture(business = false) {
    const elements = new Map();
    function element() {
        return {value:'', textContent:'', hidden:false, disabled:false, dataset:{}, children:[],
            classList:{toggle(){}}, handlers:{}, setAttribute(){}, removeAttribute(){},
            focus(){this.focused=true;},
            addEventListener(name, fn){this.handlers[name] = fn;},
            dispatchEvent(event){this.handlers[event.type]?.(event);},
            replaceChildren(){this.children=[];},
            appendChild(child){this.children.push(child); if (!this.value) this.value=child.value;},
            prepend(child){this.children.unshift(child); child.remove=()=>this.children.pop();},
            get lastElementChild(){return this.children.at(-1);},
            get selectedOptions(){return this.children.filter(child=>child.value===this.value);}
        };
    }
    const get = id => {if (!elements.has(id)) elements.set(id, element()); return elements.get(id);};
    const idle = {active:false, connected:false, changing:false, pending:false, question_ready:false,
        code:'ready', title:'Ready when you are', detail:'Choose a profile', state:'introduction'};
    const calls=[];
    let handler = async url => {
        if (url === '/api/personas') return {personas:[{file:'sample.json',display_name:'Sample',person_id:'sample'}]};
        if (url === '/api/activity') return idle;
        return {};
    };
    const context = vm.createContext({
        document:{body:{dataset:business ? {experience:'business',apiBase:'/business'} : {}}, getElementById:get, createElement:element, querySelectorAll:()=>[], hidden:false},
        window:{location:{search:''}, addEventListener(){}},
        fetch:async (url,options)=>{calls.push([url,options]); const data=await handler(business ? url.replace(/^\/business/,'') : url, options); return {ok:true,json:async()=>data};},
        URLSearchParams, AbortSignal, Event, Date,
        setTimeout:(fn,ms)=>ms===150 ? setImmediate(fn) : 1,
        setInterval:()=>1, clearInterval(){}
    });
    vm.runInContext(fs.readFileSync('static/app.js','utf8'),context);
    return {get, calls, idle, run:code=>vm.runInContext(code,context), respond:fn=>handler=fn};
}
const settle = () => new Promise(resolve=>setImmediate(resolve));

test('idle controls permit starting only after profile and telemetry load', async()=>{
    const f=fixture(); await settle();
    assert.equal(f.get('start-button').disabled,false);
    assert.equal(f.get('next-button').disabled,true);
    assert.equal(f.get('ask-button').disabled,true);
});
test('missing video library reports a visible error without creating a session',async()=>{
    const f=fixture(); await settle();
    await f.run('run(startSession)');
    assert.match(f.get('notice').textContent,/video player could not load/);
    assert.equal(f.calls.filter(([url])=>url==='/api/session/start').length,0);
    assert.equal(f.get('start-button').disabled,false);
});
test('failed join leaves end-session recovery available',async()=>{
    const f=fixture(); await settle();
    f.respond(async url=>url==='/api/session/start' ? {conversation:{conversation_id:'test',conversation_url:'test'}} : {...f.idle,active:true,connected:true});
    f.run("window.DailyIframe={createFrame:()=>({on(){},join:async()=>{throw new Error('Join failed');},destroy:async()=>{}})}");
    await f.run('run(startSession)');
    assert.match(f.get('notice').textContent,/Join failed/);
    assert.equal(f.get('end-button').hidden,false);
    assert.equal(f.get('end-button').disabled,false);
    assert.equal(f.get('person-select').disabled,true);
    assert.equal(f.get('next-button').disabled,true);
});
test('connection loss pauses controls and keeps last observed history',async()=>{
    const f=fixture(); await settle();
    const count=f.get('activity-history').children.length;
    f.respond(async()=>{throw new Error('offline');});
    await f.run('refresh()');
    assert.equal(f.get('status').textContent,'Cannot reach the app');
    assert.equal(f.get('start-button').disabled,true);
    assert.equal(f.get('activity-history').children.length,count);
});
test('reloaded active sessions offer cleanup without playback',async()=>{
    const f=fixture(); await settle();
    f.run("renderActivity({active:true,connected:true,code:'between',title:'A moment',detail:'',state:'introduction'})");
    assert.equal(f.get('end-button').hidden,false);
    assert.equal(f.get('next-button').disabled,true);
    assert.match(f.get('notice').textContent,/already open/);
});
test('answer ownership disables questions and history is bounded',async()=>{
    const f=fixture(); await settle();
    f.run("callFrame={}; joined=true; $('question-input').value='Question';");
    for(let i=0;i<8;i++) f.run("renderActivity({active:true,connected:true,answer_pending:true,code:'stage"+i+"',title:'Observed',detail:'',state:'introduction'})");
    assert.equal(f.get('ask-button').disabled,true);
    assert.equal(f.get('activity-history').children.length,4);
});

const narrating = {active:true, connected:true, pending:true, phase:'narrating',
    code:'speaking', title:'Sharing the next thought', state:'introduction'};
const questionReady = {...narrating, pending:false, phase:'question_ready', code:'question', question_ready:true};

test('manual question control is available only during joined narration',async()=>{
    const f=fixture(); await settle();
    assert.equal(f.get('pause-question-button').disabled,true);
    f.run('callFrame={}; joined=true;');
    f.run(`renderActivity(${JSON.stringify(narrating)})`);
    assert.equal(f.get('pause-question-button').disabled,false);
    for(const changes of [{code:'preparing'}, {phase:'answering'}, {interrupted:true},
        {connected:false}, {changing:true}, questionReady]) {
        f.run(`renderActivity(${JSON.stringify({...narrating,...changes})})`);
        assert.equal(f.get('pause-question-button').disabled,true);
    }
});

test('manual pause waits for acknowledgement, ignores duplicate clicks, and focuses the question',async()=>{
    const f=fixture(); await settle();
    f.run('callFrame={}; joined=true;');
    f.run(`renderActivity(${JSON.stringify(narrating)})`);
    let polls=0;
    f.respond(async url=>url==='/api/activity'
        ? (++polls===1 ? {...narrating,interrupted:true,code:'pausing'} : questionReady) : {});
    const first=f.get('pause-question-button').handlers.click();
    await f.get('pause-question-button').handlers.click();
    assert.equal(f.get('question-input').focused,undefined);
    await first;
    assert.equal(f.calls.filter(([url])=>url==='/api/debrief/interrupt').length,1);
    assert.equal(f.calls.some(([url])=>url==='/api/question'),false);
    assert.equal(f.get('question-input').focused,true);
    assert.equal(f.get('dismiss-button').disabled,false);
    assert.match(f.get('question-mode-hint').textContent,/Question mode is open/);
});

test('failed manual interruption reports the error without focusing the question',async()=>{
    const f=fixture(); await settle();
    f.run('callFrame={}; joined=true;');
    f.respond(async url=>{
        if(url==='/api/debrief/interrupt') throw new Error('Waiting for Tavus playback to start.');
        return narrating;
    });
    await f.get('pause-question-button').handlers.click();
    assert.match(f.get('notice').textContent,/Waiting for Tavus/);
    assert.equal(f.get('question-input').focused,undefined);
    assert.equal(f.get('pause-question-button').disabled,false);
});

test('missing stop acknowledgement times out without submitting a question',async()=>{
    const f=fixture(); await settle();
    f.run('callFrame={}; joined=true; let ticks=0; Date=class extends Date {static now(){return ticks++*11000;}};');
    f.respond(async url=>url==='/api/activity' ? {...narrating,interrupted:true,code:'pausing'} : {});
    await f.get('pause-question-button').handlers.click();
    assert.match(f.get('notice').textContent,/Speech has not stopped yet/);
    assert.equal(f.get('question-input').focused,undefined);
    assert.equal(f.calls.some(([url])=>url==='/api/question'),false);
});

test('typed questions still wait for the same stop acknowledgement before submitting',async()=>{
    const f=fixture(); await settle();
    f.run("callFrame={}; joined=true; $('question-input').value='How can we communicate?';");
    let polls=0;
    f.respond(async url=>{
        if(url==='/api/activity') return ++polls===1 ? narrating : questionReady;
        if(url==='/api/question') return {answer:'An example answer'};
        return {};
    });
    await f.run('run(askQuestion)');
    const paths=f.calls.map(([url])=>url);
    assert.ok(paths.indexOf('/api/debrief/interrupt')<paths.indexOf('/api/question'));
    assert.equal(f.get('answer-text').textContent,'An example answer');
});


test('business conversation controls keep all API calls in the business namespace',async()=>{
    const f=fixture(true);await settle();
    f.run('callFrame={}; joined=true;');
    f.respond(async url=>url==='/api/activity' ? questionReady : {});
    await f.get('pause-question-button').handlers.click();
    assert.equal(f.get('question-input').focused,true);
    assert.ok(f.calls.every(([url])=>url.startsWith('/business/api/')));
    assert.equal(f.calls.filter(([url])=>url==='/business/api/debrief/interrupt').length,1);
});
