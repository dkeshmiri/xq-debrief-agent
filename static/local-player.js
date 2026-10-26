/* Local audio owns the talking animation; server acknowledgements own progress. */
class XQLocalPlayer {
    constructor(base, report) {
        this.base = base; this.report = report; this.session = null;
        this.context = new AudioContext(); this.generation = 0; this.source = null;
        this.analyser = this.context.createAnalyser(); this.analyser.fftSize = 256;
        this.analyser.connect(this.context.destination);
        this.samples = new Uint8Array(this.analyser.fftSize);
        this.robot = document.getElementById('xq-robot'); this.state = 'idle';
    }
    async unlock() { await this.context.resume(); }
    stateFrom(activity) {
        const state = this.source ? 'talking' : (activity.code === 'reasoning' || this.uploading) ? 'thinking'
            : activity.question_ready ? 'listening' : 'idle';
        this.robot.dataset.state = state;
        this.robot.setAttribute('aria-label', `XQ robot guide, ${state}`);
        document.getElementById('robot-state-label').textContent = {
            idle:activity.code === 'connecting' ? 'Warming up the local voice' : activity.pending ? 'Preparing local speech' : 'Ready when you are',
            talking:'Sharing a thought', listening:'Your turn · microphone is opt-in', thinking:'Working with your question'
        }[state];
        this.activity = activity;
    }
    async ack(id, kind) {
        const response = await fetch(this.base+'/api/local/ack', {method:'POST', headers:{'Content-Type':'application/json'},
            body:JSON.stringify({session:this.session, id, kind}), signal:AbortSignal.timeout(5000)});
        if (!response.ok) throw new Error('Audio acknowledgement failed. End the conversation before retrying.');
    }
    async join(session) {
        this.session = session;
        this.poll(this.generation);
    }
    async poll(generation) {
        let revision = -1;
        try {
            while (generation === this.generation) {
                const response = await fetch(`${this.base}/api/local/command?session=${this.session}&after=${revision}`, {cache:'no-store', signal:AbortSignal.timeout(15000)});
                if (generation !== this.generation) return;
                if (!response.ok) throw new Error('Local playback disconnected. End this conversation before starting again.');
                const command = await response.json(); revision = command.revision;
                if (command.error) throw new Error(command.error);
                if (command.interrupt && this.source) {
                    this.source.onended = null; this.source.stop(); this.source = null;
                    await this.ack(command.id, 'interrupted'); this.stateFrom(this.activity || {});
                } else if (command.ready && !command.interrupt && command.id !== this.currentId) {
                    this.currentId = command.id;
                    await this.play(command, generation);
                }
            }
        } catch (error) {
            if (generation === this.generation) {
                this.stopAudio(); this.report(error.message);
            }
        }
    }
    async play(command, generation) {
        const response = await fetch(`${this.base}/api/local/audio/${command.id}?session=${this.session}`, {cache:'no-store', signal:AbortSignal.timeout(15000)});
        if (!response.ok) throw new Error('Local speech audio is no longer available. End the conversation and retry.');
        const buffer = await this.context.decodeAudioData(await response.arrayBuffer());
        if (generation !== this.generation) return;
        if (this.context.state !== 'running') throw new Error('Audio was suspended by the browser. End the conversation, then begin again.');
        const source = this.context.createBufferSource(); source.buffer = buffer; source.connect(this.analyser);
        source.onended = async () => {
            if (generation !== this.generation || this.source !== source) return;
            this.source = null; this.stateFrom(this.activity || {});
            try { await this.ack(command.id, 'ended'); } catch(error) { this.report(error.message); }
        };
        // Reserve server ownership before audio can finish or be interrupted.
        await this.ack(command.id, 'started');
        if (generation !== this.generation) return;
        this.source = source;
        source.start(); this.stateFrom(this.activity || {}); this.animate();
        document.getElementById('output').textContent = command.text;
    }
    animate() {
        if (!this.source) { this.robot.style.setProperty('--mouth', 1); return; }
        this.analyser.getByteTimeDomainData(this.samples);
        const rms = Math.sqrt(this.samples.reduce((sum, n) => sum+(n-128)**2, 0)/this.samples.length)/128;
        this.robot.style.setProperty('--mouth', Math.min(4, 1+rms*20));
        requestAnimationFrame(()=>this.animate());
    }
    stopAudio() {
        if (this.source) { this.source.onended = null; try { this.source.stop(); } catch {} this.source = null; }
        this.stateFrom({});
    }
    async destroy() {
        this.generation++; this.session = null; this.stopAudio();
        await this.context.close();
    }
}
window.XQLocalPlayer = XQLocalPlayer;
