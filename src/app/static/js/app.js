/* ═══════════════════════════════════════════════
   GitHub Star Predictor — Frontend Logic
   ═══════════════════════════════════════════════ */

const API_PREDICT = "/predict";
const API_DEMO    = "/predict/demo";

// ── DOM refs ──────────────────────────────────────────────────────────────
const repoList        = document.getElementById("repoList");
const addRepoBtn      = document.getElementById("addRepoBtn");
const predictBtn      = document.getElementById("predictBtn");
const demoBtn         = document.getElementById("demoBtn");
const clearBtn        = document.getElementById("clearBtn");
const resultsSection  = document.getElementById("resultsSection");
const resultsContainer= document.getElementById("resultsContainer");
const modelBadge      = document.getElementById("modelBadge");
const errorBox        = document.getElementById("errorBox");
const cardTemplate    = document.getElementById("repoCardTemplate");

let cardCount = 0;

// ── Card management ───────────────────────────────────────────────────────
function addCard(prefill = null) {
  const clone = cardTemplate.content.cloneNode(true);
  const card  = clone.querySelector(".repo-card");
  card.dataset.index = ++cardCount;

  if (prefill) {
    card.querySelector(".repo-name-input").value = prefill.repo_name || "";
    for (const [key, val] of Object.entries(prefill)) {
      const el = card.querySelector(`[name="${key}"]`);
      if (!el) continue;
      if (el.type === "checkbox") el.checked = Boolean(val);
      else el.value = val;
    }
  }

  card.querySelector(".remove-btn").addEventListener("click", () => {
    card.style.opacity = "0";
    card.style.transform = "scale(0.96)";
    card.style.transition = "all 150ms ease";
    setTimeout(() => card.remove(), 150);
  });

  repoList.appendChild(clone);
}

function clearAll() {
  repoList.innerHTML = "";
  hideResults();
  hideError();
  cardCount = 0;
}

// ── Read card values into a plain object ─────────────────────────────────
function readCard(card) {
  const obj = {};
  obj.repo_name = card.querySelector(".repo-name-input").value.trim() || `Repo ${card.dataset.index}`;

  card.querySelectorAll("[name]").forEach(el => {
    const key = el.name;
    if (el.type === "checkbox")      obj[key] = el.checked ? 1 : 0;
    else if (el.tagName === "SELECT") obj[key] = el.value;
    else                              obj[key] = el.value === "" ? null : Number(el.value);
  });

  return obj;
}

// ── Validation ────────────────────────────────────────────────────────────
const REQUIRED_NUMBERS = [
  "forks", "open_issues", "size", "commits", "contributors",
  "subscribers_count", "network_count", "repo_age_days"
];

function validate(repos) {
  for (const [i, r] of repos.entries()) {
    for (const field of REQUIRED_NUMBERS) {
      if (r[field] === null || r[field] === undefined || isNaN(r[field])) {
        return `Repo ${i + 1} ("${r.repo_name}"): "${field}" is required.`;
      }
    }
  }
  return null;
}

// ── API calls ─────────────────────────────────────────────────────────────
async function runPredict() {
  hideError();
  hideResults();

  const cards = [...repoList.querySelectorAll(".repo-card")];
  if (!cards.length) { showError("Add at least one repository first."); return; }

  const repos = cards.map(readCard);
  const err   = validate(repos);
  if (err) { showError(err); return; }

  setLoading(true);
  try {
    const res  = await fetch(API_PREDICT, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(repos),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Prediction failed.");
    renderResults(data);
  } catch (e) {
    showError(e.message);
  } finally {
    setLoading(false);
  }
}

async function runDemo() {
  hideError();
  hideResults();
  setLoading(true);
  try {
    const res  = await fetch(API_DEMO);
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Demo failed.");
    renderResults(data);
  } catch (e) {
    showError(e.message);
  } finally {
    setLoading(false);
  }
}

// ── Render results ────────────────────────────────────────────────────────
function renderResults({ ranked, model_uri }) {
  resultsContainer.innerHTML = "";
  modelBadge.textContent = model_uri;

  const maxStars = ranked[0]?.predicted_stars || 1;

  ranked.forEach((item, i) => {
    const pct = Math.round((item.predicted_stars / maxStars) * 100);
    const row = document.createElement("div");
    row.className = "result-row";
    row.innerHTML = `
      <div class="result-rank">#${i + 1}</div>
      <div class="result-info">
        <div class="result-name">${escHtml(item.repo_name)}</div>
        <div class="result-log">log_stars: ${item.log_stars}</div>
      </div>
      <div class="result-bar-wrap">
        <div class="result-bar-bg">
          <div class="result-bar-fill" style="width:0%"></div>
        </div>
      </div>
      <div class="result-stars">
        <div class="stars-count">★ ${formatNum(item.predicted_stars)}</div>
        <div class="stars-label">predicted stars</div>
      </div>
    `;
    resultsContainer.appendChild(row);
    // Animate bar after paint
    requestAnimationFrame(() => {
      const fill = row.querySelector(".result-bar-fill");
      setTimeout(() => fill.style.width = pct + "%", 50 + i * 80);
    });
  });

  resultsSection.classList.remove("hidden");
  resultsSection.scrollIntoView({ behavior: "smooth", block: "start" });
}

// ── Helpers ───────────────────────────────────────────────────────────────
function showError(msg) {
  errorBox.textContent = "⚠ " + msg;
  errorBox.classList.remove("hidden");
}
function hideError()   { errorBox.classList.add("hidden"); }
function hideResults() { resultsSection.classList.add("hidden"); }

function setLoading(on) {
  predictBtn.disabled = on;
  if (on) {
    predictBtn.innerHTML = `<span class="spinner"></span> Predicting…`;
  } else {
    predictBtn.innerHTML = `<span class="btn-icon">⚡</span> Predict &amp; Rank`;
  }
}

function formatNum(n) {
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + "M";
  if (n >= 1_000)     return (n / 1_000).toFixed(1) + "k";
  return String(n);
}

function escHtml(s) {
  return s.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
}

// ── Wire up events ────────────────────────────────────────────────────────
addRepoBtn .addEventListener("click", () => addCard());
predictBtn .addEventListener("click", runPredict);
demoBtn    .addEventListener("click", runDemo);
clearBtn   .addEventListener("click", clearAll);

// Start with 2 blank cards
addCard();
addCard();
