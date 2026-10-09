// All Is Well AI frontend. Plain JS; talks only to this app's own API (no CDNs, no external calls).
const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const aud = (n) => (n == null ? "" : "A$" + Number(n).toLocaleString("en-AU", { maximumFractionDigits: 0 }));
const SRC = { zoho_crm: "Zoho CRM", zoho_projects: "Zoho Projects", zoho_books: "Zoho Books", hubspot: "HubSpot", clickup: "ClickUp", bamboohr: "BambooHR" };
const srcName = (s) => SRC[s] || String(s).replace("import:", "Import: ");
const ENT = { company: "Companies", contact: "Contacts", deal: "Deals", project: "Projects", task: "Tasks", invoice: "Invoices", lead: "Leads", employee: "People", note: "Notes", record: "Imported" };
let S = { labels: {}, status: null };

function st(s) {
  if (!s) return "";
  const v = String(s).toLowerCase();
  const cls = /paid|closed won|^closed$|complete|connected|pushed|active|^ok$/.test(v) ? "good"
    : /overdue|lost|shut ?down|failed|error/.test(v) ? "bad"
    : /unpaid|progress|review|proposal|negotiation|queued|outage|offline|hold|to do|open/.test(v) ? "mid" : "blue";
  return `<span class="st ${cls}">${esc(s)}</span>`;
}
function ago(iso) {
  if (!iso) return "never";
  const m = Math.round((Date.now() - new Date(iso).getTime()) / 60000);
  if (m < 1) return "just now";
  if (m < 60) return `${m} min ago`;
  const h = Math.round(m / 60);
  return h < 48 ? `${h} hour${h === 1 ? "" : "s"} ago` : `${Math.round(h / 24)} days ago`;
}
function toast(msg, ms = 3800) { const t = $("#toast"); t.textContent = msg; t.classList.remove("hidden"); clearTimeout(t._h); t._h = setTimeout(() => t.classList.add("hidden"), ms); }
async function api(path, opts = {}) {
  const r = await fetch(path, { headers: { "Content-Type": "application/json" }, ...opts });
  if (!r.ok) { let d = {}; try { d = await r.json(); } catch {} throw new Error(d.detail || r.statusText); }
  return r.json();
}
const post = (path, body) => api(path, { method: "POST", body: JSON.stringify(body || {}) });
async function stream(path, body, onEvent) {
  const r = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  if (!r.ok) { let d = {}; try { d = await r.json(); } catch {} onEvent({ type: "error", message: d.detail || r.statusText, fix: "" }); return; }
  const reader = r.body.getReader(); const dec = new TextDecoder(); let buf = "";
  for (;;) {
    const { value, done } = await reader.read(); if (done) break;
    buf += dec.decode(value, { stream: true });
    let i; while ((i = buf.indexOf("\n")) >= 0) { const line = buf.slice(0, i).trim(); buf = buf.slice(i + 1); if (line) onEvent(JSON.parse(line)); }
  }
}

// ---------- citations: [INV-2042], [TK-07, CO-05] -> clickable ----------
const ID = "[A-Z]{2,3}-\\d+";
const REF_RE = new RegExp(`\\[(${ID}(?:\\s*[,;]\\s*${ID})*)\\]`, "g");
function citedIds(text) { const ids = []; for (const m of text.matchAll(REF_RE)) m[1].split(/[,;]/).map((x) => x.trim()).forEach((x) => ids.includes(x) || ids.push(x)); return ids; }
const chip = (id) => `<button class="chip" data-ref="${esc(id)}">${esc(S.labels[id] || id)}</button>`;
function inlineMd(s) {
  return esc(s).replace(/\*\*(.+?)\*\*/g, "<b>$1</b>")
    .replace(REF_RE, (_, ids) => ids.split(/[,;]/).map((x) => `<button class="ref" data-ref="${x.trim()}">${x.trim()}</button>`).join(" "));
}
function renderMd(text) {
  const out = []; let list = false;
  for (const raw of text.split("\n")) {
    const line = raw.trim(); const li = line.match(/^([-*•]|\d+\.)\s+(.*)/);
    if (li) { if (!list) { out.push("<ul>"); list = true; } out.push(`<li>${inlineMd(li[2])}</li>`); continue; }
    if (list) { out.push("</ul>"); list = false; }
    if (!line) continue;
    const h = line.match(/^#{1,4}\s+(.*)/) || line.match(/^\*\*(.+)\*\*:?$/);
    out.push(h ? `<h3>${inlineMd(h[1])}</h3>` : `<p>${inlineMd(line)}</p>`);
  }
  if (list) out.push("</ul>");
  return out.join("");
}
const errorHtml = (ev) => `<div class="err"><b>${esc(ev.message)}</b><br>${esc(ev.fix || "").replace(/`([^`]+)`/g, "<code>$1</code>")}</div>`;
document.addEventListener("click", (e) => {
  const b = e.target.closest("[data-ref]"); if (b && !e.target.closest("button[data-act]")) openRecord(b.dataset.ref);
  if (e.target.matches("[data-close]")) e.target.closest("dialog").close();
});
document.querySelectorAll("dialog").forEach((d) => d.addEventListener("click", (e) => { if (e.target === d) d.close(); }));

// ---------- navigation ----------
const loaders = { ask: loadTiles, connections: loadConnections, vault: loadVault, changes: loadChanges, export: loadExport };
function show(view) {
  document.querySelectorAll(".sidebar button").forEach((b) => b.classList.toggle("active", b.dataset.view === view));
  document.querySelectorAll(".view").forEach((v) => v.classList.toggle("hidden", v.id !== "view-" + view));
  (loaders[view] || (() => {}))();
}
document.querySelectorAll(".sidebar button").forEach((b) => b.addEventListener("click", () => show(b.dataset.view)));
const current = () => document.querySelector(".sidebar button.active").dataset.view;

// ---------- status ----------
async function refreshStatus() {
  let s; try { s = await api("/api/status"); } catch { return; }
  const prev = S.status; S.status = s;
  const unreachable = s.connections.filter((c) => !["connected", "never synced"].includes(c.state));
  const degraded = !s.internet || unreachable.length > 0;
  document.body.classList.toggle("degraded", degraded);
  $("#netPill").className = "pill " + (s.internet ? "ok" : "warn");
  $("#netText").textContent = s.internet ? "Online" : "No internet";
  $("#vaultChip").textContent = `Vault: ${s.vault.total} records · ${s.vault.size_mb} MB · synced ${ago(s.last_synced_at)}`;
  $("#modelName").textContent = s.llm_model;
  $("#netToggle").checked = s.simulated_offline;
  $("#bizName").textContent = s.business;
  const b = $("#banner");
  if (!s.internet) { b.innerHTML = "<b>Offline mode:</b> no internet, so no cloud platform is reachable. Everything still works from your local vault and the AI on this computer. Changes wait in Pending changes."; }
  else if (unreachable.length) {
    const names = unreachable.map((c) => `${c.name} (${c.state === "shutdown" ? "shut down" : c.state})`).join(", ");
    b.innerHTML = `<b>Continuity mode:</b> ${esc(names)} unreachable. Their data is safe in your local vault, and the AI keeps answering from it.`;
  }
  b.classList.toggle("hidden", !degraded);
  $("#downBadge").textContent = unreachable.length; $("#downBadge").classList.toggle("hidden", !unreachable.length || !s.internet);
  $("#queuedBadge").textContent = s.queued; $("#queuedBadge").classList.toggle("hidden", !s.queued);
  $("#dSend").textContent = s.internet ? "Send" : "Queue to send later";
  const w = $("#ollamaWarn");
  if (s.ollama === "not running") { w.innerHTML = "<b>The local AI (Ollama) isn't running.</b> Open the Ollama app or run <code>ollama serve</code>. The vault still works."; w.classList.remove("hidden"); }
  else if (s.ollama === "model missing") { w.innerHTML = `<b>AI model not downloaded.</b> Run <code>ollama pull ${esc(s.llm_model)}</code> and <code>ollama pull ${esc(s.embed_model)}</code>.`; w.classList.remove("hidden"); }
  else w.classList.add("hidden");
  if (prev && prev.queued > 0 && s.queued < prev.queued) toast(`${prev.queued - s.queued} pending change(s) pushed back to the platforms.`);
  const v = current();
  if (v === "connections") renderConnections(s);
  if (v === "changes" && prev && prev.queued !== s.queued) loadChanges();
}
$("#netToggle").addEventListener("change", async (e) => { await post("/api/internet-off", { on: e.target.checked }); refreshStatus(); });

// ---------- Ask ----------
const SAMPLES = ["Which clients owe us money?", "Why hasn't Thames Fintech paid?", "What is Migs working on this week?",
  "What's the status of the Harbourline Realty website?", "Which deals are closing soon?", "Who is our SEO lead and how do I reach her?"];
$("#suggestions").innerHTML = SAMPLES.map((q) => `<button>${esc(q)}</button>`).join("");
$("#suggestions").addEventListener("click", (e) => { if (e.target.tagName === "BUTTON") ask(e.target.textContent); });
$("#askForm").addEventListener("submit", (e) => { e.preventDefault(); const q = $("#askInput").value.trim(); if (q) ask(q); });

async function ask(q) {
  $("#askInput").value = ""; $("#askBtn").disabled = true;
  $("#chat").insertAdjacentHTML("beforeend", `<div class="msg-q">${esc(q)}</div>`);
  const a = document.createElement("div"); a.className = "msg-a";
  a.innerHTML = `<div class="body typing"><span class="muted">Searching your vault on this computer…</span></div>`;
  $("#chat").appendChild(a); a.scrollIntoView({ behavior: "smooth", block: "end" });
  const body = a.querySelector(".body"); let text = "", sources = [];
  await stream("/api/ask", { question: q }, (ev) => {
    if (ev.type === "sources") { sources = ev.ids; Object.assign(S.labels, ev.labels); }
    else if (ev.type === "token") { text += ev.text; body.innerHTML = renderMd(text); }
    else if (ev.type === "error") { body.classList.remove("typing"); body.innerHTML = errorHtml(ev); }
    else if (ev.type === "done") {
      body.classList.remove("typing");
      let ids = citedIds(text).filter((i) => S.labels[i]); if (!ids.length) ids = sources.slice(0, 3);
      a.insertAdjacentHTML("beforeend", `<div class="chips">${ids.map(chip).join("")}</div>
        <div class="meta"><span>From your local vault, last synced ${ago(ev.last_synced_at)}.</span>
        <span>Answered on this computer by ${esc(ev.model)} in ${ev.seconds}s${ev.internet ? "" : " · no internet used"}</span></div>`);
    }
  });
  $("#askBtn").disabled = false; a.scrollIntoView({ behavior: "smooth", block: "end" });
}

async function loadTiles() {
  const [s, inv, tasks] = await Promise.all([api("/api/status"), api("/api/records?entity=invoice"), api("/api/records?entity=task")]);
  const today = new Date().toLocaleDateString("en-CA");
  const od = inv.filter((i) => i.status === "overdue");
  const due = tasks.filter((t) => t.due_date === today && !/closed|complete/i.test(t.status));
  const up = s.connections.filter((c) => c.state === "connected").length;
  $("#tiles").innerHTML = [
    ["Records in your vault", s.vault.total, `from ${Object.keys(s.vault.by_source).length} sources`, ""],
    ["Platforms reachable", `${up} / ${s.connections.length}`, up < s.connections.length ? "vault still has everything" : "all connected", up < s.connections.length ? "warn" : ""],
    ["Overdue invoices", aud(od.reduce((a, i) => a + i.amount, 0)), `${od.length} invoices`, "bad"],
    ["Tasks due today", due.length, due.slice(0, 2).map((t) => t.title).join(", ") || "None", ""],
  ].map(([k, v, sub, cls]) => `<div class="tile ${cls}"><div class="k">${k}</div><div class="v">${esc(v)}</div><div class="muted small">${esc(sub)}</div></div>`).join("");
}

// ---------- Continuity report ----------
$("#reportBtn").addEventListener("click", async () => {
  $("#reportBtn").disabled = true;
  const dateStr = new Date().toLocaleDateString("en-AU", { weekday: "long", day: "numeric", month: "long", year: "numeric" });
  $("#reportOut").innerHTML = `<div class="card"><div class="card-head"><h2>Continuity report · ${dateStr}</h2>
    <span class="noprint"><button class="btn ghost small" id="copyRep">Copy</button> <button class="btn ghost small" onclick="window.print()">Print</button></span></div>
    <div id="repAi" class="typing"><span class="muted">Reading the vault…</span></div><div id="repFacts" class="facts-grid"></div>
    <div class="muted small" id="repMeta"></div></div>`;
  let text = "";
  await stream("/api/report", {}, (ev) => {
    if (ev.type === "facts") { Object.assign(S.labels, ev.labels); $("#repFacts").innerHTML = factsHtml(ev.facts); $("#repAi").innerHTML = `<span class="muted">Writing the report on this computer…</span>`; }
    else if (ev.type === "token") { text += ev.text; $("#repAi").innerHTML = renderMd(text); }
    else if (ev.type === "error") { $("#repAi").classList.remove("typing"); $("#repAi").innerHTML = errorHtml(ev) + `<p class="muted">The facts below are exact; they come straight from the vault.</p>`; }
    else if (ev.type === "done") { $("#repAi").classList.remove("typing"); $("#repMeta").textContent = `Written locally in ${ev.seconds}s from the vault. No cloud service used.`; }
  });
  $("#copyRep").addEventListener("click", () => navigator.clipboard?.writeText(`Continuity report · ${dateStr}\n\n${text}\n\n${$("#repFacts").innerText}`).then(() => toast("Report copied.")));
  $("#reportBtn").disabled = false;
});
function factsHtml(f) {
  const sec = (title, items, fn, max = 6) => `<div><h3>${title}</h3><ul>${items.length ? items.slice(0, max).map(fn).join("") +
    (items.length > max ? `<li class="muted">+ ${items.length - max} more</li>` : "") : "<li class='muted'>None</li>"}</ul></div>`;
  const task = (r) => `<li>${chip(r.uid)} ${esc(r.person || "")} · due ${esc(r.due_date)}</li>`;
  const inv = (r) => `<li>${chip(r.uid)} ${esc(r.company)} · <b>${aud(r.amount)}</b> · due ${esc(r.due_date)}</li>`;
  return sec("Platforms", f.connections, (c) => `<li>${esc(c.name)} ${st(c.state)} · ${c.records} records saved · last sync ${ago(c.last_success_at)}</li>`, 8) +
    sec("Due today", f.tasks_today, task) + sec("Overdue tasks", f.tasks_late, task) +
    sec(`Overdue invoices · <span class="total">${aud(f.overdue_total)}</span>`, f.overdue, inv) +
    sec(`Invoices due this week · <span class="total">${aud(f.due_soon_total)}</span>`, f.due_soon, inv) +
    sec(`Deals closing in 14 days · <span class="total">${aud(f.deals_total)}</span>`, f.deals, (r) => `<li>${chip(r.uid)} ${aud(r.amount)} · ${esc(r.status)}</li>`) +
    sec("Hot leads", f.leads, (r) => `<li>${chip(r.uid)}</li>`) +
    sec("Key contacts", f.contacts, (r) => `<li>${chip(r.uid)} ${esc(r.company)} · ${esc(r.email || "")}</li>`);
}

// ---------- Connections ----------
async function loadConnections() {
  renderConnections(await api("/api/status"));
  const runs = await api("/api/sync-runs");
  $("#syncLog").innerHTML = `<table><thead><tr><th>When</th><th>Platform</th><th>Result</th><th>Details</th></tr></thead><tbody>${
    runs.slice(0, 18).map((r) => `<tr><td class="small">${new Date(r.started_at).toLocaleTimeString()}</td><td>${esc(srcName(r.source))}</td><td>${st(r.status)}</td><td class="small">${esc(r.message)}</td></tr>`).join("")}</tbody></table>`;
}
function renderConnections(s) {
  const label = { connected: "Connected", outage: "Outage", shutdown: "Shut down", offline: "No internet", error: "Error" };
  $("#connCards").innerHTML = s.connections.map((c) => `
    <div class="conn ${c.state === "outage" || c.state === "offline" ? "down" : c.state === "shutdown" ? "gone" : ""}">
      <div class="top"><span class="nm">${esc(c.name)}</span>${st(label[c.state] || c.state)}</div>
      <div class="muted small">${esc(c.what)}</div>
      <div class="facts"><div><b>${c.records}</b>records in vault</div><div><b>${ago(c.last_success_at)}</b>last good sync</div></div>
      ${c.state !== "connected" && c.error ? `<div class="small err">${esc(c.error)}</div>` : ""}
      <div class="demo">Demo switch:
        <span class="seg" data-src="${c.source}">${[["up", "Up", ""], ["down", "Outage", "warn"], ["shutdown", "Shut down", "bad"]].map(([v, t, cls]) =>
          `<button data-act="1" data-v="${v}" class="${c.switch === v ? "on " + cls : ""}">${t}</button>`).join("")}</span></div>
    </div>`).join("") + (s.imports.length ? s.imports.map((i) => `<div class="conn"><div class="top"><span class="nm">${esc(srcName(i.source))}</span>${st("Imported")}</div>
      <div class="facts"><div><b>${i.records}</b>records in vault</div></div><div class="muted small">Added with AI import; no live connector needed.</div></div>`).join("") : "");
}
$("#connCards").addEventListener("click", async (e) => {
  const b = e.target.closest("button[data-v]"); if (!b) return;
  const src = b.closest(".seg").dataset.src;
  b.closest(".seg").querySelectorAll("button").forEach((x) => (x.disabled = true));
  const r = await post(`/api/platform/${src}`, { status: b.dataset.v });
  toast(r.status === "ok" ? `${SRC[src]} is back. Synced: ${r.message}` : `${SRC[src]}: ${r.message} Your data is safe in the vault.`);
  loadConnections(); refreshStatus();
});
$("#syncBtn").addEventListener("click", async () => {
  $("#syncBtn").disabled = true; $("#syncBtn").textContent = "Syncing…";
  try { const r = await post("/api/sync"); const ch = r.results.reduce((a, x) => a + (x.created || 0) + (x.updated || 0), 0); toast(`Sync finished: ${ch} new or changed record(s).`); }
  catch (e) { toast(e.message); }
  $("#syncBtn").disabled = false; $("#syncBtn").textContent = "Sync now"; loadConnections(); refreshStatus();
});
$("#activityBtn").addEventListener("click", async () => { const r = await post("/api/platform-activity"); toast(r.message + " Press Sync now to pull it in.", 5000); });

// ---------- Vault ----------
let VF = { entity: "", source: "", q: "" };
async function loadVault() {
  const s = S.status || (await api("/api/status"));
  $("#entityChips").innerHTML = [["", "All"], ...Object.keys(s.vault.by_entity).sort().map((e) => [e, `${ENT[e] || e} ${s.vault.by_entity[e]}`])]
    .map(([e, t]) => `<button data-e="${e}" class="${VF.entity === e ? "on" : ""}">${esc(t)}</button>`).join("");
  $("#sourceSel").innerHTML = `<option value="">All sources</option>` + Object.keys(s.vault.by_source).map((x) => `<option value="${esc(x)}" ${VF.source === x ? "selected" : ""}>${esc(srcName(x))}</option>`).join("");
  const p = new URLSearchParams(VF);
  const rows = await api("/api/records?" + p);
  $("#vaultTable").innerHTML = rows.length ? `<table><thead><tr><th>ID</th><th>Record</th><th>Company</th><th>Person</th><th>Status</th><th>Amount</th><th>Date</th><th>Source</th></tr></thead><tbody>${
    rows.map((r) => `<tr data-ref="${esc(r.uid)}"><td><b>${esc(r.uid)}</b></td><td>${esc(r.title)}${r.version > 1 ? ` <span class="muted small">v${r.version}</span>` : ""}${r.local_edit ? ` <span class="tag-local">edited offline</span>` : ""}</td>
      <td>${esc(r.company || "")}</td><td class="small">${esc(r.person || "")}</td><td>${st(r.status)}</td><td class="num">${aud(r.amount)}</td>
      <td class="small">${esc(r.due_date || "")}</td><td class="src">${esc(srcName(r.source))}</td></tr>`).join("")}</tbody></table>` : `<p class="muted">Nothing matches.</p>`;
}
$("#entityChips").addEventListener("click", (e) => { const b = e.target.closest("button"); if (b) { VF.entity = b.dataset.e; loadVault(); } });
$("#sourceSel").addEventListener("change", (e) => { VF.source = e.target.value; loadVault(); });
let _vs; $("#vaultSearch").addEventListener("input", (e) => { clearTimeout(_vs); _vs = setTimeout(() => { VF.q = e.target.value; loadVault(); }, 250); });

// ---------- record modal ----------
async function openRecord(uid) {
  let d; try { d = await api("/api/record/" + encodeURIComponent(uid)); } catch (e) { return toast(e.message); }
  const r = d.record; S.labels[r.uid] = r.label;
  d.related.forEach((x) => (S.labels[x.uid] = S.labels[x.uid] || `${x.uid} · ${x.title}`));
  const pairs = [["Type", esc(ENT[r.entity] || r.entity)], ["Source", `${esc(r.source_name)} <span class="muted small">(id ${esc(r.source_id)})</span>`]];
  if (r.company) pairs.push(["Company", esc(r.company)]);
  if (r.person) pairs.push([r.entity === "task" ? "Assigned to" : "Person / owner", esc(r.person)]);
  if (r.status) pairs.push(["Status", st(r.status) + (r.local_edit ? ` <span class="tag-local">edited offline, waiting to push</span>` : "")]);
  if (r.amount != null) pairs.push(["Amount", `<b>${aud(r.amount)}</b>`]);
  if (r.due_date) pairs.push([r.entity === "deal" ? "Closing" : r.entity === "note" ? "Date" : "Due", esc(r.due_date)]);
  if (r.email) pairs.push(["Email", esc(r.email)]);
  if (r.phone) pairs.push(["Phone", esc(r.phone)]);
  if (r.summary) pairs.push(["Details", esc(r.summary)]);
  pairs.push(["Saved locally", `${ago(r.last_synced_at)} · version ${r.version}`]);
  const acts = [];
  if (["company", "contact", "lead"].includes(r.entity) || (r.entity === "invoice" && r.status !== "paid"))
    acts.push(`<button class="btn" data-act="draft">✎ ${r.entity === "invoice" ? "Draft a payment reminder" : "Draft an email"}</button>`);
  if (r.entity === "task") acts.push(/closed|complete/i.test(r.status) ? `<button class="btn ghost" data-act="reopen">Reopen task</button>` : `<button class="btn" data-act="done">✓ Mark done</button>`);
  if (r.entity === "company") acts.push(`<button class="btn ghost" data-act="note">Add a note</button>`);
  $("#recordBody").innerHTML = `<div class="modal-head"><h2>${esc(r.label)}</h2><button class="x" data-close>×</button></div>
    <div class="kv">${pairs.map(([k, v]) => `<div>${k}</div><div>${v}</div>`).join("")}</div>
    ${d.related.length ? `<h3 class="small muted" style="margin:16px 0 4px">RELATED IN THE VAULT</h3><div class="chips">${d.related.map((x) => `<button class="chip" data-ref="${x.uid}">${esc(x.uid)} · ${esc(x.title.slice(0, 40))}${x.amount ? " · " + aud(x.amount) : ""}</button>`).join("")}</div>` : ""}
    ${d.versions.length ? `<details><summary>Version history (${d.versions.length} earlier version${d.versions.length > 1 ? "s" : ""})</summary>${d.versions.map((v) => `<p class="small"><b>v${v.version}</b> replaced ${ago(v.replaced_at)}: ${esc(v.summary || "")}</p>`).join("")}</details>` : ""}
    <details><summary>Original data from ${esc(r.source_name)}</summary><pre class="raw">${esc(JSON.stringify(r.raw, null, 2))}</pre></details>
    ${acts.length ? `<div class="row"><span class="spacer"></span>${acts.join("")}</div>` : ""}`;
  $("#recordBody").querySelectorAll("[data-act]").forEach((b) => b.addEventListener("click", async () => {
    const a = b.dataset.act;
    if (a === "draft") { $("#recordModal").close(); openDraft(r.uid); }
    if (a === "note") { $("#recordModal").close(); openNote(r); }
    if (a === "done" || a === "reopen") {
      const c = await post("/api/changes/task-status", { uid: r.uid, status: a === "done" ? "done" : "open" });
      toast(c.status === "Pushed" ? "Done, and updated in " + srcName(r.source) + "." : `Saved in the vault. ${srcName(r.source)} is unreachable, so the change is queued and will push automatically.`, 5000);
      openRecord(r.uid); refreshStatus();
    }
  }));
  if (!$("#recordModal").open) $("#recordModal").showModal();
}

// ---------- drafting + notes ----------
let DRAFT = {};
function openDraft(uid) { DRAFT = { uid }; $("#dTo").value = ""; $("#dSubject").value = ""; $("#dBody").value = ""; $("#draftModal").showModal(); runDraft(); }
async function runDraft() {
  $("#dSend").disabled = $("#dRegen").disabled = true; $("#dBody").value = ""; $("#dState").textContent = "· writing on this computer…";
  await stream("/api/draft", { uid: DRAFT.uid }, (ev) => {
    if (ev.type === "meta") { $("#dTo").value = ev.to; $("#dSubject").value = ev.subject; }
    else if (ev.type === "token") { $("#dBody").value += ev.text; $("#dBody").scrollTop = 1e6; }
    else if (ev.type === "error") $("#dBody").value = `${ev.message}\n${ev.fix}`;
  });
  $("#dState").textContent = "· edit freely before sending"; $("#dSend").disabled = $("#dRegen").disabled = false;
}
$("#dRegen").addEventListener("click", runDraft);
$("#dSend").addEventListener("click", async () => {
  const c = await post("/api/changes/email", { to: $("#dTo").value, subject: $("#dSubject").value, body: $("#dBody").value, uid: DRAFT.uid });
  $("#draftModal").close();
  toast(c.status === "Pushed" ? "Sent (simulated for the demo)." : "No internet: email queued. It sends automatically when you're back online.", 5000);
  refreshStatus(); show("changes");
});
let NOTE = null;
function openNote(r) { NOTE = r; $("#noteTitle").textContent = `Add a note to ${r.title}`; $("#noteBody").value = ""; $("#noteModal").showModal(); }
$("#noteSave").addEventListener("click", async () => {
  if (!$("#noteBody").value.trim()) return;
  const c = await post("/api/changes/note", { uid: NOTE.uid, content: $("#noteBody").value.trim() });
  $("#noteModal").close();
  toast(c.status === "Pushed" ? "Note saved to Zoho CRM." : "Zoho CRM is unreachable: note queued and will be added automatically.", 5000);
  refreshStatus();
});

// ---------- Pending changes ----------
async function loadChanges() {
  const rows = await api("/api/changes");
  $("#changesTable").innerHTML = rows.length ? `<table><thead><tr><th>Change</th><th>Platform</th><th>Status</th><th>Made</th><th>Pushed</th></tr></thead><tbody>${
    rows.map((c) => `<tr ${c.uid ? `data-ref="${esc(c.uid)}"` : ""}><td>${esc(c.description)}${c.error ? `<div class="small err">${esc(c.error)}</div>` : ""}</td><td class="src">${esc(c.source === "email" ? "Email" : srcName(c.source))}</td>
      <td>${st(c.status)}</td><td class="small">${new Date(c.created_at).toLocaleTimeString()}</td><td class="small">${c.pushed_at ? new Date(c.pushed_at).toLocaleTimeString() : "waiting"}</td></tr>`).join("")}</tbody></table>`
    : `<p class="muted">No changes yet. Open a task and mark it done, add a note to a company, or draft an email while a platform is down.</p>`;
}

// ---------- AI import ----------
let IMP = null;
async function preview(filename, content) {
  $("#importOut").innerHTML = `<p class="muted typing">Reading ${esc(filename)} and asking the local AI what the columns mean…</p>`;
  let p; try { p = await post("/api/import/preview", { filename, content }); } catch (e) { $("#importOut").innerHTML = `<p class="err">${esc(e.message)}</p>`; return; }
  IMP = { filename, content, ...p };
  const opt = (sel) => `<option value="">(not used)</option>` + p.headers.map((h) => `<option ${h === sel ? "selected" : ""}>${esc(h)}</option>`).join("");
  $("#importOut").innerHTML = `<div class="card"><div class="card-head"><h2>${esc(filename)} · ${p.rows} rows</h2><span class="ai-badge">Mapped by ${esc(p.by)}</span></div>
    <div class="field"><label>These rows are</label><select id="impEntity">${p.entities.map((e) => `<option value="${e}" ${e === p.entity ? "selected" : ""}>${ENT[e] || e}</option>`).join("")}</select></div>
    <table class="map-table"><thead><tr><th>Vault field</th><th>Column in your file</th><th>Example</th></tr></thead><tbody>${
      p.fields.map((f) => `<tr><td>${f.replace("_", " ")}</td><td><select data-f="${f}">${opt(p.map[f])}</select></td><td class="small muted" data-ex="${f}">${esc(p.map[f] ? p.sample[0][p.map[f]] : "")}</td></tr>`).join("")}</tbody></table>
    <p class="small muted">Columns you don't map are kept too: they go into the record's details and its original data.</p>
    <div class="row"><span class="spacer"></span><button class="btn" id="impGo">Import ${p.rows} rows into the vault</button></div></div>`;
  $("#importOut").querySelectorAll("select[data-f]").forEach((s) => s.addEventListener("change", () => { $(`[data-ex="${s.dataset.f}"]`).textContent = s.value ? p.sample[0][s.value] : ""; }));
  $("#impGo").addEventListener("click", async () => {
    const mapping = {}; $("#importOut").querySelectorAll("select[data-f]").forEach((s) => s.value && (mapping[s.dataset.f] = s.value));
    const r = await post("/api/import/commit", { filename, content, entity: $("#impEntity").value, mapping });
    $("#importOut").innerHTML = `<div class="card"><h2>Imported into your vault</h2><p>${r.created} new, ${r.updated} updated. You can now ask the AI about them, and they're included in exports.</p>
      <button class="btn ghost" onclick="VF={entity:'',source:'import:${esc(filename)}',q:''};show('vault')">View imported records</button></div>`;
    refreshStatus();
  });
}
async function readFile(f) { preview(f.name, await f.text()); }
$("#fileInput").addEventListener("change", (e) => e.target.files[0] && readFile(e.target.files[0]));
const drop = $("#drop");
drop.addEventListener("dragover", (e) => { e.preventDefault(); drop.classList.add("over"); });
drop.addEventListener("dragleave", () => drop.classList.remove("over"));
drop.addEventListener("drop", (e) => { e.preventDefault(); drop.classList.remove("over"); e.dataTransfer.files[0] && readFile(e.dataTransfer.files[0]); });
$("#sampleBtn").addEventListener("click", async () => preview("pipedrive-deals-export.csv", await (await fetch("/static/samples/pipedrive-deals-export.csv")).text()));

// ---------- Export ----------
async function loadExport() {
  const s = await api("/api/status");
  $("#exportSummary").innerHTML = `<p><b>${s.vault.total} records</b> from ${Object.keys(s.vault.by_source).map(srcName).join(", ")}, plus ${s.vault.versions} earlier versions. Vault size ${s.vault.size_mb} MB, stored on this computer.</p>`;
}

// ---------- boot ----------
refreshStatus().then(loadTiles);
setInterval(refreshStatus, 4000);
