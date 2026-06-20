#!/usr/bin/env python3
"""Export precomputed JSON for the GitHub Pages static site."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

# Allow running as `python src/export_static_site.py` from repo root.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from elo_engine import (  # noqa: E402
    EloEngine,
    P4P_LABEL,
    apply_inactivity_decay,
    asymmetric_elo_update,
    ensure_division_elo,
    is_valid_fighter_id,
    load_config,
    load_fight_data,
)

INACTIVITY_YEARS_CURRENT_MODE = 2
TOP_N = 10

DIVISIONS: list[dict[str, str]] = [
    {"code": "p4p", "name": "Pound for Pound", "gender": "all"},
    {"code": "hw", "name": "Heavyweight", "gender": "M"},
    {"code": "lhw", "name": "Light Heavyweight", "gender": "M"},
    {"code": "mw", "name": "Middleweight", "gender": "M"},
    {"code": "ww", "name": "Welterweight", "gender": "M"},
    {"code": "lw", "name": "Lightweight", "gender": "M"},
    {"code": "fw", "name": "Featherweight", "gender": "M"},
    {"code": "bw", "name": "Bantamweight", "gender": "M"},
    {"code": "flw", "name": "Flyweight", "gender": "M"},
    {"code": "wsw", "name": "Women's Strawweight", "gender": "W"},
    {"code": "wflw", "name": "Women's Flyweight", "gender": "W"},
    {"code": "wbw", "name": "Women's Bantamweight", "gender": "W"},
    {"code": "wfw", "name": "Women's Featherweight", "gender": "W"},
]

DIVISION_NAMES = {d["code"]: d["name"] for d in DIVISIONS}
RANKING_DIVISION_CODES = [d["code"] for d in DIVISIONS]


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "fighter"


class FightRecorder(EloEngine):
    """Elo engine that records per-fight rating changes."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.fight_records: list[dict[str, Any]] = []
        self.last_fight_dates: dict[str, pd.Timestamp] = {}

    def process_fight(self, fight: pd.Series) -> None:
        result = str(fight.get("result", "")).strip().lower()
        weight_class = str(fight.get("weight", "")).strip().lower()
        winner_id = str(fight.get("winner_id", "")).strip()
        loser_id = str(fight.get("loser_id", "")).strip()

        if not is_valid_fighter_id(winner_id) or not is_valid_fighter_id(loser_id):
            return

        multiplier = self.config["RESULT_MULTIPLIERS"].get(result)
        if multiplier is None or multiplier == 0.0:
            return
        if not weight_class or weight_class == "nan":
            return

        fight_date = pd.to_datetime(fight["date"], errors="coerce")
        if pd.isna(fight_date):
            return

        k_adjusted = float(self.config["BASE_K_FACTOR"]) * float(multiplier)

        winner_state = self._get_state(winner_id)
        loser_state = self._get_state(loser_id)

        apply_inactivity_decay(winner_state, fight_date, self.config)
        apply_inactivity_decay(loser_state, fight_date, self.config)
        ensure_division_elo(winner_state, weight_class, self.starting_elo, self.carry_over_pct)
        ensure_division_elo(loser_state, weight_class, self.starting_elo, self.carry_over_pct)

        w_p4p_before = winner_state.p4p
        l_p4p_before = loser_state.p4p
        w_div_before = winner_state.divisional_elos[weight_class]
        l_div_before = loser_state.divisional_elos[weight_class]

        winner_state.p4p, loser_state.p4p = asymmetric_elo_update(
            winner_state.p4p,
            loser_state.p4p,
            k_adjusted,
            self.loss_multiplier,
        )
        winner_state.divisional_elos[weight_class], loser_state.divisional_elos[weight_class] = (
            asymmetric_elo_update(
                w_div_before,
                l_div_before,
                k_adjusted,
                self.loss_multiplier,
            )
        )

        winner_state.last_fight_weight = weight_class
        loser_state.last_fight_weight = weight_class
        winner_state.last_fight_date = fight_date
        loser_state.last_fight_date = fight_date

        self.last_fight_dates[winner_id] = fight_date
        self.last_fight_dates[loser_id] = fight_date

        self._append_snapshot(fight_date, winner_id, P4P_LABEL, winner_state.p4p)
        self._append_snapshot(fight_date, loser_id, P4P_LABEL, loser_state.p4p)
        self._append_snapshot(
            fight_date, winner_id, weight_class, winner_state.divisional_elos[weight_class]
        )
        self._append_snapshot(
            fight_date, loser_id, weight_class, loser_state.divisional_elos[weight_class]
        )

        fight_id = str(fight.get("fight_id", "")).strip()
        self.fight_records.append(
            {
                "fight_id": fight_id,
                "date": fight_date.strftime("%Y-%m-%d"),
                "weight_class": weight_class,
                "result": result,
                "winner_id": winner_id,
                "loser_id": loser_id,
                "winner_p4p_before": round(w_p4p_before, 2),
                "winner_p4p_after": round(winner_state.p4p, 2),
                "loser_p4p_before": round(l_p4p_before, 2),
                "loser_p4p_after": round(loser_state.p4p, 2),
                "winner_div_before": round(w_div_before, 2),
                "winner_div_after": round(winner_state.divisional_elos[weight_class], 2),
                "loser_div_before": round(l_div_before, 2),
                "loser_div_after": round(loser_state.divisional_elos[weight_class], 2),
            }
        )


def load_snapshots(snapshots_path: Path) -> pd.DataFrame:
    snapshots = pd.read_csv(snapshots_path, dtype={"fighter_id": str})
    snapshots["date"] = pd.to_datetime(snapshots["date"])
    snapshots["elo_score"] = pd.to_numeric(snapshots["elo_score"], errors="coerce")
    return snapshots.dropna(subset=["elo_score"])


def compute_rank_table(snapshots: pd.DataFrame) -> pd.DataFrame:
    """Assign rank per (date, weight_class) from monthly snapshots."""
    records: list[dict[str, Any]] = []
    for (date, weight_class), group in snapshots.groupby(["date", "weight_class"], sort=False):
        ranked = group.sort_values("elo_score", ascending=False).reset_index(drop=True)
        for rank, row in enumerate(ranked.itertuples(index=False), start=1):
            records.append(
                {
                    "date": date,
                    "weight_class": weight_class,
                    "fighter_id": row.fighter_id,
                    "rank": rank,
                    "elo": round(float(row.elo_score), 2),
                }
            )
    return pd.DataFrame(records)


def active_fighter_ids(
    last_fight_dates: dict[str, pd.Timestamp],
    reference_date: pd.Timestamp,
    years: int = INACTIVITY_YEARS_CURRENT_MODE,
) -> set[str]:
    cutoff = reference_date - pd.DateOffset(years=years)
    return {fid for fid, fight_date in last_fight_dates.items() if fight_date >= cutoff}


def build_rankings(
    snapshots: pd.DataFrame,
    reference_date: pd.Timestamp,
    active_ids: set[str] | None,
    top_n: int = TOP_N,
) -> dict[str, list[dict[str, Any]]]:
    latest = snapshots[snapshots["date"] == reference_date].copy()
    if active_ids is not None:
        latest = latest[latest["fighter_id"].isin(active_ids)]

    rankings: dict[str, list[dict[str, Any]]] = {}
    for code in RANKING_DIVISION_CODES:
        division_rows = latest[latest["weight_class"] == code].nlargest(top_n, "elo_score")
        entries: list[dict[str, Any]] = []
        for rank, row in enumerate(division_rows.itertuples(index=False), start=1):
            entries.append(
                {
                    "rank": rank,
                    "fighter_id": row.fighter_id,
                    "name": row.fighter_name,
                    "elo": round(float(row.elo_score), 2),
                }
            )
        rankings[code] = entries
    return rankings


def fighter_fight_list(
    fighter_id: str,
    fight_records: list[dict[str, Any]],
    fighter_names: dict[str, str],
) -> list[dict[str, Any]]:
    fights: list[dict[str, Any]] = []
    for record in fight_records:
        if record["winner_id"] != fighter_id and record["loser_id"] != fighter_id:
            continue

        is_winner = record["winner_id"] == fighter_id
        opponent_id = record["loser_id"] if is_winner else record["winner_id"]
        weight_class = record["weight_class"]

        if is_winner:
            p4p_before = record["winner_p4p_before"]
            p4p_after = record["winner_p4p_after"]
            div_before = record["winner_div_before"]
            div_after = record["winner_div_after"]
            outcome = "W"
        else:
            p4p_before = record["loser_p4p_before"]
            p4p_after = record["loser_p4p_after"]
            div_before = record["loser_div_before"]
            div_after = record["loser_div_after"]
            outcome = "L"

        fights.append(
            {
                "date": record["date"],
                "weight_class": weight_class,
                "weight_class_name": DIVISION_NAMES.get(weight_class, weight_class.title()),
                "opponent_id": opponent_id,
                "opponent_name": fighter_names.get(opponent_id, opponent_id),
                "result": record["result"],
                "outcome": outcome,
                "p4p_before": p4p_before,
                "p4p_after": p4p_after,
                "p4p_delta": round(p4p_after - p4p_before, 2),
                "div_before": div_before,
                "div_after": div_after,
                "div_delta": round(div_after - div_before, 2),
            }
        )

    fights.sort(key=lambda row: row["date"], reverse=True)
    return fights


def fighter_rank_history(
    fighter_id: str,
    rank_table: pd.DataFrame,
    divisions_fought: set[str],
) -> dict[str, list[dict[str, Any]]]:
    history: dict[str, list[dict[str, Any]]] = {}
    fighter_ranks = rank_table[rank_table["fighter_id"] == fighter_id]
    if fighter_ranks.empty:
        return history

    for weight_class in [P4P_LABEL, *sorted(divisions_fought)]:
        class_rows = fighter_ranks[fighter_ranks["weight_class"] == weight_class].sort_values("date")
        if class_rows.empty:
            continue
        history[weight_class] = [
            {
                "date": row.date.strftime("%Y-%m-%d"),
                "rank": int(row.rank),
                "elo": float(row.elo),
            }
            for row in class_rows.itertuples(index=False)
        ]
    return history


def load_export_state(state_path: Path) -> set[str]:
    if not state_path.exists():
        return set()
    payload = json.loads(state_path.read_text(encoding="utf-8"))
    return set(payload.get("processed_fight_ids", []))


def save_export_state(state_path: Path, processed_fight_ids: set[str]) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "processed_fight_ids": sorted(processed_fight_ids),
        "fight_count": len(processed_fight_ids),
    }
    state_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def new_fights_since(
    fights_df: pd.DataFrame,
    processed_fight_ids: set[str],
) -> tuple[pd.DataFrame, set[str]]:
    fights = fights_df.copy()
    fights["fight_id"] = fights["fight_id"].astype(str).str.strip()
    fights["date"] = pd.to_datetime(fights["date"], errors="coerce")
    fights = fights.dropna(subset=["date"]).sort_values("date", ascending=True)
    new_fights = fights[~fights["fight_id"].isin(processed_fight_ids)]
    affected_ids: set[str] = set()
    for _, fight in new_fights.iterrows():
        winner_id = str(fight.get("winner_id", "")).strip()
        loser_id = str(fight.get("loser_id", "")).strip()
        if is_valid_fighter_id(winner_id):
            affected_ids.add(winner_id)
        if is_valid_fighter_id(loser_id):
            affected_ids.add(loser_id)
    return new_fights, affected_ids


def build_fighter_profile(
    fighter_id: str,
    name: str,
    recorder: FightRecorder,
    rank_table: pd.DataFrame,
    divisions_by_fighter: dict[str, set[str]],
    active_ids: set[str],
) -> dict[str, Any]:
    divisions_fought = divisions_by_fighter.get(fighter_id, set())
    last_fight = recorder.last_fight_dates.get(fighter_id)
    return {
        "id": fighter_id,
        "name": name,
        "slug": slugify(name),
        "last_fight_date": last_fight.strftime("%Y-%m-%d") if last_fight is not None else None,
        "active_current_mode": fighter_id in active_ids,
        "divisions": sorted(divisions_fought),
        "division_names": {
            code: DIVISION_NAMES.get(code, code.title()) for code in sorted(divisions_fought)
        },
        "rank_history": fighter_rank_history(fighter_id, rank_table, divisions_fought),
        "fights": fighter_fight_list(fighter_id, recorder.fight_records, recorder.fighter_names),
    }


def update_fighters_index(
    index_path: Path,
    fighter_names: dict[str, str],
    new_fighter_ids: set[str] | None = None,
) -> list[dict[str, str]]:
    existing: dict[str, dict[str, str]] = {}
    if index_path.exists():
        for entry in json.loads(index_path.read_text(encoding="utf-8")):
            existing[entry["id"]] = entry

    ids_to_add = new_fighter_ids if new_fighter_ids is not None else set(fighter_names)
    for fighter_id in ids_to_add:
        if fighter_id in fighter_names:
            existing[fighter_id] = {
                "id": fighter_id,
                "name": fighter_names[fighter_id],
                "slug": slugify(fighter_names[fighter_id]),
            }

    fighter_index = sorted(existing.values(), key=lambda row: row["name"].lower())
    index_path.write_text(json.dumps(fighter_index, indent=2), encoding="utf-8")
    return fighter_index


def export_site(
    config_path: Path,
    data_dir: Path,
    snapshots_path: Path,
    output_dir: Path,
    *,
    incremental: bool = False,
) -> None:
    config = load_config(config_path)
    fights_df, fighter_names = load_fight_data(data_dir)
    snapshots = load_snapshots(snapshots_path)

    data_output = output_dir / "data"
    fighters_output = data_output / "fighters"
    fighters_output.mkdir(parents=True, exist_ok=True)
    state_path = data_output / "export_state.json"

    processed_fight_ids = load_export_state(state_path) if incremental else set()
    new_fights, affected_ids = new_fights_since(fights_df, processed_fight_ids)

    if incremental and new_fights.empty:
        print("No new fights; updating rankings and meta only.")
        fighters_to_export: set[str] = set()
    elif incremental:
        fighters_to_export = affected_ids
        print(f"Incremental export: {len(new_fights)} new fights, {len(fighters_to_export)} fighters.")
    else:
        fighters_to_export = set(fighter_names.keys())
        print(f"Full export: {len(fighters_to_export)} fighters.")

    recorder = FightRecorder(config=config, fighter_names=fighter_names)
    fights_sorted = fights_df.copy()
    fights_sorted["date"] = pd.to_datetime(fights_sorted["date"], errors="coerce")
    fights_sorted = fights_sorted.dropna(subset=["date"]).sort_values("date", ascending=True)
    for _, fight in fights_sorted.iterrows():
        recorder.process_fight(fight)

    reference_date = snapshots["date"].max()
    rank_table = compute_rank_table(snapshots)
    active_ids = active_fighter_ids(recorder.last_fight_dates, reference_date)

    meta = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "reference_date": reference_date.strftime("%Y-%m-%d"),
        "fighter_count": len(fighter_names),
        "fight_count": len(fights_sorted),
        "top_n": TOP_N,
        "inactivity_years_current_mode": INACTIVITY_YEARS_CURRENT_MODE,
        "divisions": DIVISIONS,
        "model": {
            "STARTING_ELO": config["STARTING_ELO"],
            "BASE_K_FACTOR": config["BASE_K_FACTOR"],
            "LOSS_MULTIPLIER": config.get("LOSS_MULTIPLIER", 1.5),
        },
    }
    (data_output / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

    rankings = {
        "reference_date": reference_date.strftime("%Y-%m-%d"),
        "historical": build_rankings(snapshots, reference_date, active_ids=None),
        "current": build_rankings(snapshots, reference_date, active_ids=active_ids),
    }
    (data_output / "rankings.json").write_text(json.dumps(rankings, indent=2), encoding="utf-8")

    divisions_by_fighter: dict[str, set[str]] = {}
    for record in recorder.fight_records:
        for fid in (record["winner_id"], record["loser_id"]):
            divisions_by_fighter.setdefault(fid, set()).add(record["weight_class"])

    for fighter_id in fighters_to_export:
        name = fighter_names.get(fighter_id)
        if not name:
            continue
        profile = build_fighter_profile(
            fighter_id,
            name,
            recorder,
            rank_table,
            divisions_by_fighter,
            active_ids,
        )
        (fighters_output / f"{fighter_id}.json").write_text(
            json.dumps(profile, indent=2),
            encoding="utf-8",
        )

    all_fight_ids = set(fights_sorted["fight_id"].astype(str).str.strip())
    save_export_state(state_path, all_fight_ids)

    index_path = data_output / "fighters_index.json"
    if incremental and index_path.exists():
        existing_ids = {entry["id"] for entry in json.loads(index_path.read_text(encoding="utf-8"))}
        new_fighter_ids = set(fighter_names) - existing_ids
        if new_fighter_ids:
            fighter_index = update_fighters_index(index_path, fighter_names, new_fighter_ids)
        else:
            fighter_index = json.loads(index_path.read_text(encoding="utf-8"))
    else:
        fighter_index = update_fighters_index(index_path, fighter_names)

    print(f"Exported site data to {data_output}")
    print(f"  Fighter profiles written: {len(fighters_to_export):,}")
    print(f"  Fighters indexed: {len(fighter_index):,}")
    print(f"  Reference date: {reference_date.strftime('%Y-%m-%d')}")
    print(f"  Active (current mode): {len(active_ids):,}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export JSON data for GitHub Pages site.")
    parser.add_argument("--config", type=Path, default=Path("config/config.json"))
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument(
        "--snapshots",
        type=Path,
        default=Path("data/historical_elo_snapshots.csv"),
    )
    parser.add_argument("--output-dir", type=Path, default=Path("docs"))
    parser.add_argument(
        "--incremental",
        action="store_true",
        help="Only rewrite fighter profiles affected by new fights since last export.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    export_site(
        args.config,
        args.data_dir,
        args.snapshots,
        args.output_dir,
        incremental=args.incremental,
    )


if __name__ == "__main__":
    main()
