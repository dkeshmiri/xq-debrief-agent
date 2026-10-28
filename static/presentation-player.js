/* A single replica's media, without Daily's meeting tiles or video cropping. */
class PresentationPlayer {
    constructor(container, placeholder, onNotice) {
        this.call = window.DailyIframe.createCallObject({videoSource:false, audioSource:false});
        this.placeholder = placeholder;
        this.closed = false;
        this.ids = new Set();
        this.video = document.createElement('video');
        this.video.autoplay = true; this.video.playsInline = true; this.video.muted = true;
        this.video.className = 'replica-video';
        this.video.setAttribute('aria-label', 'XQ presentation guide');
        this.audio = document.createElement('audio'); this.audio.autoplay = true;
        this.resume = document.createElement('button');
        this.resume.textContent = 'Enable presenter audio'; this.resume.hidden = true;
        this.resume.className = 'resume-presenter-audio';
        this.resume.addEventListener('click', async () => {
            try { await this.audio.play(); this.resume.hidden = true; }
            catch { onNotice('Audio could not start. Check your browser’s audio permissions.'); }
        });
        container.replaceChildren(this.video, this.audio, this.resume);
        for (const event of ['participant-joined', 'participant-updated', 'participant-left', 'track-started', 'track-stopped'])
            this.call.on(event, () => this.sync());
        this.call.on('left-meeting', () => this.clear());
    }
    on(event, callback) { this.call.on(event, callback); return this; }
    async join(options) { await this.call.join(options); this.sync(); }
    setReplicaIds(ids = []) { this.ids = new Set(ids); this.sync(); }
    sync() {
        if (this.closed) return;
        const replicas = Object.values(this.call.participants()).filter(p => !p.local && (
            this.ids.has(p.session_id) || /^tavus-replica(?:-|$)/.test(p.user_id || '')));
        const participant = replicas.find(p => p.tracks?.video?.state === 'playable') || replicas[0];
        for (const [kind, element] of [['video', this.video], ['audio', this.audio]]) {
            const info = participant?.tracks?.[kind];
            const track = info?.state === 'playable' ? (info.persistentTrack || info.track) : null;
            if (element.srcObject?.getTracks()[0] === track) continue;
            element.srcObject = track ? new MediaStream([track]) : null;
            if (track) element.play().catch(() => {
                if (!this.closed && kind === 'audio' && element.srcObject?.getTracks()[0] === track)
                    this.resume.hidden = false;
            });
            if (kind === 'audio') this.resume.hidden = true;
        }
        this.placeholder.hidden = !!this.video.srcObject;
    }
    clear() {
        for (const element of [this.video, this.audio]) { element.pause(); element.srcObject = null; }
        this.resume.hidden = true; this.placeholder.hidden = false;
    }
    async destroy() { this.closed = true; this.clear(); await this.call.destroy(); }
}
window.PresentationPlayer = PresentationPlayer;
