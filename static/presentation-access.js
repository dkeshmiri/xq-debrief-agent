'use strict';
(() => {
    const form = document.getElementById('presentation-unlock');
    const pin = document.getElementById('presentation-pin');
    const unlock = document.getElementById('presentation-unlock-button');
    const open = document.getElementById('presentation-mode');
    const status = document.getElementById('presentation-access-status');
    let submitting = false;
    function setAccess(unlocked) {
        open.disabled = !unlocked;
        status.textContent = unlocked ? 'Presentation Mode is unlocked for this browser.' : 'Operator PIN required.';
    }
    open.addEventListener('click', () => {
        if (!open.disabled) window.location.href = '/presentation';
    });
    form.addEventListener('submit', async event => {
        event.preventDefault();
        if (submitting) return;
        submitting = true;
        unlock.disabled = true;
        open.disabled = true;
        try {
            const response = await fetch('/api/presentation/unlock', {
                method:'POST', headers:{'Content-Type':'application/json'},
                body:JSON.stringify({pin:pin.value}), cache:'no-store'
            });
            const data = await response.json();
            if (!response.ok) throw new Error(data.error || 'Could not unlock Presentation Mode.');
            setAccess(data.unlocked === true);
        } catch (error) {
            status.textContent = error.message;
        } finally {
            pin.value = '';
            submitting = false;
            unlock.disabled = false;
        }
    });
    fetch('/api/presentation/access', {cache:'no-store'})
        .then(response => response.ok ? response.json() : {unlocked:false})
        .then(data => { if (!submitting && open.disabled) setAccess(data.unlocked === true); })
        .catch(() => { if (!submitting) status.textContent = 'Unable to check access. Enter your operator PIN to retry.'; });
})();
