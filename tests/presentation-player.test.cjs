const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
function fixture() {
    const events = {}, participants = {};
    let options, destroyed = false;
    const call = {on:(name,fn)=>events[name]=fn, participants:()=>participants,
        join:async()=>{}, destroy:async()=>{destroyed=true;}};
    const element = () => ({srcObject:null,hidden:false,handlers:{},setAttribute(){},
        addEventListener(name,fn){this.handlers[name]=fn;}, play:()=>Promise.resolve(), pause(){},
        replaceChildren(...children){this.children=children;}});
    const container=element(), placeholder=element();
    const context = vm.createContext({window:{DailyIframe:{createCallObject:o=>{options=o;return call;}}},
        document:{createElement:element}, MediaStream:class {constructor(tracks){this.tracks=tracks;} getTracks(){return this.tracks;}}});
    vm.runInContext(fs.readFileSync('static/presentation-player.js','utf8'),context);
    const player=new context.window.PresentationPlayer(container,placeholder,()=>{});
    return {player,participants,events,placeholder,options,destroyed:()=>destroyed};
}
const participant=(id,user_id)=>({session_id:id,user_id,local:false,tracks:{
    video:{state:'playable',track:{id:id+'-video'}},audio:{state:'playable',track:{id:id+'-audio'}}}});
test('only replica media renders even with other people present, and track replacements update',()=>{
    const f=fixture();
    assert.equal(f.options.videoSource,false); assert.equal(f.options.audioSource,false);
    f.participants.viewer=participant('viewer','human'); f.player.sync();
    assert.equal(f.player.video.srcObject,null);
    f.participants.replica=participant('replica','tavus-replica-123'); f.events['participant-joined']();
    assert.equal(f.player.video.srcObject.getTracks()[0].id,'replica-video');
    assert.equal(f.player.audio.srcObject.getTracks()[0].id,'replica-audio');
    assert.equal(f.placeholder.hidden,true);
    f.participants.replica.tracks.video.track={id:'replacement'}; f.events['participant-updated']();
    assert.equal(f.player.video.srcObject.getTracks()[0].id,'replacement');
    delete f.participants.replica; f.events['participant-left']();
    assert.equal(f.player.video.srcObject,null); assert.equal(f.placeholder.hidden,false);
});
test('server identified PAL works without a replica user ID and ending clears tracks',async()=>{
    const f=fixture(); f.participants.pal=participant('pal','unknown');
    f.player.setReplicaIds(['pal']);
    assert.equal(f.player.video.srcObject.getTracks()[0].id,'pal-video');
    await f.player.destroy(); f.events['participant-updated']();
    assert.equal(f.destroyed(),true); assert.equal(f.player.video.srcObject,null);
    assert.equal(f.player.audio.srcObject,null);
});
test('blocked audio offers an explicit retry control',async()=>{
    const f=fixture(); f.participants.replica=participant('replica','tavus-replica-123');
    f.player.audio.play=()=>Promise.reject(new Error('autoplay'));
    f.player.sync(); await Promise.resolve();
    assert.equal(f.player.resume.hidden,false);
    f.player.audio.play=()=>Promise.resolve(); await f.player.resume.handlers.click();
    assert.equal(f.player.resume.hidden,true);
});
