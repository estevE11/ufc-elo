import {
  fetchJSON,
  getCompareIdsFromURL,
  fighterPageUrl,
  formatResult,
} from "./common.js";

const COLORS = {
  a: { line: "#ff3030", fill: "rgba(255, 48, 48, 0.12)" },
  b: { line: "#3b9dff", fill: "rgba(59, 157, 255, 0.12)" },
};

let chart = null;
let meta = null;
let fighters = { a: null, b: null };
let divLabels = {};
let sharedDivisions = [];
let activeDivision = "p4p";

async function init() {
  const { a, b } = getCompareIdsFromURL();
  if (!a || !b) {
    fail("Two fighters are required to compare. <a href='index.html'>Back to rankings</a>");
    return;
  }
  if (a === b) {
    fail("Pick two different fighters. <a href='index.html'>Back to rankings</a>");
    return;
  }

  try {
    const [m, fa, fb] = await Promise.all([
      fetchJSON("meta.json"),
      fetchJSON(`fighters/${a}.json`),
      fetchJSON(`fighters/${b}.json`),
    ]);
    meta = m;
    fighters = { a: fa, b: fb };
    divLabels = Object.fromEntries(meta.divisions.map((d) => [d.code, d.name]));

    computeSharedDivisions();
    renderHeader();
    renderVersus();
    renderFilters();
    renderChart();
    renderHeadToHead();
    document.title = `${fa.name} vs ${fb.name} — UFC Elo`;
  } catch (err) {
    fail("Could not load one of the fighters. <a href='index.html'>Back to rankings</a>");
    console.error(err);
  }
}

function fail(html) {
  document.getElementById("app").innerHTML = `<div class="error">${html}</div>`;
}

/** Divisions both fighters fought in, p4p first. */
function computeSharedDivisions() {
  const setB = new Set(fighters.b.divisions);
  const shared = fighters.a.divisions.filter((d) => setB.has(d));
  sharedDivisions = ["p4p", ...shared];
  activeDivision = "p4p";
}

/** Chronological per-fight elo points for one fighter in a division. */
function series(fighter, code) {
  const chrono = [...fighter.fights].reverse();
  const pts = [];
  let n = 0;
  for (const f of chrono) {
    if (code === "p4p") {
      pts.push({ x: ++n, y: f.p4p_after });
    } else if (f.weight_class === code) {
      pts.push({ x: ++n, y: f.div_after });
    }
  }
  return pts;
}

function divisionName(code) {
  return code === "p4p" ? "Pound for Pound" : divLabels[code] || code.toUpperCase();
}

function renderHeader() {
  document.getElementById("compare-title").innerHTML =
    `<a class="vs-name vs-a" href="${fighterPageUrl(fighters.a.id)}">${fighters.a.name}</a>` +
    `<span class="vs-sep">vs</span>` +
    `<a class="vs-name vs-b" href="${fighterPageUrl(fighters.b.id)}">${fighters.b.name}</a>`;

  const shared = sharedDivisions
    .filter((d) => d !== "p4p")
    .map(divisionName);
  document.getElementById("compare-sub").textContent = shared.length
    ? `Shared divisions: ${shared.join(", ")}`
    : "No shared weight class — comparing pound-for-pound only.";
}

function record(fighter) {
  let w = 0,
    l = 0,
    d = 0;
  for (const f of fighter.fights) {
    if (f.outcome === "W") w++;
    else if (f.outcome === "L") l++;
    else d++;
  }
  return d ? `${w}-${l}-${d}` : `${w}-${l}`;
}

function peakP4P(fighter) {
  return fighter.fights.reduce((mx, f) => Math.max(mx, f.p4p_after), -Infinity);
}

function currentP4P(fighter) {
  // fights are newest-first
  return fighter.fights.length ? fighter.fights[0].p4p_after : null;
}

function renderVersus() {
  const card = (key) => {
    const f = fighters[key];
    const cur = currentP4P(f);
    return `
    <div class="vs-card vs-card-${key}">
      <a class="vs-card-name" href="${fighterPageUrl(f.id)}">${f.name}</a>
      <dl class="vs-stats">
        <div><dt>Record</dt><dd>${record(f)}</dd></div>
        <div><dt>Rated fights</dt><dd>${f.fights.length}</dd></div>
        <div><dt>Current P4P Elo</dt><dd>${cur != null ? cur.toFixed(1) : "—"}</dd></div>
        <div><dt>Peak P4P Elo</dt><dd>${peakP4P(f).toFixed(1)}</dd></div>
        <div><dt>Last fight</dt><dd>${f.last_fight_date || "—"}</dd></div>
      </dl>
    </div>`;
  };
  document.getElementById("versus").innerHTML = card("a") + card("b");
}

function renderFilters() {
  const container = document.getElementById("chart-filters");
  container.innerHTML = sharedDivisions
    .map((code) => {
      const label = code === "p4p" ? "P4P" : divLabels[code] || code.toUpperCase();
      return `<button class="chart-filter${code === activeDivision ? " active" : ""}" data-code="${code}">${label}</button>`;
    })
    .join("");

  container.querySelectorAll(".chart-filter").forEach((btn) => {
    btn.addEventListener("click", () => {
      activeDivision = btn.dataset.code;
      container.querySelectorAll(".chart-filter").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      renderChart();
    });
  });
}

function renderChart() {
  const canvas = document.getElementById("compare-chart");
  document.getElementById("chart-title").textContent = `${divisionName(activeDivision)} — Elo by Fight`;

  const dataA = series(fighters.a, activeDivision);
  const dataB = series(fighters.b, activeDivision);

  if (chart) {
    chart.destroy();
    chart = null;
  }

  chart = new Chart(canvas, {
    type: "line",
    data: {
      datasets: [
        {
          label: fighters.a.name,
          data: dataA,
          borderColor: COLORS.a.line,
          backgroundColor: COLORS.a.fill,
          tension: 0.25,
          pointRadius: 2,
          pointHoverRadius: 5,
          borderWidth: 2,
          fill: false,
        },
        {
          label: fighters.b.name,
          data: dataB,
          borderColor: COLORS.b.line,
          backgroundColor: COLORS.b.fill,
          tension: 0.25,
          pointRadius: 2,
          pointHoverRadius: 5,
          borderWidth: 2,
          fill: false,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "nearest", intersect: false },
      plugins: {
        legend: { labels: { color: "#ccc", usePointStyle: true, padding: 16 } },
        tooltip: {
          callbacks: {
            title: (items) => `Fight #${items[0].parsed.x}`,
            label: (ctx) => `${ctx.dataset.label}: ${ctx.parsed.y.toFixed(1)} Elo`,
          },
        },
      },
      scales: {
        x: {
          type: "linear",
          title: { display: true, text: "Fight number", color: "#999" },
          ticks: { color: "#888", stepSize: 1, precision: 0 },
          grid: { color: "#222" },
        },
        y: {
          title: { display: true, text: "Elo", color: "#999" },
          ticks: { color: "#888" },
          grid: { color: "#222" },
        },
      },
    },
  });
}

function renderHeadToHead() {
  const section = document.getElementById("h2h");
  const meetings = [...fighters.a.fights]
    .filter((f) => f.opponent_id === fighters.b.id)
    .reverse();

  if (meetings.length === 0) {
    section.innerHTML = "";
    return;
  }

  const rows = meetings
    .map((f) => {
      const aWon = f.outcome === "W";
      const winner = f.outcome === "D" ? "Draw" : aWon ? fighters.a.name : fighters.b.name;
      return `
      <li>
        <span class="h2h-date">${f.date}</span>
        <span class="h2h-winner ${f.outcome === "D" ? "" : aWon ? "vs-a" : "vs-b"}">${winner}</span>
        <span class="h2h-method">${formatResult(f.result)}</span>
        <span class="h2h-div">${f.weight_class_name}</span>
      </li>`;
    })
    .join("");

  section.innerHTML = `
    <h2 class="h2h-title">Head to Head (${meetings.length})</h2>
    <ul class="h2h-list">${rows}</ul>`;
}

init();
