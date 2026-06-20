import { fetchJSON, fighterPageUrl } from "./common.js";

let meta = null;
let rankings = null;
let fightersIndex = null;
let currentMode = "current";
let activeDivision = "p4p";

async function init() {
  try {
    [meta, rankings, fightersIndex] = await Promise.all([
      fetchJSON("meta.json"),
      fetchJSON("rankings.json"),
      fetchJSON("fighters_index.json"),
    ]);
    renderDivisionTabs();
    renderRankings();
    setupModeSwitch();
    setupSearch();
    document.getElementById("ref-date").textContent = rankings.reference_date;
  } catch (err) {
    document.getElementById("app").innerHTML =
      `<div class="error">Failed to load rankings data. Run <code>python src/export_static_site.py</code> first.</div>`;
    console.error(err);
  }
}

function renderDivisionTabs() {
  const container = document.getElementById("division-tabs");
  container.innerHTML = meta.divisions
    .map(
      (div) =>
        `<button class="division-tab${div.code === activeDivision ? " active" : ""}" data-code="${div.code}">${div.name}</button>`
    )
    .join("");

  container.querySelectorAll(".division-tab").forEach((btn) => {
    btn.addEventListener("click", () => {
      activeDivision = btn.dataset.code;
      container.querySelectorAll(".division-tab").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      renderRankings();
    });
  });
}

function renderRankings() {
  const modeData = rankings[currentMode];
  const entries = modeData[activeDivision] || [];
  const division = meta.divisions.find((d) => d.code === activeDivision);

  document.getElementById("division-title").textContent = division?.name || activeDivision;
  document.getElementById("mode-subtitle").textContent =
    currentMode === "current"
      ? `Active fighters only (fought within ${meta.inactivity_years_current_mode} years)`
      : "All fighters (historical, no inactivity filter)";

  const tbody = document.getElementById("rankings-body");
  if (entries.length === 0) {
    tbody.innerHTML = `<tr><td colspan="3">No ranked fighters in this division.</td></tr>`;
    return;
  }

  tbody.innerHTML = entries
    .map(
      (entry) => `
    <tr class="rank-${entry.rank}">
      <td class="rank-num">#${entry.rank}</td>
      <td><a class="fighter-link" href="${fighterPageUrl(entry.fighter_id)}">${entry.name}</a></td>
      <td class="elo-score">${entry.elo.toFixed(2)}</td>
    </tr>`
    )
    .join("");
}

function setupModeSwitch() {
  const toggle = document.getElementById("mode-toggle");
  const label = document.getElementById("mode-label");

  function updateLabel() {
    label.textContent = currentMode === "current" ? "Current" : "Historical";
    toggle.classList.toggle("active", currentMode === "current");
  }

  toggle.addEventListener("click", () => {
    currentMode = currentMode === "current" ? "historical" : "current";
    updateLabel();
    renderRankings();
  });

  updateLabel();
}

function setupSearch() {
  const input = document.getElementById("fighter-search");
  const results = document.getElementById("search-results");

  input.addEventListener("input", () => {
    const query = input.value.trim().toLowerCase();
    if (query.length < 2) {
      results.classList.remove("visible");
      results.innerHTML = "";
      return;
    }

    const matches = fightersIndex
      .filter((f) => f.name.toLowerCase().includes(query))
      .slice(0, 12);

    if (matches.length === 0) {
      results.innerHTML = `<div style="padding:0.5rem 0.75rem;color:var(--muted)">No matches</div>`;
    } else {
      results.innerHTML = matches
        .map((f) => `<a href="${fighterPageUrl(f.id)}">${f.name}</a>`)
        .join("");
    }
    results.classList.add("visible");
  });

  document.addEventListener("click", (e) => {
    if (!e.target.closest(".search-box")) {
      results.classList.remove("visible");
    }
  });
}

init();
