/* app.js — the dashboard renderer.
 *
 * One job: turn the view model the backend returns (onboarding/view_model.py) into
 * the flow the coordinator sees, and turn button clicks back into gate decisions.
 * No framework, no build step — vanilla JS on purpose, so the walkthrough has nothing
 * to explain but the agent design itself.
 *
 * The render is a pure function of the view model: render(view) wipes #dash-body and
 * rebuilds it. Every gate click POSTs, gets a fresh view back, and re-renders. The
 * frontend holds almost no state — the orchestrator on the server is the source of
 * truth. That mirrors the backend design: one engine, the UI just draws it.
 */

const $ = (sel) => document.querySelector(sel);

// --- agent identity icons (match the mockup's color/icon system) ------------------
const ICON = {
  coord: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><circle cx="12" cy="5" r="2"/><circle cx="5" cy="18" r="2"/><circle cx="19" cy="18" r="2"/><path d="M12 7v3.5M12 10.5L6.2 16M12 10.5L17.8 16"/></svg>',
  it:    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><rect x="4" y="5" width="16" height="11" rx="1.5"/><path d="M2 20h20"/></svg>',
  comp:  '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><path d="M14 3H7a1 1 0 00-1 1v16a1 1 0 001 1h10a1 1 0 001-1V7z"/><path d="M14 3v4h4M9 12h6M9 16h5"/></svg>',
  mgr:   '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><circle cx="12" cy="8" r="3.2"/><path d="M5.5 20a6.5 6.5 0 0113 0"/></svg>',
};

// Escape user/agent-supplied text before putting it in innerHTML. The content comes
// from our own agents, but escaping is cheap insurance against a stray < breaking the
// layout — and a clean thing to point at in a security-minded interview.
function esc(s) {
  return String(s == null ? "" : s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

// --- app state (deliberately tiny) ------------------------------------------------
let SESSION_ID = null;
let CURRENT_HIRE = null;
let BUSY = false;
let CURRENT_PENDING = null;   // the gate_type currently awaiting the coordinator
let CURRENT_MANAGER = null;   // the hire's manager name, for the "Contact manager" route
// What the coordinator decided at each gate, kept so the choice (Approve / Edit /
// Request changes) leaves a PERSISTENT, visible trace on the resolved card — instead
// of all three looking the same once the flow moves on.
let DECISIONS = {};           // gate_type -> { action, text }
let LAST_VIEW = null;         // last rendered view, so an in-place edit can re-render without a server round-trip
let EDITED = {};              // gate_type -> edited message text (the coordinator's draft, before they approve & send)

// Which stage card a resolved gate's decision badge belongs on.
const GATE_STAGE = {
  plan_approval: "plan", special_access: "it", escalation: "compliance",
  "30_60_90_signoff": "manager_prep", welcome_message_review: "welcome",
  readiness_at_risk: "readiness",
};

// ==================================================================================
// Boot
// ==================================================================================
async function boot() {
  wireNav();
  $("#live-toggle").addEventListener("change", () => {
    $("#mode-label").classList.toggle("live-on", $("#live-toggle").checked);
    if (CURRENT_HIRE) runProfile(CURRENT_HIRE);
  });
  const sel = $("#profile-select");
  sel.addEventListener("change", () => runProfile(sel.value));

  const data = await fetchJSON("/api/profiles");
  sel.innerHTML = "";
  data.profiles.forEach((p) => {
    const o = document.createElement("option");
    o.value = p.hire_id;
    o.textContent = p.label;
    sel.appendChild(o);
  });
  if (data.profiles.length) runProfile(data.profiles[0].hire_id);
}

function wireNav() {
  document.querySelectorAll("nav button").forEach((b) => {
    b.addEventListener("click", () => {
      document.querySelectorAll("nav button").forEach((x) => x.classList.remove("active"));
      document.querySelectorAll(".view").forEach((v) => v.classList.remove("active"));
      b.classList.add("active");
      document.getElementById(b.dataset.v).classList.add("active");
      window.scrollTo(0, 0);
    });
  });
}

// ==================================================================================
// Run + resolve
// ==================================================================================
async function runProfile(hireId) {
  CURRENT_HIRE = hireId;
  DECISIONS = {};               // fresh run → forget the prior hire's decisions
  EDITED = {};                  // …and any in-progress message edits
  const mode = $("#live-toggle").checked ? "live" : "cached";
  $("#dash-body").innerHTML =
    `<div class="loading"><span class="spin"></span> ${
      mode === "live" ? "Running the agents live (this calls GPT-4o)…" : "Loading…"
    }</div>`;
  const r = await postJSON("/api/run", { hire_id: hireId, mode });
  SESSION_ID = r.session_id;
  render(r.view);
}

// Dispatch a click inside the active gate. Approve/acknowledge resolve immediately;
// Edit opens an editor; Escalate opens the two human-routing options. Edit advances the
// flow (it's an approval of your version); Escalate does NOT — it hands the item to a
// person and leaves the gate open so you can still approve.
function onGateAction(action) {
  switch (action) {
    case "edit-open":      return togglePanel("edit");
    case "escalate-open":  return togglePanel("escalate");
    case "cancel":         return togglePanel(null);
    case "approve": {
      // If the coordinator edited a message first (Manager Prep gate), approving SENDS
      // their edited version — record it as an edit so the card shows "Approved with your edits".
      const e = EDITED[CURRENT_PENDING];
      if (e != null) {
        record("edit", e);
        return resolveGate("edit", { edited_payload: { coordinator_note: e } });
      }
      record("approve");
      return resolveGate("approve");
    }
    case "deny":           record("deny");     return resolveGate("deny");
    case "acknowledge":    record("approve");  return resolveGate("acknowledge");
    case "take_action":    return togglePanel("escalate");
    case "edit-confirm": {
      const t = panelText("edit"); record("edit", t);
      return resolveGate("edit", { edited_payload: { coordinator_note: t } });
    }
    case "edit-save": {
      // Two-step (Manager Prep): save the edited message into the draft and re-render so
      // the coordinator SEES the updated draft, with the gate still open to Approve & send.
      const t = panelText("edit");
      EDITED[CURRENT_PENDING] = t;
      applyEditToView(CURRENT_PENDING, t);
      return render(LAST_VIEW);
    }
    case "escalate-ticket":
      return showRouted(
        "🎫 <b>Servicedesk ticket drafted</b> for this request. In a live system this would " +
        "open a ServiceNow / Jira ticket for the IT team to action. " +
        "<span class='muted'>(Demo — nothing was actually sent. You can still Approve below to continue.)</span>"
      );
    case "escalate-manager":
      return showRouted(
        `✉️ <b>Message drafted to ${esc(CURRENT_MANAGER || "the manager")}</b>. In a live system this ` +
        "would reach them over Slack or email to weigh in. " +
        "<span class='muted'>(Demo — nothing was actually sent. You can still Approve below to continue.)</span>"
      );
  }
}

// Show that the item was handed to a person, WITHOUT advancing the flow. These routes
// are deliberately not wired (the integrations are mocked) — we say so plainly rather
// than fake a result, and leave the gate open so the coordinator can still approve.
function showRouted(message) {
  const gate = document.querySelector(".gate.active");
  if (!gate) return;
  togglePanel(null);
  const prev = gate.querySelector(".routed");
  if (prev) prev.remove();
  const main = gate.querySelector(".gate-main");
  if (main) main.insertAdjacentHTML("beforebegin", `<div class="routed">${message}</div>`);
}

function record(action, text) {
  if (CURRENT_PENDING) DECISIONS[CURRENT_PENDING] = { action, text: (text || "").trim() };
}

// Fold a saved message edit back into the current view so re-rendering shows the updated
// draft (without a server round-trip — the send is mocked, the edit is the coordinator's).
function applyEditToView(gateType, text) {
  if (!LAST_VIEW || !LAST_VIEW.stages) return;
  if (gateType === "30_60_90_signoff") {
    const st = LAST_VIEW.stages.find((s) => s.id === "manager_prep");
    if (st && st.details && st.details.note) {
      st.details.note.body = text;
      st.details.note.edited = true;
    }
  }
}

// Show one of the gate's inline panels (edit / changes) and hide the buttons; pass null
// to restore the buttons. DOM-only — no re-render, so the textarea keeps focus.
function togglePanel(name) {
  const gate = document.querySelector(".gate.active");
  if (!gate) return;
  const main = gate.querySelector(".gate-main");
  if (main) main.hidden = !!name;
  gate.querySelectorAll(".gate-panel").forEach((p) => (p.hidden = p.dataset.panel !== name));
  if (name) {
    const ta = gate.querySelector(`.gate-panel[data-panel="${name}"] textarea`);
    if (ta) ta.focus();
  }
}

function panelText(name) {
  const ta = document.querySelector(`.gate.active .gate-panel[data-panel="${name}"] textarea`);
  return ta ? ta.value : "";
}

async function resolveGate(action, extra) {
  if (BUSY || !SESSION_ID) return;
  BUSY = true;
  markGateWorking();
  const r = await postJSON(`/api/session/${SESSION_ID}/gate`, { action, ...(extra || {}) });
  BUSY = false;
  render(r.view);
}

// ==================================================================================
// Render
// ==================================================================================
function render(view) {
  const root = $("#dash-body");

  // Graceful-failure / expired / error paths — a readable banner, never a crash.
  if (!view || view.ok === false) {
    root.innerHTML = banner(view);
    return;
  }

  LAST_VIEW = view;
  CURRENT_PENDING = view.pending_gate ? view.pending_gate.gate_type : null;
  CURRENT_MANAGER = view.hire ? view.hire.manager : null;
  const parts = [];
  parts.push(hireHeader(view.hire));
  parts.push(`<div class="section-label">Onboarding flow</div>`);
  parts.push(orchBand(view.orchestrator));
  parts.push(renderFlow(view.stages));
  parts.push(legend());
  parts.push(
    `<p class="foot">Content is the real output of the agents.
     Failure states (e.g. a missing start date) surface here as a plain-English message — never a crash.</p>`
  );
  root.innerHTML = parts.join("");

  // Delegate gate-button clicks through the dispatcher.
  root.querySelectorAll("[data-action]").forEach((btn) => {
    btn.addEventListener("click", () => onGateAction(btn.dataset.action));
  });

  // Scroll the pending gate into view so the coordinator's next decision is obvious.
  const active = root.querySelector(".gate.active");
  if (active) active.scrollIntoView({ behavior: "smooth", block: "center" });
}

// Small attribute icons (people / pin / badge / manager) for the profile chips.
const ATTR_ICON = {
  team:     '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><circle cx="9" cy="8" r="3"/><path d="M3.5 19a5.5 5.5 0 0111 0"/><path d="M16 6a3 3 0 010 6M21 19a5.5 5.5 0 00-4-5.3"/></svg>',
  location: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><path d="M12 21s7-5.5 7-11a7 7 0 10-14 0c0 5.5 7 11 7 11z"/><circle cx="12" cy="10" r="2.5"/></svg>',
  employ:   '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><rect x="3" y="7" width="18" height="13" rx="2"/><path d="M8 7V5a2 2 0 012-2h4a2 2 0 012 2v2"/></svg>',
  manager:  '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><circle cx="12" cy="8" r="3.2"/><path d="M5.5 20a6.5 6.5 0 0113 0"/></svg>',
};

// Initials for the avatar, e.g. "Sarah Chen" -> "SC".
function initials(name) {
  return String(name || "").trim().split(/\s+/).map((w) => w[0] || "").slice(0, 2).join("").toUpperCase();
}

// Days from today to the start date — computed in JS so the countdown is live
// (relative to *now*, not to when the run was cached). Returns null if unparseable.
function daysToStart(startStr) {
  const start = new Date(startStr);
  if (isNaN(start.getTime())) return null;
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  start.setHours(0, 0, 0, 0);
  return Math.round((start - today) / 86400000);
}

// Countdown text + urgency class. Closer start = hotter color, so the coordinator
// feels the pressure to finish — the whole point of the product.
function countdown(days) {
  if (days == null) return null;
  let text, cls;
  if (days < 0) { text = `Started ${Math.abs(days)} day${days === -1 ? "" : "s"} ago`; cls = "far"; }
  else if (days === 0) { text = "Starts today"; cls = "soon"; }
  else if (days === 1) { text = "1 day to start"; cls = "soon"; }
  else { text = `${days} days to start`; cls = days <= 3 ? "soon" : days <= 14 ? "mid" : "far"; }
  return { text, cls };
}

function hireHeader(h) {
  if (!h) return "";
  const cd = countdown(daysToStart(h.start_date));
  const cdHtml = cd
    ? `<div class="hc-countdown ${cd.cls}"><span class="dot"></span>${esc(cd.text)}</div>`
    : "";
  const attr = (icon, k, v) =>
    `<div class="hc-attr">${ATTR_ICON[icon]}<span class="k">${k}</span> <b>${esc(v)}</b></div>`;
  return `
    <div class="hirecard">
      <div class="hc-top">
        <div class="hc-id">
          <div class="hc-avatar">${esc(initials(h.name))}</div>
          <div>
            <h2 class="hc-name">${esc(h.name)}</h2>
            <div class="hc-role">${esc(h.role_title)}</div>
          </div>
        </div>
        <div class="hc-start">
          <div class="hc-start-label">Start date</div>
          <div class="hc-start-date">${esc(h.start_date)}</div>
          ${cdHtml}
        </div>
      </div>
      <div class="hc-attrs">
        ${attr("team", "Team", h.team)}
        ${attr("location", "Location", h.location)}
        ${attr("employ", "Type", h.employment)}
        ${attr("manager", "Manager", h.manager)}
      </div>
    </div>`;
}

function orchBand(o) {
  if (!o) return "";
  return `
    <div class="orch">
      <span class="avatar ag-coord">${ICON.coord}</span>
      <div class="grow">
        <div class="ttl"><span class="badge">Assistant</span> Onboarding Assistant</div>
        <div class="ostate">${esc(o.status)}</div>
      </div>
    </div>`;
}

// The flow: connectors + stage cards, with IT + Compliance grouped "in parallel".
function renderFlow(stages) {
  const byId = {};
  stages.forEach((s) => (byId[s.id] = s));
  const out = ['<div class="flow">'];

  // 1. consolidated plan
  out.push(conn("●", "The Assistant built <b>one consolidated plan</b> to approve in a single click, not four."));
  out.push(card(byId.plan));

  // 2. parallel delegation: IT + Compliance
  out.push(conn("↓", "Once approved, IT and Compliance are handed their work <b>at the same time</b>"));
  out.push('<div class="pll-head">⫶ Happening at the same time</div>');
  out.push('<div class="parallel">');
  out.push(card(byId.it, true));
  out.push(card(byId.compliance, true));
  out.push("</div>");

  // 3. handoff IT -> Manager Prep
  out.push(conn("↓", "IT hands its <b>provisioning summary</b> to Manager Prep — so the 30-60-90 references the real tools the hire will have."));
  out.push(card(byId.manager_prep));

  // 4. back to coordinator: welcome
  out.push(conn("↓", "Specialists report back to the <b>Assistant</b>"));
  out.push(card(byId.welcome));

  // 5. readiness safety net
  out.push(conn("↓", "The Assistant schedules a final safety check"));
  out.push(card(byId.readiness));

  out.push("</div>");
  return out.join("");
}

function conn(chev, html) {
  return `<div class="conn"><span class="chev">${chev}</span><span class="note">${html}</span></div>`;
}

// ---------------------------------------------------------------------------------
// A single stage card: avatar + title + summary + pill, then reasoning / details /
// gate. `compact` drops the left indent for the parallel two-column layout.
// ---------------------------------------------------------------------------------
function card(stage, compact) {
  if (!stage) return "";
  const cls = `ag-${stage.agent_class}`;
  const by = stage.agent === "coordinator" ? `<span class="by">· Assistant</span>` : "";
  const p = pill(stage);

  const blocks = [];
  blocks.push(`
    <div class="node">
      <span class="avatar ${cls}">${ICON[stage.agent_class]}</span>
      <div class="grow">
        <div class="t">${esc(stage.title)} ${by}</div>
        <div class="d">${esc(stage.summary)}</div>
      </div>
      <span class="pill ${p.cls}">${esc(p.txt)}</span>
    </div>`);

  // Once a gate is resolved, show what the coordinator decided (approve / edit / send back).
  if (!stage.gate) {
    const badge = decisionBadge(stage.id);
    if (badge) blocks.push(badge);
  }

  // Show the reasoning trace ONLY on the Coordinator's cards (the consolidated plan and
  // the welcome message), where it adds something. On the specialist cards
  // (IT / Compliance / Manager Prep) the structured detail below already enumerates every
  // decision — including the rationale where it matters — so a separate step-by-step "why"
  // list just repeats the same actions in prose. Don't make the coordinator read it twice.
  if (stage.agent === "coordinator" && stage.reasoning && stage.reasoning.length) {
    const reasonLabel = stage.id === "plan" ? "Reason for this plan" : "Why this decision";
    blocks.push(detailsBlock(reasonLabel, `<ol class="why-steps">${
      stage.reasoning.map((s) => `<li>${esc(s)}</li>`).join("")
    }</ol>`, compact));
  }

  const det = renderDetails(stage);
  if (det) {
    // While the Manager Prep gate is pending, open its details so the coordinator can see
    // the draft they're about to review/send (and any edits they just saved) without hunting.
    const openDetails = stage.id === "manager_prep" && !!stage.gate;
    blocks.push(detailsBlock(detailLabel(stage.id), det, compact, openDetails));
  }

  if (stage.gate) blocks.push(gateCard(stage.gate));

  return `<div class="card ${cls}">${blocks.join("")}</div>`;
}

function detailsBlock(summary, innerHtml, compact, open) {
  return `<details class="tr"${open ? " open" : ""}><summary>${esc(summary)}</summary>
    <div class="inner">${innerHtml}</div></details>`;
}

function pill(stage) {
  const txt = {
    pending: "Pending", scheduled: "Scheduled",
    awaiting_approval: {
      plan: "Needs approval", it: "Awaiting you", compliance: "Awaiting you",
      manager_prep: "Ready to send", welcome: "Ready for review",
    }[stage.id] || "Awaiting you",
    complete: {
      plan: "Approved", welcome: "Approved", manager_prep: "Sent to manager",
    }[stage.id] || "Complete",
  }[stage.status] || stage.status;
  const cls = stage.status === "complete" ? "p-done"
    : stage.status === "awaiting_approval" ? "p-wait" : "p-pend";
  return { txt, cls };
}

// ---------------------------------------------------------------------------------
// Gate card — the two HITL shapes. Decision = 3 actions; Alert = 2.
// ---------------------------------------------------------------------------------
function gateCard(gate) {
  const isAlert = gate.shape === "alert";
  // Plain-language labels — the coordinator is non-technical, so no "gate" jargon.
  const tag = isAlert
    ? '<span class="tag tag-alert">Heads-up</span>'
    : '<span class="tag tag-gate">Your approval needed</span>';
  const why = gate.rationale ? `<div class="why">${esc(gate.rationale)}</div>` : "";

  if (isAlert) {
    return `<div class="gate active">
      <div class="gh">${tag} ${esc(gate.summary)}</div>
      ${why}
      <div class="gate-main">
        <div class="btns">
          <button class="btn alt" data-action="acknowledge">Got it</button>
          <button class="btn" data-action="take_action">Take action</button>
        </div>
        <div class="actions-hint">This is a heads-up to act on, not something to approve.</div>
      </div>
    </div>`;
  }

  // Special access is a BINARY decision — grant the access or don't. There's nothing to
  // reword (you can't "edit" an AWS grant), and the coordinator IS the designated approver,
  // so this gate is a clean yes/no: Approve or Deny. Denying doesn't halt onboarding — the
  // hire just doesn't get that grant.
  if (gate.gate_type === "special_access") {
    return `<div class="gate active">
      <div class="gh"><span class="tag tag-gate">Your decision</span> ${esc(gate.summary)}</div>
      ${why}
      <div class="gate-main">
        <div class="btns">
          <button class="btn primary" data-action="approve">Approve — grant access</button>
          <button class="btn deny" data-action="deny">Deny</button>
        </div>
        <div class="actions-hint">Grant this access, or deny it — onboarding continues either way; the hire just won't get this one.</div>
      </div>
    </div>`;
  }

  const manager = CURRENT_MANAGER || "the manager";

  // The Manager Prep gate sends a whole MESSAGE to the manager, so it gets the richer
  // edit experience: the full cover note pre-loaded into a tall editor, and a two-step
  // flow — Save your edits → see the updated draft → Approve & send. The other decision
  // gates keep the lighter one-step "Save & approve".
  const isMP = gate.gate_type === "30_60_90_signoff";

  // Pre-fill the Edit box with the most relevant text for this gate (the whole message
  // for message gates, otherwise the proposed decision) so editing feels real, not a stub.
  let editSeed = gate.proposed_decision || "";
  if (gate.gate_type === "welcome_message_review" && gate.payload &&
      gate.payload.draft && gate.payload.draft.body) {
    editSeed = gate.payload.draft.body;
  }
  if (isMP && gate.payload && gate.payload.note && gate.payload.note.body) {
    editSeed = gate.payload.note.body;
  }
  // If the coordinator already saved edits this session, keep showing THEIR version.
  if (EDITED[gate.gate_type] != null) editSeed = EDITED[gate.gate_type];

  const edited = isMP && EDITED[gate.gate_type] != null;
  const approveLabel = isMP ? (edited ? "Approve &amp; send edited message" : "Approve &amp; send") : "Approve";
  const hint = isMP
    ? `Approve &amp; send the message to ${esc(manager)} · Edit to rewrite it · Escalate to route it to a person`
    : "Approve to continue · Edit to adjust it yourself · Escalate to send it to a person";

  return `<div class="gate active">
      <div class="gh">${tag} ${esc(gate.summary)}</div>
      ${why}
      <div class="gate-main">
        <div class="btns">
          <button class="btn primary" data-action="approve">${approveLabel}</button>
          <button class="btn" data-action="edit-open">${edited ? "Edit again" : "Edit"}</button>
          <button class="btn text" data-action="escalate-open">Escalate</button>
        </div>
        <div class="actions-hint">${hint}</div>
      </div>
      <div class="gate-panel" data-panel="edit" hidden>
        <div class="lbl">${isMP
          ? `Edit the full message to ${esc(manager)}, then save — you'll review the updated draft before sending:`
          : "Adjust this yourself, then approve your version:"}</div>
        <textarea${isMP ? ' class="tall"' : ""}>${esc(editSeed)}</textarea>
        <div class="btns">
          ${isMP
            ? '<button class="btn primary" data-action="edit-save">Save changes</button>'
            : '<button class="btn primary" data-action="edit-confirm">Save &amp; approve</button>'}
          <button class="btn text" data-action="cancel">Cancel</button>
        </div>
      </div>
      <div class="gate-panel" data-panel="escalate" hidden>
        <div class="lbl">This one needs a person — where should it go?</div>
        <div class="btns route-opts">
          <button class="btn route" data-action="escalate-ticket">🎫 Raise a servicedesk ticket</button>
          <button class="btn route" data-action="escalate-manager">✉️ Contact ${esc(manager)}</button>
        </div>
        <div class="btns"><button class="btn text" data-action="cancel">Cancel</button></div>
      </div>
    </div>`;
}

// A persistent badge on a resolved card showing that the coordinator EDITED it — so an
// edit leaves a visible mark instead of looking like a plain approve after the fact.
function decisionBadge(stageId) {
  const gt = Object.keys(DECISIONS).find((k) => GATE_STAGE[k] === stageId);
  if (!gt) return "";
  const d = DECISIONS[gt];
  if (d.action === "edit") {
    const note = d.text ? `: <span>${esc(d.text.length > 140 ? d.text.slice(0, 140) + "…" : d.text)}</span>` : "";
    return `<div class="decided edit">✏️ Approved with your edits${note}</div>`;
  }
  if (d.action === "deny") {
    return `<div class="decided denied">⊘ You denied this — access not granted</div>`;
  }
  // A plain approve needs no badge — the status pill already says "Approved" / "Complete".
  return "";
}

function markGateWorking() {
  const gate = document.querySelector(".gate.active");
  if (!gate) return;
  gate.querySelectorAll("button").forEach((b) => (b.disabled = true));
  const visible = gate.querySelector(".gate-main:not([hidden]) .btns, .gate-panel:not([hidden]) .btns");
  if (visible) visible.insertAdjacentHTML("beforeend", '<span class="spin"></span>');
}

// ---------------------------------------------------------------------------------
// Per-stage detail bodies — render the structured agent output nicely.
// ---------------------------------------------------------------------------------
function detailLabel(id) {
  return {
    plan: "See the onboarding plan",
    it: "Provisioning detail",
    compliance: "Documents & status",
    manager_prep: "Cover note, draft 30-60-90 & checklist",
    welcome: "Read the message",
    readiness: "",
  }[id] || "Details";
}

function renderDetails(stage) {
  const d = stage.details || {};
  switch (stage.id) {
    case "plan":          return planDetails(d);
    case "it":            return itDetails(d);
    case "compliance":    return complianceDetails(d);
    case "manager_prep":  return managerPrepDetails(d);
    case "welcome":       return welcomeDetails(d);
    default:              return "";
  }
}

function planDetails(d) {
  if (!d.sections || !d.sections.length) return "";
  return d.sections.map((s) => `
    <div class="plan-sec">
      <span class="av ag-${s.agent_class}">${ICON[s.agent_class]}</span>
      <div><b>${esc(s.label === "Coordinator" ? "Assistant" : s.label)}</b> ${esc(s.text)}
        ${s.gate ? `<span class="g">${esc(s.gate)}</span>` : ""}</div>
    </div>`).join("");
}

function itDetails(d) {
  const out = [];
  if (d.hardware) {
    out.push(group("Hardware",
      `<div class="kv">${esc(d.hardware.item)} <span class="dr">(${esc(d.hardware.status)})</span></div>`
      + (d.hardware.notes ? `<div class="dr">${esc(d.hardware.notes)}</div>` : "")));
  }
  if (d.software_access && d.software_access.length) {
    out.push(group("Accounts & systems", d.software_access.map((s) =>
      docRow(`${esc(s.system)} — ${esc(s.access_level)}`, esc(s.status))).join("")));
  }
  if (d.security_groups && d.security_groups.length) {
    out.push(group("Security groups",
      d.security_groups.map((g) => `<span class="chip">${esc(g.group)}</span>`).join("")));
  }
  // Special access is NOT listed here on purpose: it lives in the approval card below,
  // which is the single place the coordinator acts on it. Listing it here too just made
  // the same request appear twice.
  if (d.warnings && d.warnings.length) {
    out.push(`<div class="warn">⚠ ${d.warnings.map(esc).join("<br>⚠ ")}</div>`);
  }
  return out.join("");
}

// Translate the document's lifecycle state into plain language for the coordinator.
// The key reassurance: nothing for them to send by hand — it goes out automatically on
// schedule. (The data keeps the precise state; this is just the display.)
function docStatusLabel(status, deadline) {
  const by = deadline ? ` · by ${esc(deadline)}` : "";
  switch (status) {
    case "not_started": return `Sends automatically${by}`;
    case "sent":        return `Sent — awaiting signature${by}`;
    case "in_progress": return `In progress${by}`;
    case "completed":   return `Completed`;
    case "overdue":     return `Overdue — needs attention${by}`;
    default:            return `${esc(status)}${by}`;
  }
}

function complianceDetails(d) {
  const out = [];
  if (d.required_documents && d.required_documents.length) {
    out.push(`<div class="auto-note">✓ These go out automatically at the right time — nothing for you to send.</div>`);
    out.push(group("Required documents", d.required_documents.map((doc) =>
      docRow(`${esc(doc.name)}`, docStatusLabel(doc.status, doc.deadline))).join("")));
  }
  if (d.escalations && d.escalations.length) {
    out.push(group("Escalation", d.escalations.map((e) =>
      `<div class="kv">${esc(e.reason)}</div>
       <div class="dr">Proposed set: ${e.proposed_document_set.map(esc).join(", ")}</div>`).join("")));
  }
  return out.join("");
}

function managerPrepDetails(d) {
  // Lead with WHAT the agent did (3 clear actions), then the package the coordinator
  // reviews and sends: cover note → draft 30-60-90 → checklist.
  const out = [];
  const mgr = d.manager_name || "the manager";
  if (d.actions && d.actions.length) {
    out.push(`<div class="agent-actions">${d.actions.map((a) => {
      const ok = a.status === "done";
      return `<div class="aa-row">
        <span class="aa-ic ${ok ? "ok" : "warn"}">${ok ? "✓" : "!"}</span>
        <div><b>${esc(a.label)}</b>${a.detail ? `<span class="aa-d">${esc(a.detail)}</span>` : ""}</div>
      </div>`;
    }).join("")}</div>`);
  }
  if (d.note) {
    const editedTag = d.note.edited
      ? `<div class="auto-note">✏️ Edited by you — this is the version that will be sent to ${esc(mgr)}.</div>`
      : "";
    out.push(`${editedTag}<div class="welcome-msg${d.note.edited ? " edited" : ""}">
      <div class="to">To ${esc(mgr)}</div>
      <div class="subj">${esc(d.note.subject_line)}</div>
      <div class="body">${esc(d.note.body)}</div>
    </div>`);
  }
  const t = d.thirty_sixty_ninety || {};
  out.push(group(`Draft 30-60-90 — for ${esc(mgr)} to review &amp; make their own`,
    `<div class="cols3">
       ${planCol("First 30", t.thirty_days)}
       ${planCol("Days 30-60", t.sixty_days)}
       ${planCol("Days 60-90", t.ninety_days)}
     </div>`));
  if (d.manager_checklist && d.manager_checklist.length) {
    out.push(group("Manager prep checklist",
      `<ul style="margin:0;padding-left:16px;">${
        d.manager_checklist.map((c) => `<li>${esc(c)}</li>`).join("")}</ul>`));
  }
  return out.join("");
}

function welcomeDetails(d) {
  const sched = d.send_strategy === "schedule"
    ? `Scheduled to send ${esc(d.scheduled_send_date)}`
    : "Sends on approval (starts within 2 weeks)";
  return `<div class="welcome-msg">
      <div class="subj">${esc(d.subject_line)}</div>
      <div class="body">${esc(d.body)}</div>
    </div>
    <div class="dr" style="margin-top:6px;">${sched}</div>`;
}

// small helpers
function group(label, inner) {
  return `<div class="dgroup"><div class="dlabel">${esc(label)}</div>${inner}</div>`;
}
function docRow(left, right) {
  return `<div class="doc-row"><span class="dl">${left}</span><span class="dr">${right}</span></div>`;
}
function planCol(head, items) {
  return `<div class="col"><div class="ch">${esc(head)}</div>
    <ul>${(items || []).map((i) => `<li>${esc(i)}</li>`).join("")}</ul></div>`;
}

function legend() {
  return `<div class="legend">
    <div class="grp">
      <span class="li"><span class="sw" style="background:var(--coord)"></span>Assistant</span>
      <span class="li"><span class="sw" style="background:var(--it)"></span>IT</span>
      <span class="li"><span class="sw" style="background:var(--comp)"></span>Compliance</span>
      <span class="li"><span class="sw" style="background:var(--mgr)"></span>Manager Prep</span>
    </div>
    <div class="grp">
      <span class="li"><span class="sw" style="background:var(--accent)"></span>Your approval needed</span>
      <span class="li"><span class="sw" style="background:var(--alert)"></span>Heads-up to act on</span>
    </div>
  </div>`;
}

function banner(view) {
  const msg = (view && view.message) ||
    "Something went wrong. Pick the hire again to restart.";
  const errs = view && view.errors && view.errors.length
    ? `<ul>${view.errors.map((e) => `<li>${esc(e)}</li>`).join("")}</ul>` : "";
  return `<div class="banner">
      <h3>Couldn't process this hire</h3>
      <p>${esc(msg)}</p>${errs}
    </div>`;
}

// ==================================================================================
// fetch helpers
// ==================================================================================
async function fetchJSON(url) {
  const r = await fetch(url);
  return r.json();
}
async function postJSON(url, body) {
  const r = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return r.json();
}

boot();
