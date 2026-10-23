"use strict";
(() => {
  const $ = id => document.getElementById(id);
  const base = document.body?.dataset?.apiBase || '';
  function choose(existing) {
    $("existing-panel").hidden = !existing;
    $("new-panel").hidden = existing;
    $("choose-existing").setAttribute("aria-pressed", String(existing));
    $("choose-new").setAttribute("aria-pressed", String(!existing));
    $("choose-existing").classList.toggle("secondary", !existing);
    $("choose-new").classList.toggle("secondary", existing);
  }
  $("choose-existing").addEventListener("click", () => choose(true));
  $("choose-new").addEventListener("click", () => choose(false));
  $("select-form").addEventListener("submit", event => {
    event.preventDefault();
    if ($("saved-profile").value) window.location.href = `${base}/debrief?file=${encodeURIComponent($("saved-profile").value)}`;
  });
  async function load() {
    try {
      const response = await fetch(`${base}/api/personas`);
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "Could not load saved profiles.");
      $("saved-profile").replaceChildren();
      for (const person of data.personas) {
        const option = document.createElement("option");
        option.value = person.file;
        option.textContent = `${person.display_name} — ${person.family_role}`;
        $("saved-profile").appendChild(option);
      }
      $("continue").disabled = !data.personas.length;
      if (!data.personas.length) $("status").textContent = "No saved profiles yet. Create one to begin.";
    } catch (error) { $("status").textContent = error.message; }
  }
  load();
})();
