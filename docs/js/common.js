/** Shared helpers for the static site. */

const DATA_BASE = "data";
const JSON_FETCH_ATTEMPTS = 2;
const JSON_RETRY_DELAY_MS = 750;

export async function fetchJSON(path) {
  let lastError;

  for (let attempt = 0; attempt < JSON_FETCH_ATTEMPTS; attempt += 1) {
    try {
      const response = await fetch(`${DATA_BASE}/${path}`, { cache: "no-cache" });
      if (!response.ok) {
        throw new Error(`Failed to load ${path}: ${response.status}`);
      }
      return await response.json();
    } catch (error) {
      lastError = error;
      if (attempt + 1 < JSON_FETCH_ATTEMPTS) {
        await new Promise((resolve) => setTimeout(resolve, JSON_RETRY_DELAY_MS));
      }
    }
  }

  throw lastError;
}

export function getFighterIdFromURL() {
  const params = new URLSearchParams(window.location.search);
  return params.get("id");
}

export function fighterPageUrl(fighterId) {
  return `fighter.html?id=${encodeURIComponent(fighterId)}`;
}

export function getCompareIdsFromURL() {
  const params = new URLSearchParams(window.location.search);
  return { a: params.get("a"), b: params.get("b") };
}

export function formatDelta(value) {
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(2)}`;
}

export function deltaClass(value) {
  if (value > 0) return "delta-pos";
  if (value < 0) return "delta-neg";
  return "";
}

export function formatResult(result) {
  const labels = {
    "ko/tko": "KO/TKO",
    sub: "Submission",
    ud: "Unanimous Dec.",
    sd: "Split Dec.",
    md: "Majority Dec.",
    dq: "DQ",
    draw: "Draw",
    nc: "No Contest",
  };
  return labels[result] || result.toUpperCase();
}

export function shortResult(result) {
  const labels = {
    "ko/tko": "KO",
    sub: "SUB",
    ud: "UD",
    sd: "SD",
    md: "MD",
    dq: "DQ",
    draw: "D",
    nc: "NC",
  };
  return labels[result] || result.toUpperCase();
}

const WEIGHT_SHORT = {
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
  catch: "CW",
};

export function shortWeightClass(code) {
  return WEIGHT_SHORT[code] || (code ? code.toUpperCase() : "—");
}

/** ISO date (YYYY-MM-DD) -> MM/YY. */
export function shortDate(iso) {
  if (!iso) return "—";
  const [y, m] = iso.split("-");
  return `${m}/${y.slice(2)}`;
}
