const API_BASE = window.API_BASE || "http://localhost:8000";

// ------------------------------------------------------------- state --
let sentiment = "Neutral";
let materials = [];
let samples = [];
let chatHistory = []; // [{role, content}]

// --------------------------------------------------------------- refs --
const $ = (id) => document.getElementById(id);
const hcpName = $("hcpName");
const hcpSuggestions = $("hcpSuggestions");
const interactionType = $("interactionType");
const dateInput = $("date");
const timeInput = $("time");
const attendees = $("attendees");
const topics = $("topics");
const outcomes = $("outcomes");
const followups = $("followups");
const materialsChips = $("materialsChips");
const samplesChips = $("samplesChips");
const aiSuggestions = $("aiSuggestions");
const aiSuggestionsList = $("aiSuggestionsList");
const formStatus = $("formStatus");
const pastList = $("pastList");
const apiStatus = $("apiStatus");

const today = new Date();
dateInput.value = today.toISOString().slice(0, 10);
timeInput.value = today.toTimeString().slice(0, 5);

// ---------------------------------------------------------- HCP search --
let hcpDebounce;
hcpName.addEventListener("input", () => {
  clearTimeout(hcpDebounce);
  const q = hcpName.value.trim();
  hcpDebounce = setTimeout(() => searchHcps(q), 200);
});
hcpName.addEventListener("blur", () => setTimeout(() => hcpSuggestions.classList.add("hidden"), 150));

async function searchHcps(q) {
  try {
    const res = await fetch(`${API_BASE}/api/hcps?q=${encodeURIComponent(q)}`);
    const data = await res.json();
    renderHcpSuggestions(data.hcps, q);
  } catch (e) {
    console.error("HCP search failed", e);
  }
}

function renderHcpSuggestions(hcps, q) {
  hcpSuggestions.innerHTML = "";
  hcps.forEach((h) => {
    const div = document.createElement("div");
    div.className = "suggestion-item";
    div.innerHTML = `<span>${h.name}</span><span class="spec">${h.specialty || ""}</span>`;
    div.onclick = () => {
      hcpName.value = h.name;
      hcpSuggestions.classList.add("hidden");
    };
    hcpSuggestions.appendChild(div);
  });
  if (q && !hcps.some((h) => h.name.toLowerCase() === q.toLowerCase())) {
    const addDiv = document.createElement("div");
    addDiv.className = "suggestion-item add-new";
    addDiv.textContent = `+ Add "${q}" as new HCP`;
    addDiv.onclick = async () => {
      await fetch(`${API_BASE}/api/hcps?name=${encodeURIComponent(q)}`, { method: "POST" });
      hcpName.value = q;
      hcpSuggestions.classList.add("hidden");
    };
    hcpSuggestions.appendChild(addDiv);
  }
  hcpSuggestions.classList.toggle("hidden", hcps.length === 0 && !q);
}

// --------------------------------------------------------------- chips --
$("addMaterialBtn").onclick = () => {
  const name = prompt("Material shared (e.g. Product X Brochure):");
  if (name) { materials.push(name); renderChips(); }
};
$("addSampleBtn").onclick = () => {
  const name = prompt("Sample distributed (e.g. Oncoboost 10mg x2):");
  if (name) { samples.push(name); renderChips(); }
};

function renderChips() {
  materialsChips.innerHTML = materials.map((m, i) =>
    `<span class="chip">${m}<button onclick="removeMaterial(${i})">✕</button></span>`).join("");
  samplesChips.innerHTML = samples.map((s, i) =>
    `<span class="chip sample">${s}<button onclick="removeSample(${i})">✕</button></span>`).join("");
}
window.removeMaterial = (i) => { materials.splice(i, 1); renderChips(); };
window.removeSample = (i) => { samples.splice(i, 1); renderChips(); };

// ----------------------------------------------------------- sentiment --
document.querySelectorAll("#sentimentRow .pill").forEach((btn) => {
  btn.onclick = () => {
    sentiment = btn.dataset.value;
    document.querySelectorAll("#sentimentRow .pill").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
  };
});

// ----------------------------------------------------- voice note (tool) --
$("voiceNoteBtn").onclick = async () => {
  const transcript = prompt("Paste the voice-note transcript:");
  if (!transcript) return;
  const consent = confirm("Confirm: has the HCP/rep given consent to summarize this recording?");
  formStatus.textContent = "Summarizing voice note…";
  try {
    const res = await fetch(`${API_BASE}/api/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message: `Summarize this voice note transcript (consent_given=${consent}): ${transcript}`,
        history: chatHistory,
      }),
    });
    const data = await res.json();
    appendChat("user", "🎙️ Voice note submitted for summarization");
    renderToolCalls(data.tool_calls);
    appendChat("agent", data.reply);
    const summaryCall = data.tool_calls.find((t) => t.tool === "summarize_voice_note");
    if (summaryCall && summaryCall.result.status === "ok") {
      topics.value = (topics.value ? topics.value + "\n" : "") + summaryCall.result.summary;
    }
  } catch (e) {
    console.error(e);
  } finally {
    formStatus.textContent = "";
  }
};

// ------------------------------------------------------------ form log --
$("interactionForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const payload = {
    hcp_name: hcpName.value,
    interaction_type: interactionType.value,
    date: dateInput.value,
    time: timeInput.value,
    attendees: attendees.value,
    topics_discussed: topics.value,
    materials_shared: materials,
    samples_distributed: samples,
    sentiment,
    outcomes: outcomes.value,
    follow_up_actions: followups.value ? followups.value.split("\n").filter(Boolean) : [],
  };
  formStatus.textContent = "Logging…";
  try {
    const res = await fetch(`${API_BASE}/api/interactions`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const record = await res.json();
    formStatus.textContent = `Logged ✓ (#${record.id})`;
    await loadPastInteractions();
    await fetchFollowupSuggestions(record.id);
  } catch (err) {
    formStatus.textContent = "Error logging interaction";
    console.error(err);
  }
});

async function fetchFollowupSuggestions(interactionId) {
  try {
    const res = await fetch(`${API_BASE}/api/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message: `Suggest follow-up actions for interaction_id ${interactionId}.`,
        history: chatHistory,
      }),
    });
    const data = await res.json();
    const call = data.tool_calls.find((t) => t.tool === "suggest_followups");
    if (call && call.result.suggestions) {
      aiSuggestionsList.innerHTML = call.result.suggestions.map((s) => `<li>${s}</li>`).join("");
      aiSuggestions.classList.remove("hidden");
    }
  } catch (e) {
    console.error("follow-up suggestion failed", e);
  }
}

// -------------------------------------------------------- past listing --
async function loadPastInteractions() {
  try {
    const res = await fetch(`${API_BASE}/api/interactions`);
    const data = await res.json();
    renderPastInteractions(data.interactions);
  } catch (e) {
    console.error(e);
  }
}

function renderPastInteractions(list) {
  if (!list.length) {
    pastList.innerHTML = `<p class="empty-note">Nothing logged yet — use the form or ask the AI Assistant.</p>`;
    return;
  }
  pastList.innerHTML = list
    .slice()
    .reverse()
    .map(
      (r) => `
    <div class="past-item">
      <div class="past-item-main">
        <div class="past-item-hcp">${r.hcp_name || "(unnamed HCP)"} <span class="sentiment-tag ${r.sentiment}">${r.sentiment}</span></div>
        <div class="past-item-meta">#${r.id} · ${r.interaction_type} · ${r.date || "no date"} ${r.time || ""} · via ${r.source}</div>
        <div class="past-item-topics">${r.topics_discussed || "<em>no topics recorded</em>"}</div>
      </div>
      <button class="edit-btn" onclick="editInteraction(${r.id})">Edit</button>
    </div>`
    )
    .join("");
}

window.editInteraction = async (id) => {
  const field = prompt("Which field do you want to edit? (topics_discussed, outcomes, sentiment, hcp_name, interaction_type)");
  if (!field) return;
  const value = prompt(`New value for ${field}:`);
  if (value === null) return;
  const res = await fetch(`${API_BASE}/api/interactions/${id}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ [field]: value }),
  });
  if (res.ok) {
    await loadPastInteractions();
  } else {
    alert("Could not update interaction");
  }
};

// -------------------------------------------------------------- chat ui --
function appendChat(role, text) {
  const div = document.createElement("div");
  div.className = `chat-msg ${role === "user" ? "user" : "agent"}`;
  div.innerHTML = `<p></p>`;
  div.querySelector("p").textContent = text;
  $("chatFeed").appendChild(div);
  $("chatFeed").scrollTop = $("chatFeed").scrollHeight;
  chatHistory.push({ role: role === "user" ? "user" : "assistant", content: text });
}

function renderToolCalls(toolCalls) {
  toolCalls.forEach((tc) => {
    const chip = document.createElement("div");
    chip.className = "tool-chip";
    chip.textContent = `🛠 ${tc.tool}`;
    $("chatFeed").appendChild(chip);
  });
  $("chatFeed").scrollTop = $("chatFeed").scrollHeight;
}

$("chatForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const input = $("chatInput");
  const message = input.value.trim();
  if (!message) return;
  appendChat("user", message);
  input.value = "";
  $("chatSendBtn").disabled = true;

  try {
    const res = await fetch(`${API_BASE}/api/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, history: chatHistory.slice(0, -1) }),
    });
    const data = await res.json();
    renderToolCalls(data.tool_calls);
    appendChat("agent", data.reply || "(no reply)");

    if (data.form_update) applyFormUpdate(data.form_update);

    const suggestCall = data.tool_calls.find((t) => t.tool === "suggest_followups");
    if (suggestCall && suggestCall.result.suggestions) {
      aiSuggestionsList.innerHTML = suggestCall.result.suggestions.map((s) => `<li>${s}</li>`).join("");
      aiSuggestions.classList.remove("hidden");
    }
    if (data.tool_calls.some((t) => t.tool === "log_interaction" || t.tool === "edit_interaction")) {
      await loadPastInteractions();
    }
  } catch (err) {
    appendChat("agent", "Sorry, I couldn't reach the backend. Is it running on " + API_BASE + "?");
    console.error(err);
  } finally {
    $("chatSendBtn").disabled = false;
  }
});

function applyFormUpdate(record) {
  if (record.hcp_name) hcpName.value = record.hcp_name;
  if (record.interaction_type) interactionType.value = record.interaction_type;
  if (record.topics_discussed) topics.value = record.topics_discussed;
  if (record.outcomes) outcomes.value = record.outcomes;
  if (record.sentiment) {
    sentiment = record.sentiment;
    document.querySelectorAll("#sentimentRow .pill").forEach((b) => {
      b.classList.toggle("active", b.dataset.value === sentiment);
    });
  }
  if (Array.isArray(record.materials_shared)) { materials = record.materials_shared; }
  if (Array.isArray(record.samples_distributed)) { samples = record.samples_distributed; }
  renderChips();
}

// -------------------------------------------------------------- health --
async function checkHealth() {
  try {
    const res = await fetch(`${API_BASE}/api/health`);
    apiStatus.className = res.ok ? "status-dot status-ok" : "status-dot status-down";
  } catch {
    apiStatus.className = "status-dot status-down";
  }
}

checkHealth();
loadPastInteractions();
setInterval(checkHealth, 15000);
