/** Shared helpers for the static site. */

const DATA_BASE = "data";

export async function fetchJSON(path) {
  const response = await fetch(`${DATA_BASE}/${path}`);
  if (!response.ok) {
    throw new Error(`Failed to load ${path}: ${response.status}`);
  }
  return response.json();
}

export function getFighterIdFromURL() {
  const params = new URLSearchParams(window.location.search);
  return params.get("id");
}

export function fighterPageUrl(fighterId) {
  return `fighter.html?id=${encodeURIComponent(fighterId)}`;
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
