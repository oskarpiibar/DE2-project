const repoList       = document.getElementById("repoList");
const addRepoBtn     = document.getElementById("addRepoBtn");
const predictBtn     = document.getElementById("predictBtn");
const demoBtn        = document.getElementById("demoBtn");
const clearBtn       = document.getElementById("clearBtn");
const resultsSection = document.getElementById("resultsSection");
const resultsContainer = document.getElementById("resultsContainer");
const modelBadge     = document.getElementById("modelBadge");
const errorBox       = document.getElementById("errorBox");
const cardTemplate   = document.getElementById("repoCardTemplate");

let cardCount = 0;

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

  card.querySelector(".remove-btn").addEventListener("click", () => card.remove());
  repoList.appendChild(clone);
}

function clearAll() {
  repoList.innerHTML = "";
  resultsSection.classList.add("hidden");
  errorBox.classList.add("hidden");
  cardCount = 0;
}

function readCard(card) {
  const obj = {};
  obj.repo_name = card.querySelector(".repo-name-input").value.trim() || "Repo " + card.dataset.index;
  card.querySelectorAll("[name]").forEach(el => {
    if (el.type === "checkbox")       obj[el.name] = el.checked ? 1 : 0;
    else if (el.tagName === "SELECT") obj[el.name] = el.value;
    else obj[el.name] = el.value === "" ? null : Number(el.value);
  });
  return obj;
}

const REQUIRED = ["forks","open_issues","size","commits","contributors","subscribers_count","network_count","repo_age_days"];

function validate(repos) {
  for (const [i, r] of repos.entries()) {
    for (const f of REQUIRED) {
      if (r[f] === null || r[f] === undefined || isNaN(r[f]))
        return `Repo ${i + 1} ("${r.repo_name}"): "${f}" is required.`;
    }
  }
  return null;
}

async function runPredict() {
  errorBox.classList.add("hidden");
  resultsSection.classList.add("hidden");

  const cards = [...repoList.querySelectorAll(".repo-card")];
  if (!cards.length) { showError("Add at least one repository first."); return; }

  const repos = cards.map(readCard);
  const err   = validate(repos);
  if (err) { showError(err); return; }

  predictBtn.disabled = true;
  predictBtn.textContent = "Predicting...";

  try {
    const res  = await fetch("/predict", {
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
    predictBtn.disabled = false;
    predictBtn.textContent = "Predict and Rank";
  }
}

async function runDemo() {
  errorBox.classList.add("hidden");
  resultsSection.classList.add("hidden");
  try {
    const res  = await fetch("/predict/demo");
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Demo failed.");
    renderResults(data);
  } catch (e) {
    showError(e.message);
  }
}

function renderResults({ ranked, model_uri }) {
  resultsContainer.innerHTML = "";
  modelBadge.textContent = model_uri;

  ranked.forEach((item, i) => {
    const row = document.createElement("div");
    row.className = "result-row";
    row.innerHTML = `
      <div class="result-rank">#${i + 1}</div>
      <div class="result-info">
        <div class="result-name">${item.repo_name}</div>
        <div class="result-log">log_stars: ${item.log_stars}</div>
      </div>
      <div class="result-stars">${formatNum(item.predicted_stars)} stars</div>
    `;
    resultsContainer.appendChild(row);
  });

  resultsSection.classList.remove("hidden");
}

function showError(msg) {
  errorBox.textContent = msg;
  errorBox.classList.remove("hidden");
}

function formatNum(n) {
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + "M";
  if (n >= 1_000)     return (n / 1_000).toFixed(1) + "k";
  return String(n);
}

addRepoBtn .addEventListener("click", () => addCard());
predictBtn .addEventListener("click", runPredict);
demoBtn    .addEventListener("click", runDemo);
clearBtn   .addEventListener("click", clearAll);

addCard();
addCard();
