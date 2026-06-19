#!/usr/bin/env python3
"""Multi-dimensional Elo rating engine for UFC fight history."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import pandas as pd

P4P_LABEL = "p4p"
SNAPSHOT_COLUMNS = ["date", "fighter_id", "fighter_name", "weight_class", "elo_score"]
INVALID_FIGHTER_IDS = {"", "none", "nan"}


@dataclass
class FighterState:
    p4p: float
    last_fight_weight: Optional[str] = None
    divisional_elos: dict[str, float] = field(default_factory=dict)
    last_fight_date: Optional[pd.Timestamp] = None


def load_config(config_path: Path) -> dict[str, Any]:
    with config_path.open(encoding="utf-8") as handle:
        return json.load(handle)


def expected_score(rating_a: float, rating_b: float) -> float:
    return 1.0 / (1.0 + 10.0 ** ((rating_b - rating_a) / 400.0))


def is_valid_fighter_id(fighter_id: Any) -> bool:
    if fighter_id is None or pd.isna(fighter_id):
        return False
    return str(fighter_id).strip().lower() not in INVALID_FIGHTER_IDS


def apply_inactivity_decay(
    state: FighterState,
    fight_date: pd.Timestamp,
    config: dict[str, Any],
) -> None:
    """Placeholder for inactivity decay; no-op when disabled in config."""
    if not config.get("ENABLE_INACTIVITY_DECAY", False):
        return
    if state.last_fight_date is None:
        return

    months_idle = (fight_date.year - state.last_fight_date.year) * 12 + (
        fight_date.month - state.last_fight_date.month
    )
    threshold = config.get("INACTIVITY_MONTHS_THRESHOLD", 12)
    decay_pct = config.get("INACTIVITY_DECAY_PCT", 0.05)

    if months_idle >= threshold:
        decay_factor = 1.0 - decay_pct
        state.p4p *= decay_factor
        for weight_class in state.divisional_elos:
            state.divisional_elos[weight_class] *= decay_factor


def ensure_division_elo(
    state: FighterState,
    weight_class: str,
    starting_elo: float,
    carry_over_pct: float,
) -> float:
    if weight_class in state.divisional_elos:
        return state.divisional_elos[weight_class]

    if state.last_fight_weight is None:
        state.divisional_elos[weight_class] = starting_elo
    else:
        previous_elo = state.divisional_elos.get(state.last_fight_weight, starting_elo)
        if previous_elo > starting_elo:
            # Carry over 90% of a strong rating, but never debut below starting Elo.
            state.divisional_elos[weight_class] = max(previous_elo * carry_over_pct, starting_elo)
        else:
            # At or below baseline in the prior division — start fresh at starting Elo.
            state.divisional_elos[weight_class] = starting_elo

    return state.divisional_elos[weight_class]


def asymmetric_elo_update(
    rating_winner: float,
    rating_loser: float,
    k_adjusted: float,
    loss_multiplier: float,
) -> tuple[float, float]:
    """Apply Elo update where losses cost loss_multiplier times more than wins gain."""
    expected_winner = expected_score(rating_winner, rating_loser)
    expected_loser = expected_score(rating_loser, rating_winner)
    delta_winner = k_adjusted * (1.0 - expected_winner)
    delta_loser = k_adjusted * loss_multiplier * (0.0 - expected_loser)
    return rating_winner + delta_winner, rating_loser + delta_loser


class EloEngine:
    def __init__(self, config: dict[str, Any], fighter_names: dict[str, str]) -> None:
        self.config = config
        self.fighter_names = fighter_names
        self.starting_elo = float(config["STARTING_ELO"])
        self.carry_over_pct = float(config["DEBUT_CARRY_OVER_PCT"])
        self.loss_multiplier = float(config.get("LOSS_MULTIPLIER", 1.5))
        self.fighters_state: dict[str, FighterState] = {}
        self.event_snapshots: list[dict[str, Any]] = []

    def _get_state(self, fighter_id: str) -> FighterState:
        if fighter_id not in self.fighters_state:
            self.fighters_state[fighter_id] = FighterState(p4p=self.starting_elo)
        return self.fighters_state[fighter_id]

    def _fighter_name(self, fighter_id: str) -> str:
        return self.fighter_names.get(fighter_id, fighter_id)

    def _append_snapshot(
        self,
        fight_date: pd.Timestamp,
        fighter_id: str,
        weight_class: str,
        elo_score: float,
    ) -> None:
        self.event_snapshots.append(
            {
                "date": fight_date.strftime("%Y-%m-%d"),
                "fighter_id": fighter_id,
                "fighter_name": self._fighter_name(fighter_id),
                "weight_class": weight_class,
                "elo_score": round(elo_score, 2),
            }
        )

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

        winner_state.p4p, loser_state.p4p = asymmetric_elo_update(
            winner_state.p4p,
            loser_state.p4p,
            k_adjusted,
            self.loss_multiplier,
        )

        winner_div = winner_state.divisional_elos[weight_class]
        loser_div = loser_state.divisional_elos[weight_class]
        winner_state.divisional_elos[weight_class], loser_state.divisional_elos[weight_class] = (
            asymmetric_elo_update(winner_div, loser_div, k_adjusted, self.loss_multiplier)
        )

        winner_state.last_fight_weight = weight_class
        loser_state.last_fight_weight = weight_class
        winner_state.last_fight_date = fight_date
        loser_state.last_fight_date = fight_date

        self._append_snapshot(fight_date, winner_id, P4P_LABEL, winner_state.p4p)
        self._append_snapshot(fight_date, loser_id, P4P_LABEL, loser_state.p4p)
        self._append_snapshot(
            fight_date,
            winner_id,
            weight_class,
            winner_state.divisional_elos[weight_class],
        )
        self._append_snapshot(
            fight_date,
            loser_id,
            weight_class,
            loser_state.divisional_elos[weight_class],
        )

    def run(self, fights_df: pd.DataFrame) -> pd.DataFrame:
        fights = fights_df.copy()
        fights["date"] = pd.to_datetime(fights["date"], errors="coerce")
        fights = fights.dropna(subset=["date"]).sort_values("date", ascending=True)

        for _, fight in fights.iterrows():
            self.process_fight(fight)

        if not self.event_snapshots:
            return pd.DataFrame(columns=SNAPSHOT_COLUMNS)

        event_df = pd.DataFrame(self.event_snapshots)
        return build_forward_filled_snapshots(event_df)


def build_forward_filled_snapshots(event_df: pd.DataFrame) -> pd.DataFrame:
    """Expand event snapshots to a monthly forward-filled time series."""
    event_df = event_df.copy()
    event_df["date"] = pd.to_datetime(event_df["date"])
    event_df["elo_score"] = pd.to_numeric(event_df["elo_score"], errors="coerce")
    event_df = event_df.dropna(subset=["elo_score"])

    # Keep the latest observation per fighter/class on each fight date.
    event_df = (
        event_df.sort_values("date")
        .groupby(["date", "fighter_id", "weight_class"], as_index=False)
        .last()
    )

    filled_frames: list[pd.DataFrame] = []
    global_max = event_df["date"].max()

    for (fighter_id, weight_class), group in event_df.groupby(
        ["fighter_id", "weight_class"],
        dropna=False,
    ):
        group = group.sort_values("date").set_index("date")
        fighter_name = str(group["fighter_name"].iloc[-1])

        monthly = group[["elo_score"]].resample("MS").last()
        full_index = pd.date_range(monthly.index.min(), global_max, freq="MS")
        monthly = monthly.reindex(full_index).ffill().dropna(subset=["elo_score"])
        if monthly.empty:
            continue

        frame = monthly.reset_index().rename(columns={"index": "date"})
        frame["fighter_id"] = fighter_id
        frame["fighter_name"] = fighter_name
        frame["weight_class"] = weight_class
        filled_frames.append(frame)

    if not filled_frames:
        return pd.DataFrame(columns=SNAPSHOT_COLUMNS)

    snapshots = pd.concat(filled_frames, ignore_index=True)
    snapshots["date"] = snapshots["date"].dt.strftime("%Y-%m-%d")
    snapshots["elo_score"] = snapshots["elo_score"].round(2)
    return snapshots[SNAPSHOT_COLUMNS].sort_values(
        ["date", "weight_class", "elo_score"],
        ascending=[True, True, False],
    )


def load_fight_data(data_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    fights_path = data_dir / "fights.csv"
    fighters_path = data_dir / "fighters.csv"

    fights_df = pd.read_csv(fights_path, dtype=str)
    fighters_df = pd.read_csv(fighters_path, dtype=str)

    fighter_names = dict(zip(fighters_df["fighter_id"], fighters_df["name"]))
    return fights_df, fighter_names


def run_engine(
    config_path: Path,
    data_dir: Path,
    output_path: Path,
) -> pd.DataFrame:
    config = load_config(config_path)
    fights_df, fighter_names = load_fight_data(data_dir)

    engine = EloEngine(config=config, fighter_names=fighter_names)
    snapshots = engine.run(fights_df)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    snapshots.to_csv(output_path, index=False)
    return snapshots


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run UFC multi-dimensional Elo engine.")
    parser.add_argument("--config", type=Path, default=Path("config/config.json"))
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/historical_elo_snapshots.csv"),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    snapshots = run_engine(args.config, args.data_dir, args.output)
    print(
        f"Saved {len(snapshots):,} forward-filled snapshot rows to {args.output} "
        f"({snapshots['fighter_id'].nunique()} fighters)."
    )


if __name__ == "__main__":
    main()
