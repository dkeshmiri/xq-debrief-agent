/* Windows backend transport only. The visible app keeps its existing Daily UI. */
(() => {
  'use strict';
  let call, context;
  const wanted = new Set();
  const streams = new Map();
  const emit = event => window.xqTransportEvent(event).catch(() => {});
  const participant = p => ({id:p.session_id, info:{userName:p.user_name, isLocal:p.local}});
  const worklet = `class XQPCM extends AudioWorkletProcessor {
    constructor() { super(); this.frame = new Int16Array(320); this.offset = 0; }
    process(inputs) {
      const channels = inputs[0];
      if (!channels || !channels.length) return true;
      for (let i=0; i<channels[0].length; i++) {
        let value=0;
        for (const channel of channels) value += channel[i] / channels.length;
        this.frame[this.offset++] = Math.round(Math.max(-1, Math.min(1, value))*32767);
        if (this.offset === 320) {
          this.port.postMessage(this.frame.buffer, [this.frame.buffer]);
          this.frame = new Int16Array(320); this.offset=0;
        }
      }
      return true;
    }
  } registerProcessor('xq-pcm', XQPCM);`;
  let audioReady;
  function prepareAudio() {
    if (!audioReady) audioReady = (async () => {
      context = new AudioContext({sampleRate:16000});
      if (context.sampleRate !== 16000) throw new Error('16 kHz audio is unavailable.');
      const url = URL.createObjectURL(new Blob([worklet], {type:'text/javascript'}));
      try { await context.audioWorklet.addModule(url); }
      finally { URL.revokeObjectURL(url); }
      await context.resume();
    })();
    return audioReady;
  }
  function stopAudio(id) {
    const stream = streams.get(id);
    if (stream) { stream.source.disconnect(); stream.node.disconnect(); stream.node.port.close(); }
    streams.delete(id);
  }
  async function attach(p) {
    if (!p || p.local || !wanted.has(p.session_id)) return;
    const track = p.tracks?.audio?.persistentTrack;
    if (!track || track.readyState === 'ended') { stopAudio(p.session_id); return; }
    if (streams.get(p.session_id)?.track === track) return;
    await prepareAudio();
    if (!wanted.has(p.session_id) || streams.get(p.session_id)?.track === track) return;
    stopAudio(p.session_id);
    const source = context.createMediaStreamSource(new MediaStream([track]));
    const node = new AudioWorkletNode(context, 'xq-pcm');
    node.port.onmessage = ({data}) => {
      if (!wanted.has(p.session_id)) return;
      const bytes = new Uint8Array(data);
      let binary = '';
      for (const byte of bytes) binary += String.fromCharCode(byte);
      emit({type:'audio', id:p.session_id, pcm:btoa(binary)});
    };
    // The processor writes silence to its output; no duplicate audible voice.
    source.connect(node).connect(context.destination);
    streams.set(p.session_id, {track, source, node});
  }
  const attachSafely = p => attach(p).catch(error => emit({type:'error', message:error.message}));
  window.xqDaily = {
    async join({url, token}) {
      call = window.DailyIframe.createCallObject({audioSource:false, videoSource:false,
                                                 subscribeToTracksAutomatically:false});
      call.on('joined-meeting', () => emit({type:'state', state:'joined'}));
      call.on('left-meeting', () => emit({type:'state', state:'left'}));
      call.on('error', e => emit({type:'error', message:e.errorMsg || 'Daily connection failed'}));
      call.on('app-message', e => emit({type:'message', data:e.data, sender:e.fromId}));
      call.on('participant-joined', e => emit({type:'joined', participant:participant(e.participant)}));
      call.on('participant-updated', e => attachSafely(e.participant));
      call.on('track-started', e => attachSafely(e.participant));
      call.on('participant-left', e => {
        wanted.delete(e.participant.session_id); stopAudio(e.participant.session_id);
        emit({type:'left', participant:participant(e.participant)});
      });
      await call.join({url, ...(token ? {token} : {}), userName:'XQ Windows Transport'});
    },
    send(message) { call.sendAppMessage(message, '*'); },
    participants() {
      return Object.fromEntries(Object.entries(call.participants()).map(([id,p]) => [id, participant(p)]));
    },
    async listen(id) {
      wanted.add(id);
      call.updateParticipant(id, {setSubscribedTracks:{audio:true, video:false, screenAudio:false, screenVideo:false}});
      await attach(call.participants()[id]);
    },
    async leave() {
      wanted.clear();
      for (const id of streams.keys()) stopAudio(id);
      if (context) await context.close();
      if (call) { await call.leave(); await call.destroy(); }
    }
  };
})();
