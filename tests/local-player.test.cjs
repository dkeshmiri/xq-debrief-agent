const {test} = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');

function fixture() {
    const nodes = new Map();
    const node = id => {
        if (!nodes.has(id)) nodes.set(id, {dataset:{}, style:{setProperty(){}}, setAttribute(){}});
        return nodes.get(id);
    };
    const calls = [], sources = [];
    class AudioContext {
        state = 'running';
        createAnalyser(){return {fftSize:256,connect(){},getByteTimeDomainData(array){array.fill(128);}};}
        createBufferSource(){const source={connect(){},start(){source.started=true;},stop(){source.stopped=true;}}; sources.push(source); return source;}
        async decodeAudioData(){return {};}
        async resume(){}
        async close(){}
    }
    const context = vm.createContext({window:{}, document:{getElementById:node}, AudioContext,
        Uint8Array, AbortSignal, requestAnimationFrame(){},
        fetch:async (url,options)=>{calls.push([url,options]); return {ok:true,arrayBuffer:async()=>new ArrayBuffer(4)};}});
    vm.runInContext(fs.readFileSync('static/local-player.js','utf8'), context);
    const player = new context.window.XQLocalPlayer('/business', ()=>{});
    player.session = 'session';
    return {player, node, calls, sources};
}

test('robot states distinguish idle, actual audio, question readiness, and API work',()=>{
    const f = fixture();
    for (const [activity,state] of [[{},'idle'],[{question_ready:true},'listening'],[{code:'reasoning'},'thinking']]) {
        f.player.stateFrom(activity); assert.equal(f.node('xq-robot').dataset.state,state);
    }
    f.player.source = {};
    f.player.stateFrom({}); assert.equal(f.node('xq-robot').dataset.state,'talking');
    f.player.source = null; f.player.uploading = true;
    f.player.stateFrom({question_ready:true}); assert.equal(f.node('xq-robot').dataset.state,'thinking');
});

test('audio start and end acknowledge the matching workspace/session/utterance',async()=>{
    const f = fixture();
    await f.player.play({id:'sentence',text:'Hello.'}, 0);
    assert.equal(f.sources[0].started,true);
    assert.equal(f.node('output').textContent,'Hello.');
    assert.equal(JSON.parse(f.calls[1][1].body).kind,'started');
    await f.sources[0].onended();
    assert.equal(f.calls[2][0],'/business/api/local/ack');
    assert.deepEqual(JSON.parse(f.calls[2][1].body),{session:'session',id:'sentence',kind:'ended'});
});

test('ending a session stops sound and rejects late completion',async()=>{
    const f = fixture();
    await f.player.play({id:'old',text:'Hello.'}, 0);
    const late = f.sources[0].onended;
    await f.player.destroy();
    await late();
    assert.equal(f.sources[0].stopped,true);
    assert.equal(f.calls.length,2);
    assert.equal(f.node('xq-robot').dataset.state,'idle');
});
