"use strict";
(() => {
  const $ = id => document.getElementById(id);
  const forces = ["Intellectual", "Instinctive", "Resourceful", "Selfless", "Harmonious", "Objective", "Altruistic", "Intentional", "Commanding", "Collaborative", "Structured", "Receptive"];
  const eq = ["self_awareness", "self_regulation", "motivation", "social_awareness", "social_regulation"];
  const composites = ["self_composite", "others_composite", "total_eq"];
  let extraction = null;
  let result = null;
  let busy = false;
  let draftId = null;
  let revision = null;
  let dirty = false;
  const human = value => value.replaceAll("_", " ").replace(/\b\w/g, ch => ch.toUpperCase());
  const get = path => path.split(".").reduce((obj, key) => obj[key], extraction.facts);
  function set(path, value) {
    const keys = path.split(".");
    const last = keys.pop();
    keys.reduce((obj, key) => obj[key], extraction.facts)[last] = value;
  }
  function status(message, error = false) {
    $("status").textContent = message;
    $("status").classList.toggle("error", error);
  }
  function setBusy(value) {
    busy = value;
    $("use-persona").disabled = value;
    $("upload-fields").disabled = value;
    $("review-fields").disabled = value;
    $("generate-button").disabled = value || dirty || !$("reviewed").checked;
    $("status").setAttribute("aria-busy", String(value));
  }
  function clearResult() {
    result = null;
    $("use-persona").hidden = true;
    $("result-section").hidden = true;
    $("json-preview").textContent = "";
  }
  function missing() {
    const paths = [];
    function visit(value, path) {
      if (value !== null && typeof value === "object" && !Array.isArray(value)) {
        Object.entries(value).forEach(([key, child]) => visit(child, path ? `${path}.${key}` : key));
      } else if (path !== "person.age" && (value === null || value === "" || (Array.isArray(value) && !value.length))) {
        paths.push(path);
      }
    }
    visit(extraction.facts, "");
    return paths;
  }
  function updateReadiness() {
    const paths = missing();
    $("review-badge").textContent = paths.length ? `${paths.length} missing fields` : "Facts complete";
    $("review-badge").classList.toggle("draft", !!paths.length);
    $("missing").classList.toggle("success", !paths.length);
    $("missing").textContent = paths.length
      ? `Missing: ${paths.map(human).join(", ")}. You can generate a clearly marked draft now, or complete these fields from verified results. A draft cannot be used by the debrief engine.`
      : "All required factual fields are present. Review them before generating a debrief-ready persona.";
    $("generate-button").textContent = paths.length ? "Generate family JSON draft" : "Generate family JSON";
    document.querySelectorAll("[data-path]").forEach(input => input.classList.toggle("missing", paths.includes(input.dataset.path)));
  }
  function field(container, labelText, path, type = "text") {
    const label = document.createElement("label");
    label.textContent = labelText;
    const input = document.createElement("input");
    input.type = type;
    input.dataset.path = path;
    input.value = get(path) ?? "";
    if (type === "number") {
      input.min = "0";
      input.max = path === "person.age" ? "120" : "100";
      input.step = path === "person.age" ? "1" : "any";
    } else input.maxLength = 200;
    input.addEventListener("input", () => {
      set(path, input.value === "" ? null : type === "number" ? Number(input.value) : input.value.trim());
      changed();
    });
    label.append(input);
    $(container).append(label);
  }
  function changed() {
    clearResult();
    dirty = true;
    $("override-panel").hidden = false;
    $("download-extraction").disabled = true;
    $("reviewed").checked = false;
    $("generate-button").disabled = true;
    updateReadiness();
  }
  function renderReview(role) {
    dirty = false;
    $("override-panel").hidden = true;
    $("override-pin").value = "";
    $("download-extraction").disabled = false;
    ["identity-fields", "disc-fields", "force-fields", "cluster-fields", "eq-fields", "evidence", "sections", "warnings"].forEach(id => $(id).replaceChildren());
    const identity = [
      ["First name", "person.first_name"], ["Display name", "person.display_name"],
      ["Age (optional)", "person.age", "number"], ["Assessment date", "assessment.assessment_date", "date"],
      ["Assessment source", "assessment.source"], ["Reported primary style", "disc.primary_style"],
    ];
    identity.forEach(args => field("identity-fields", ...args));
    const roleLabel = document.createElement("label");
    roleLabel.textContent = "Family role";
    const roleInput = document.createElement("input");
    roleInput.id = "review-role";
    roleInput.value = role;
    roleInput.maxLength = 100;
    roleInput.required = true;
    roleInput.addEventListener("input", changed);
    roleLabel.append(roleInput);
    $("identity-fields").append(roleLabel);
    ["natural", "adapted"].forEach(profile => [..."DISC"].forEach(trait => field("disc-fields", `${human(profile)} ${trait}`, `disc.${profile}.${trait}`, "number")));
    forces.forEach(force => field("force-fields", force, `driving_forces.scores.${force}`, "number"));
    ["primary_cluster", "situational_cluster", "indifferent_cluster"].forEach(cluster => {
      const label = document.createElement("label");
      label.textContent = human(cluster);
      const select = document.createElement("select");
      select.multiple = true;
      select.dataset.path = `driving_forces.${cluster}`;
      const selected = get(select.dataset.path);
      [...selected, ...forces.filter(force => !selected.includes(force))].forEach(force => {
        const option = document.createElement("option");
        option.value = option.textContent = force;
        option.selected = selected.includes(force);
        select.append(option);
      });
      select.addEventListener("change", () => {set(select.dataset.path, [...select.selectedOptions].map(option => option.value)); changed();});
      label.append(select);
      $("cluster-fields").append(label);
    });
    eq.forEach(key => field("eq-fields", human(key), `eq.scores.${key}`, "number"));
    composites.forEach(key => field("eq-fields", human(key), `eq.${key}`, "number"));
    extraction.warnings.forEach(warning => {const p = document.createElement("p"); p.textContent = warning; $("warnings").append(p);});
    $("warnings").hidden = !extraction.warnings.length;
    extraction.evidence.forEach(item => {
      const div = document.createElement("div"); div.className = "evidence-item";
      const strong = document.createElement("strong"); strong.textContent = `${item.field} · ${item.document}, page ${item.page}`;
      div.append(strong, document.createTextNode(item.observation)); $("evidence").append(div);
    });
    extraction.sections.forEach(section => {
      const div = document.createElement("div"); div.className = "report-section";
      const title = document.createElement("h4"); title.textContent = `${section.title} · pages ${section.pages.join(", ")}`;
      const list = document.createElement("ul");
      section.findings.forEach(finding => {const li = document.createElement("li"); li.textContent = finding; list.append(li);});
      div.append(title, list); $("sections").append(div);
    });
    $("reviewed").checked = false;
    $("review-section").hidden = false;
    updateReadiness();
  }
  async function api(url, options) {
    const response = await fetch(url, options);
    let data;
    try {data = await response.json();} catch {throw new Error(`The server returned an unreadable response (${response.status}). Please retry.`);}
    if (!response.ok) throw new Error(data.error || `Request failed (${response.status}).`);
    return data;
  }
  function download(value, filename) {
    const url = URL.createObjectURL(new Blob([JSON.stringify(value, null, 2) + "\n"], {type: "application/json"}));
    const a = document.createElement("a"); a.href = url; a.download = filename;
    document.body.append(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  function loadDraft(data) {
    draftId = data.draft_id;
    revision = data.revision;
    extraction = data.extraction;
    clearResult();
    renderReview(data.family_role);
    $("override-history").textContent = data.overrides.length
      ? `${data.overrides.length} manual override save(s) recorded. Review revision ${revision}. Source evidence is retained as originally extracted.`
      : "No manual overrides saved.";
    try {sessionStorage.setItem("xq-assessment-draft", draftId);} catch {}
  }
  $("save-overrides").addEventListener("click", async () => {
    if (busy || !dirty || !draftId) return;
    const inputs = $("review-fields").querySelectorAll("input:not([type=checkbox]), select");
    if ([...inputs].some(input => !input.reportValidity())) return;
    const pin = $("override-pin").value;
    if (!pin) return status("Enter the override PIN to save changes.", true);
    const body = JSON.stringify({revision, facts: extraction.facts, family_role: $("review-role").value, pin});
    setBusy(true);
    try {
      const data = await api(`/api/assessments/${draftId}/override`, {method: "POST", headers: {"Content-Type": "application/json"}, body});
      loadDraft(data);
      status("Manual overrides saved. Confirm the saved review to generate family JSON.");
    } catch (error) {status(error.message, true);} finally {$("override-pin").value = ""; setBusy(false);}
  });
  $("reload-review").addEventListener("click", async () => {
    if (busy || !draftId) return;
    setBusy(true);
    try {loadDraft(await api(`/api/assessments/${draftId}`)); status("Saved review reloaded.");}
    catch (error) {status(error.message, true);} finally {setBusy(false);}
  });
  $("upload-form").addEventListener("submit", async event => {
    event.preventDefault(); if (busy) return;
    const files = [...$("reports").files];
    if (files.length > 3 || files.some(file => !file.name.toLowerCase().endsWith(".pdf"))) return status("Choose up to 3 PDF files.", true);
    if (files.reduce((sum, file) => sum + file.size, 0) > 24 * 1024 * 1024) return status("The combined upload must not exceed 24 MiB.", true);
    const form = new FormData($("upload-form"));
    clearResult(); extraction = null; $("review-section").hidden = true;
    setBusy(true); status("Reading report text and charts. This may take a few minutes…");
    try {
      const data = await api("/api/assessments/extract", {method: "POST", body: form});
      loadDraft(data);
      status("Extraction complete. Review the facts and any missing information below.");
      $("review-section").scrollIntoView({behavior: "smooth", block: "start"});
    } catch (error) {status(error.message, true);} finally {setBusy(false);}
  });
  $("reviewed").addEventListener("change", () => {$("generate-button").disabled = busy || dirty || !$("reviewed").checked;});
  $("review-form").addEventListener("submit", async event => {
    event.preventDefault(); if (busy || dirty || !extraction || !$("reviewed").checked) return;
    const body = JSON.stringify({draft_id: draftId, revision, reviewed: true});
    clearResult(); setBusy(true); status("Writing family-oriented language while preserving your reviewed assessment facts…");
    try {
      result = await api("/api/assessments/generate", {method: "POST", headers: {"Content-Type": "application/json"}, body});
      $("use-persona").hidden = !result.ready_for_debrief;
      $("result-badge").textContent = result.ready_for_debrief ? "Debrief-ready" : "Incomplete draft";
      $("result-badge").classList.toggle("draft", !result.ready_for_debrief);
      $("result-note").textContent = result.ready_for_debrief
        ? "Validated against the persona schema. Review the family language, then save this profile to the app or download the JSON. Saving adds a new family member without replacing an existing profile."
        : `This draft is not valid for the debrief engine. Missing: ${result.missing_fields.map(human).join(", ")}. Complete those fields above and regenerate to produce a debrief-ready file.`;
      $("download-json").textContent = result.ready_for_debrief ? "Download persona JSON" : "Download draft JSON";
      $("family-overview").textContent = result.persona.integrated.overview;
      $("json-preview").textContent = JSON.stringify(result.persona, null, 2);
      $("result-section").hidden = false;
      status(result.ready_for_debrief ? "Family persona generated and validated." : "Family draft generated. Missing scores remain unknown.");
      $("result-section").scrollIntoView({behavior: "smooth", block: "start"});
    } catch (error) {status(error.message, true);} finally {setBusy(false);}
  });
  $("use-persona").addEventListener("click", async () => {
    if (busy || dirty || !result?.ready_for_debrief) return;
    setBusy(true);
    try {
      const data = await api("/api/assessments/use", {method: "POST", headers: {"Content-Type": "application/json"},
        body: JSON.stringify({draft_id: draftId, revision, reviewed: true})});
      window.location.href = `/debrief?file=${encodeURIComponent(data.file)}`;
    } catch (error) {status(error.message, true);} finally {setBusy(false);}
  });
  $("download-json").addEventListener("click", () => {
    if (!result) return;
    const name = (result.persona.person.display_name || "persona").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "persona";
    download(result.persona, `${name}${result.ready_for_debrief ? "" : ".draft"}.json`);
  });
  $("download-extraction").addEventListener("click", () => {
    if (extraction && !dirty) download({...extraction, family_role: $("review-role").value}, "reviewed-assessment.json");
  });
  $("copy-json").addEventListener("click", async () => {
    if (!result) return;
    try {await navigator.clipboard.writeText(JSON.stringify(result.persona, null, 2)); status("JSON copied.");}
    catch {status("Clipboard access is unavailable. Use Download JSON instead.", true);}
  });
  async function restoreDraft() {
    let saved;
    try {saved = sessionStorage.getItem("xq-assessment-draft");} catch {return;}
    if (!saved) return;
    setBusy(true);
    try {loadDraft(await api(`/api/assessments/${encodeURIComponent(saved)}`)); status("Your last saved review has been restored.");}
    catch {try {sessionStorage.removeItem("xq-assessment-draft");} catch {}}
    finally {setBusy(false);}
  }
  restoreDraft();
})();
