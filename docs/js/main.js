import { fetchJSON, fighterPageUrl } from "./common.js";

let meta = null;
let rankings = null;
let fightersIndex = null;
let currentMode = "current";

async function init() {
  try {
    [meta, rankings, fightersIndex] = await Promise.all([
      fetchJSON("meta.json"),
      fetchJSON("rankings.json"),
      fetchJSON("fighters_index.json"),
    ]);
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

function renderRankings() {
  const modeData = rankings[currentMode];

  document.getElementById("mode-subtitle").textContent =
    currentMode === "current"
      ? `Active fighters only (fought within ${meta.inactivity_years_current_mode} years)`
      : "All fighters (historical, no inactivity filter)";

  const grid = document.getElementById("division-grid");
  grid.innerHTML = meta.divisions
    .map((division) => {
      const entries = modeData[division.code] || [];
      const rows =
        entries.length === 0
          ? `<li class="mini-empty">No ranked fighters</li>`
          : entries
              .map(
                (entry) => `
            <li class="rank-${entry.rank}">
              <span class="mini-rank">#${entry.rank}</span>
              <a class="fighter-link" href="${fighterPageUrl(entry.fighter_id)}">${entry.name}</a>
              <span class="elo-score">${entry.elo.toFixed(2)}</span>
            </li>`
              )
              .join("");
      return `
      <section class="division-card">
        <header class="division-card-header">${division.name}</header>
        <ol class="mini-rank-list">${rows}</ol>
      </section>`;
    })
    .join("");
}

function setupModeSwitch() {
  const toggle = document.getElementById("mode-toggle");
  const options = toggle.querySelectorAll(".mode-option");

  function update() {
    toggle.classList.toggle("is-historical", currentMode === "historical");
    options.forEach((btn) => {
      const active = btn.dataset.mode === currentMode;
      btn.classList.toggle("active", active);
      btn.setAttribute("aria-checked", active ? "true" : "false");
    });
  }

  options.forEach((btn) => {
    btn.addEventListener("click", () => {
      if (btn.dataset.mode === currentMode) return;
      currentMode = btn.dataset.mode;
      update();
      renderRankings();
    });
  });

  update();
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
