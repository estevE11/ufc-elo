#!/usr/bin/env python3
"""UFCStats.com scraper — builds fighters.csv and fights.csv."""

from __future__ import annotations

import argparse
import hashlib
import logging
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin

import pandas as pd
import requests
from bs4 import BeautifulSoup

BASE_URL = "http://ufcstats.com"
COMPLETED_EVENTS_URL = f"{BASE_URL}/statistics/events/completed"
RATE_LIMIT_SECONDS = 1.5
USER_AGENT = "Mozilla/5.0 (compatible; UFC-ELO-Scraper/1.0)"

FIGHTERS_COLUMNS = ["fighter_id", "name"]
FIGHTS_COLUMNS = [
    "fight_id",
    "date",
    "winner_id",
    "loser_id",
    "result",
    "weight",
    "championship",
]

WEIGHT_PATTERNS: list[tuple[str, str]] = [
    ("women's strawweight", "wsw"),
    ("women's flyweight", "wflw"),
    ("women's bantamweight", "wbw"),
    ("women's featherweight", "wfw"),
    ("light heavyweight", "lhw"),
    ("heavyweight", "hw"),
    ("middleweight", "mw"),
    ("welterweight", "ww"),
    ("lightweight", "lw"),
    ("featherweight", "fw"),
    ("bantamweight", "bw"),
    ("flyweight", "flw"),
    ("catch weight", "catch"),
    ("catchweight", "catch"),
]

def sanitize(text: Optional[str]) -> str:
    if not text:
        return ""
    return re.sub(r"\s+", " ", text.replace("\n", " ")).strip()


def extract_id(url: str, segment: str) -> Optional[str]:
    match = re.search(rf"{segment}/([a-f0-9]+)", url)
    return match.group(1) if match else None


def normalize_weight(text: str) -> str:
    lowered = sanitize(text).lower()
    for pattern, code in WEIGHT_PATTERNS:
        if pattern in lowered:
            return code
    return lowered or "unknown"


def normalize_result(method_text: str, flag_text: str) -> str:
    flag = sanitize(flag_text).lower()
    if flag == "draw":
        return "draw"
    if flag == "nc":
        return "nc"

    method = sanitize(method_text).split(" ")[0].upper()
    full_method = sanitize(method_text).upper()

    if method.startswith("KO/TKO") or method in {"KO", "TKO"}:
        return "ko/tko"
    if "SUB" in full_method or "SUBMISSION" in full_method:
        return "sub"
    if method.startswith("DQ") or full_method.startswith("DQ"):
        return "dq"
    if "CNC" in full_method or "OVERTURNED" in full_method:
        return "nc"
    if method.startswith("U-DEC"):
        return "ud"
    if method.startswith("S-DEC"):
        return "sd"
    if method.startswith("M-DEC"):
        return "md"
    return method.lower()


def normalize_championship(bout_text: str) -> str:
    text = sanitize(bout_text).lower()
    if "bmf" in text:
        return "bmf"
    if "interim" in text:
        return "in"
    if "title" in text or "championship" in text:
        return "un"
    return "none"


class UFCStatsScraper:
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.fighters_path = data_dir / "fighters.csv"
        self.fights_path = data_dir / "fights.csv"
        self.error_log_path = data_dir / "scraper_errors.log"

        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})

        self.fighters_df = self._load_csv(self.fighters_path, FIGHTERS_COLUMNS)
        self.fights_df = self._load_csv(self.fights_path, FIGHTS_COLUMNS)
        self.known_fighter_ids = set(self.fighters_df["fighter_id"].astype(str))
        self.known_fight_ids = set(self.fights_df["fight_id"].astype(str))

        self._configure_error_logging()

    @staticmethod
    def _load_csv(path: Path, columns: list[str]) -> pd.DataFrame:
        if path.exists():
            return pd.read_csv(path, dtype=str).fillna("")
        return pd.DataFrame(columns=columns)

    def _configure_error_logging(self) -> None:
        self.error_logger = logging.getLogger("ufc_scraper_errors")
        self.error_logger.setLevel(logging.ERROR)
        self.error_logger.handlers.clear()
        handler = logging.FileHandler(self.error_log_path, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s | %(message)s"))
        self.error_logger.addHandler(handler)

    def _log_error(self, context: str, error: Exception) -> None:
        self.error_logger.error("%s | %s: %s", context, type(error).__name__, error)

    def _is_challenge_page(self, html: str) -> bool:
        return "Checking your browser" in html or 'var nonce="' in html and "b-statistics__table-events" not in html

    def _solve_challenge(self, html: str) -> None:
        match = re.search(r'var nonce="([^"]+)"', html)
        if not match:
            raise RuntimeError("Anti-bot challenge page missing nonce")
        nonce = match.group(1)
        target = "00"
        counter = 0
        while True:
            digest = hashlib.sha256(f"{nonce}:{counter}".encode()).hexdigest()
            if digest.startswith(target):
                break
            counter += 1
        self.session.post(
            urljoin(BASE_URL, "/__c"),
            data={"nonce": nonce, "n": counter},
            timeout=30,
        )

    def fetch(self, url: str) -> Optional[BeautifulSoup]:
        time.sleep(RATE_LIMIT_SECONDS)
        try:
            response = self.session.get(url, timeout=60)
            response.raise_for_status()
            if self._is_challenge_page(response.text):
                self._solve_challenge(response.text)
                time.sleep(RATE_LIMIT_SECONDS)
                response = self.session.get(url, timeout=60)
                response.raise_for_status()
            return BeautifulSoup(response.text, "html.parser")
        except Exception as exc:
            self._log_error(f"fetch {url}", exc)
            return None

    def _save_csvs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.fighters_df.to_csv(self.fighters_path, index=False)
        self.fights_df.to_csv(self.fights_path, index=False)

    def _add_fighter(self, fighter_id: str, name: str) -> None:
        if not fighter_id or fighter_id in self.known_fighter_ids:
            return
        name = sanitize(name)
        row = pd.DataFrame([{"fighter_id": fighter_id, "name": name}])
        self.fighters_df = pd.concat([self.fighters_df, row], ignore_index=True)
        self.known_fighter_ids.add(fighter_id)

    def _add_fight(self, fight_record: dict[str, str]) -> None:
        fight_id = fight_record["fight_id"]
        if fight_id in self.known_fight_ids:
            return
        row = pd.DataFrame([fight_record])
        self.fights_df = pd.concat([self.fights_df, row], ignore_index=True)
        self.known_fight_ids.add(fight_id)

    def _parse_event_date(self, soup: BeautifulSoup) -> Optional[str]:
        for item in soup.select("li.b-list__box-list-item"):
            text = sanitize(item.get_text(" ", strip=True))
            if text.lower().startswith("date:"):
                raw_date = text.split(":", 1)[1].strip()
                try:
                    parsed = datetime.strptime(raw_date, "%B %d, %Y")
                    return parsed.strftime("%Y-%m-%d")
                except ValueError as exc:
                    self._log_error(f"date parse '{raw_date}'", exc)
                    return None
        return None

    def _fetch_bout_head(self, fight_url: str) -> str:
        soup = self.fetch(fight_url)
        if not soup:
            return ""
        head = soup.select_one(".b-fight-details__fight-head")
        return sanitize(head.get_text(" ", strip=True)) if head else ""

    def _parse_fight_row(
        self,
        row,
        event_date: str,
        stop_on_existing: bool,
    ) -> str:
        """
        Parse a single bout row. Returns:
        - 'stop' if incremental mode hit an existing fight
        - 'ok' on success
        - 'error' on failure
        """
        fight_link = row.get("data-link") or ""
        fight_id = extract_id(fight_link, "fight-details")
        if not fight_id:
            return "error"

        if stop_on_existing and fight_id in self.known_fight_ids:
            return "stop"

        if fight_id in self.known_fight_ids:
            return "ok"

        cols = row.select("td")
        if len(cols) < 8:
            self._log_error(f"fight row columns fight_id={fight_id}", ValueError("unexpected column count"))
            return "error"

        flag = row.select_one("a.b-flag")
        flag_text = sanitize(flag.get_text()) if flag else ""

        fighter_links = cols[1].select('a[href*="fighter-details"]')
        if len(fighter_links) < 2:
            self._log_error(f"fighter links fight_id={fight_id}", ValueError("missing fighter links"))
            return "error"

        fighter_pairs = []
        for link in fighter_links[:2]:
            fighter_id = extract_id(link.get("href", ""), "fighter-details")
            fighter_name = sanitize(link.get_text())
            if fighter_id:
                fighter_pairs.append((fighter_id, fighter_name))

        if len(fighter_pairs) < 2:
            return "error"

        flag_lower = flag_text.lower()
        if flag_lower in {"draw", "nc"}:
            winner_id = "None"
            loser_id = "None"
        else:
            winner_id, _ = fighter_pairs[0]
            loser_id, _ = fighter_pairs[1]

        for fighter_id, fighter_name in fighter_pairs:
            self._add_fighter(fighter_id, fighter_name)

        weight_col = cols[6]
        weight_text = sanitize(weight_col.get_text(" ", strip=True))
        has_belt = bool(weight_col.select('img[src*="belt"]'))

        method_text = sanitize(cols[7].get_text(" ", strip=True))

        if has_belt:
            bout_head = self._fetch_bout_head(fight_link)
            weight_source = bout_head or weight_text
            championship = normalize_championship(bout_head)
        else:
            weight_source = weight_text
            championship = normalize_championship(weight_text)

        fight_record = {
            "fight_id": fight_id,
            "date": event_date,
            "winner_id": winner_id,
            "loser_id": loser_id,
            "result": normalize_result(method_text, flag_text),
            "weight": normalize_weight(weight_source),
            "championship": championship,
        }
        self._add_fight(fight_record)
        return "ok"

    def _parse_event(self, event_url: str, stop_on_existing: bool) -> str:
        soup = self.fetch(event_url)
        if not soup:
            return "error"

        event_date = self._parse_event_date(soup)
        if not event_date:
            self._log_error(f"event date {event_url}", ValueError("missing event date"))
            return "error"

        for row in soup.select("tr.b-fight-details__table-row[data-link]"):
            status = self._parse_fight_row(row, event_date, stop_on_existing)
            if status == "stop":
                return "stop"
        return "ok"

    def _collect_event_urls(self, full_scrape: bool) -> list[str]:
        index_url = f"{COMPLETED_EVENTS_URL}?page=all" if full_scrape else COMPLETED_EVENTS_URL
        soup = self.fetch(index_url)
        if not soup:
            return []

        urls: list[str] = []
        for row in soup.select("table.b-statistics__table-events tr.b-statistics__table-row"):
            link = row.select_one('a[href*="event-details"]')
            if link and link.get("href"):
                urls.append(link["href"])
        return urls

    def run(self, mode: str) -> None:
        full_scrape = mode == "full"
        stop_on_existing = not full_scrape

        event_urls = self._collect_event_urls(full_scrape=full_scrape)
        if not event_urls:
            print("No events found.", file=sys.stderr)
            return

        print(f"Processing {len(event_urls)} events ({mode} mode)...")

        for index, event_url in enumerate(event_urls, start=1):
            try:
                status = self._parse_event(event_url, stop_on_existing=stop_on_existing)
                self._save_csvs()
                print(
                    f"[{index}/{len(event_urls)}] {event_url.split('/')[-1]} "
                    f"— fighters: {len(self.fighters_df)}, fights: {len(self.fights_df)}"
                )
                if status == "stop":
                    print("Incremental update complete: reached existing fight.")
                    break
            except Exception as exc:
                self._log_error(f"event {event_url}", exc)
                continue

        self._save_csvs()
        print(
            f"Done. Saved {len(self.fighters_df)} fighters and {len(self.fights_df)} fights "
            f"to {self.data_dir}"
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scrape ufcstats.com into fighters.csv and fights.csv",
    )
    parser.add_argument(
        "--mode",
        choices=["full", "incremental"],
        default="incremental",
        help="full: scrape all completed events; incremental: page 1 only, stop at known fights",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path("db"),
        help="Directory for CSV output and scraper_errors.log (default: db)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    scraper = UFCStatsScraper(data_dir=args.data_dir)
    scraper.run(mode=args.mode)


if __name__ == "__main__":
    main()
