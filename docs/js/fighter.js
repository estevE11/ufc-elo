import {
  fetchJSON,
  getFighterIdFromURL,
  fighterPageUrl,
  formatDelta,
  deltaClass,
  formatResult,
  shortResult,
  shortWeightClass,
  shortDate,
} from "./common.js";

let chart = null;
let profile = null;
let meta = null;
let activeChartDivision = "p4p";

const DIVISION_LABELS = {
  p4p: "P4P",
  hw: "HW",
  lhw: "LHW",
  mw: "MW",
  ww: "WW",
  lw: "LW",
  fw: "FW",
  bw: "BW",
  flw: "FLW",
  wsw: "WSW",
  wflw: "WFLW",
  wbw: "WBW",
  wfw: "WFW",
  catch: "Catch",
};

async function init() {
  const fighterId = getFighterIdFromURL();
  if (!fighterId) {
    document.getElementById("app").innerHTML =
      `<div class="error">No fighter specified. <a href="index.html">Back to rankings</a></div>`;
    return;
  }

  try {
    [meta, profile] = await Promise.all([
      fetchJSON("meta.json"),
      fetchJSON(`fighters/${fighterId}.json`),
    ]);
    renderProfile();
    renderChartFilters();
    renderChart();
    renderFights();
    setupCompare(fighterId);
    document.title = `${profile.name} — UFC Elo`;
  } catch (err) {
    document.getElementById("app").innerHTML =
      `<div class="error">Fighter not found. <a href="index.html">Back to rankings</a></div>`;
    console.error(err);
  }
}

function renderProfile() {
  const divisions = profile.divisions
    .map((code) => profile.division_names[code] || code)
    .join(", ");

  document.getElementById("fighter-name").textContent = profile.name;
  document.getElementById("fighter-meta").textContent = [
    profile.fights.length ? `${profile.fights.length} rated fights` : null,
    divisions ? `Divisions: ${divisions}` : null,
    profile.last_fight_date ? `Last fight: ${profile.last_fight_date}` : null,
  ]
    .filter(Boolean)
    .join(" · ");
}

function renderChartFilters() {
  const container = document.getElementById("chart-filters");
  const divisions = ["p4p", ...profile.divisions.filter((d) => d !== "p4p")];

  container.innerHTML = divisions
    .map((code) => {
      const label =
        code === "p4p"
          ? "P4P"
          : profile.division_names[code] || DIVISION_LABELS[code] || code.toUpperCase();
      return `<button class="chart-filter${code === activeChartDivision ? " active" : ""}" data-code="${code}">${label}</button>`;
    })
    .join("");

  container.querySelectorAll(".chart-filter").forEach((btn) => {
    btn.addEventListener("click", () => {
      activeChartDivision = btn.dataset.code;
      container.querySelectorAll(".chart-filter").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      renderChart();
    });
  });
}

function renderChart() {
  const history = profile.rank_history[activeChartDivision] || [];
  const canvas = document.getElementById("rank-chart");
  const title = document.getElementById("chart-title");

  const divisionName =
    activeChartDivision === "p4p"
      ? "Pound for Pound"
      : profile.division_names[activeChartDivision] ||
        DIVISION_LABELS[activeChartDivision] ||
        activeChartDivision;

  title.textContent = `${divisionName} Ranking Over Time`;

  if (chart) {
    chart.destroy();
    chart = null;
  }

  if (history.length === 0) {
    const ctx = canvas.getContext("2d");
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    return;
  }

  const labels = history.map((p) => p.date);
  const ranks = history.map((p) => p.rank);
  const elos = history.map((p) => p.elo);

  chart = new Chart(canvas, {
    type: "line",
    data: {
      labels,
      datasets: [
        {
          label: "Rank",
          data: ranks,
          borderColor: "#d20a0a",
          backgroundColor: "rgba(210, 10, 10, 0.1)",
          yAxisID: "yRank",
          tension: 0.2,
          pointRadius: 0,
          pointHoverRadius: 4,
          borderWidth: 2,
        },
        {
          label: "Elo",
          data: elos,
          borderColor: "#666",
          yAxisID: "yElo",
          tension: 0.2,
          pointRadius: 0,
          pointHoverRadius: 4,
          borderWidth: 1,
          borderDash: [4, 4],
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: { labels: { color: "#999" } },
        tooltip: {
          callbacks: {
            label(ctx) {
              if (ctx.dataset.label === "Rank") {
                return `Rank: #${ctx.parsed.y}`;
              }
              return `Elo: ${ctx.parsed.y.toFixed(2)}`;
            },
          },
        },
      },
      scales: {
        x: {
          ticks: { color: "#666", maxTicksLimit: 10 },
          grid: { color: "#222" },
        },
        yRank: {
          type: "linear",
          position: "left",
          reverse: true,
          title: { display: true, text: "Rank", color: "#999" },
          ticks: { color: "#999", stepSize: 1 },
          grid: { color: "#222" },
        },
        yElo: {
          type: "linear",
          position: "right",
          title: { display: true, text: "Elo", color: "#666" },
          ticks: { color: "#666" },
          grid: { drawOnChartArea: false },
        },
      },
    },
  });
}

function setupCompare(fighterId) {
  const btn = document.getElementById("compare-btn");
  const box = document.getElementById("compare-search");
  const input = document.getElementById("compare-input");
  const results = document.getElementById("compare-results");
  let index = null;

  async function ensureIndex() {
    if (!index) index = await fetchJSON("fighters_index.json");
    return index;
  }

  btn.addEventListener("click", async () => {
    const open = box.classList.toggle("open");
    if (open) {
      await ensureIndex();
      input.focus();
    }
  });

  input.addEventListener("input", () => {
    const query = input.value.trim().toLowerCase();
    if (query.length < 2 || !index) {
      results.classList.remove("visible");
      results.innerHTML = "";
      return;
    }
    const matches = index
      .filter((f) => f.id !== fighterId && f.name.toLowerCase().includes(query))
      .slice(0, 10);
    results.innerHTML = matches.length
      ? matches
          .map(
            (f) =>
              `<a href="compare.html?a=${encodeURIComponent(fighterId)}&b=${encodeURIComponent(f.id)}">${f.name}</a>`
          )
          .join("")
      : `<div style="padding:0.5rem 0.85rem;color:var(--muted)">No matches</div>`;
    results.classList.add("visible");
  });

  document.addEventListener("click", (e) => {
    if (!e.target.closest(".compare-control")) {
      box.classList.remove("open");
      results.classList.remove("visible");
    }
  });
}

function renderFights() {
  const tbody = document.getElementById("fights-body");
  const fights = profile.fights;

  if (fights.length === 0) {
    tbody.innerHTML = `<tr><td colspan="8">No rated fights on record.</td></tr>`;
    return;
  }

  tbody.innerHTML = fights
    .map((fight) => {
      const outcomeClass = fight.outcome === "W" ? "outcome-w" : "outcome-l";
      const divDeltaCls = deltaClass(fight.div_delta);
      return `
    <tr>
      <td class="col-outcome ${outcomeClass}"><span class="outcome-text">${fight.outcome}</span><span class="outcome-bar" aria-hidden="true"></span></td>
      <td class="col-date"><span class="cell-full">${fight.date}</span><span class="cell-short">${shortDate(fight.date)}</span></td>
      <td class="col-div"><span class="cell-full">${fight.weight_class_name}</span><span class="cell-short">${shortWeightClass(fight.weight_class)}</span></td>
      <td class="col-opp"><a href="${fighterPageUrl(fight.opponent_id)}">${fight.opponent_name}</a></td>
      <td class="col-method"><span class="cell-full">${formatResult(fight.result)}</span><span class="cell-short">${shortResult(fight.result)}</span></td>
      <td class="col-p4p-delta ${deltaClass(fight.p4p_delta)}">${formatDelta(fight.p4p_delta)}</td>
      <td class="col-p4p-elo">${fight.p4p_after.toFixed(2)}</td>
      <td class="col-div-delta ${divDeltaCls}"><span class="cell-full">${formatDelta(fight.div_delta)}</span><span class="cell-short elo-delta-mini ${divDeltaCls}">${formatDelta(fight.div_delta)}</span></td>
      <td class="col-div-elo">${fight.div_after.toFixed(2)}</td>
    </tr>`;
    })
    .join("");
}

init();
