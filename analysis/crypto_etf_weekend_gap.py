#!/usr/bin/env python3
"""Reproduce the weekend BTC / Monday IBIT opening-gap analysis.

Data sources:
- Nasdaq historical API: IBIT daily OHLC (unadjusted price fields)
- Coinbase Exchange public candles API: BTC-USD OHLC

The script scans ordinary Friday-to-Monday trading gaps from IBIT's launch
through ANALYSIS_END, ranks them by the exact BTC move between the five-minute
candles beginning Friday 16:00 ET and Monday 09:30 ET, and exports the top
three cases.
"""

from __future__ import annotations

import json
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

import matplotlib.pyplot as plt
import matplotlib.ticker as mtick
import pandas as pd


ANALYSIS_START = date(2024, 1, 11)
ANALYSIS_END = date(2026, 9, 15)
NY = ZoneInfo("America/New_York")
ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "crypto-etf-03-weekend-price"
IMAGE_DIR = ROOT / "images" / "crypto-etf-03-weekend-price"
USER_AGENT = "zenn-crypto-etf-weekend-study/1.0"


def get_json(url: str) -> object:
    request = Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json, text/plain, */*",
        },
    )
    with urlopen(request, timeout=30) as response:
        return json.load(response)


def fetch_ibit_daily() -> pd.DataFrame:
    params = urlencode(
        {
            "assetclass": "etf",
            "fromdate": ANALYSIS_START.isoformat(),
            "todate": ANALYSIS_END.isoformat(),
            "limit": 5000,
        }
    )
    url = f"https://api.nasdaq.com/api/quote/IBIT/historical?{params}"
    payload = get_json(url)
    if not isinstance(payload, dict) or payload.get("data") is None:
        raise RuntimeError(f"Nasdaq response did not contain data: {payload}")

    rows = payload["data"]["tradesTable"]["rows"]
    frame = pd.DataFrame(rows)
    frame["date"] = pd.to_datetime(frame["date"], format="%m/%d/%Y")
    for column in ("open", "close", "high", "low"):
        frame[column] = pd.to_numeric(frame[column].str.replace("$", "", regex=False))
    frame["volume"] = pd.to_numeric(frame["volume"].str.replace(",", "", regex=False))
    return frame.sort_values("date").set_index("date")


def fetch_coinbase_candles(
    start: datetime,
    end: datetime,
    granularity: int,
    chunk_candles: int = 280,
) -> pd.DataFrame:
    """Fetch public Coinbase Exchange candles in bounded sequential chunks."""
    if start.tzinfo is None or end.tzinfo is None:
        raise ValueError("start and end must be timezone-aware")

    chunks: list[pd.DataFrame] = []
    cursor = start.astimezone(timezone.utc)
    end_utc = end.astimezone(timezone.utc)
    step = timedelta(seconds=granularity * chunk_candles)

    while cursor < end_utc:
        chunk_end = min(cursor + step, end_utc)
        params = urlencode(
            {
                "start": cursor.isoformat().replace("+00:00", "Z"),
                "end": chunk_end.isoformat().replace("+00:00", "Z"),
                "granularity": granularity,
            }
        )
        url = (
            "https://api.exchange.coinbase.com/products/BTC-USD/candles?"
            f"{params}"
        )
        payload = get_json(url)
        if not isinstance(payload, list):
            raise RuntimeError(f"Coinbase response was not a candle list: {payload}")
        if payload:
            chunk = pd.DataFrame(
                payload,
                columns=["time", "low", "high", "open", "close", "volume"],
            )
            chunks.append(chunk)
        cursor = chunk_end
        time.sleep(0.12)

    if not chunks:
        raise RuntimeError("Coinbase returned no candles")

    frame = pd.concat(chunks, ignore_index=True).drop_duplicates(subset=["time"])
    frame["time"] = pd.to_datetime(frame["time"], unit="s", utc=True)
    for column in ("low", "high", "open", "close", "volume"):
        frame[column] = pd.to_numeric(frame[column])
    return frame.sort_values("time").set_index("time")


def exact_open(frame: pd.DataFrame, instant: datetime) -> float:
    utc_instant = pd.Timestamp(instant.astimezone(timezone.utc))
    try:
        return float(frame.loc[utc_instant, "open"])
    except KeyError as error:
        raise KeyError(f"Missing candle beginning at {utc_instant}") from error


def friday_monday_pairs(ibit: pd.DataFrame) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    dates = list(ibit.index)
    pairs: list[tuple[pd.Timestamp, pd.Timestamp]] = []
    for friday, monday in zip(dates, dates[1:]):
        if friday.weekday() == 4 and monday.weekday() == 0 and (monday - friday).days == 3:
            pairs.append((friday, monday))
    return pairs


def scan_weekends(ibit: pd.DataFrame) -> pd.DataFrame:
    records: list[dict[str, object]] = []
    for friday, monday in friday_monday_pairs(ibit):
        friday_et = datetime.combine(friday.date(), datetime.min.time(), NY).replace(
            hour=16
        )
        monday_et = datetime.combine(monday.date(), datetime.min.time(), NY).replace(
            hour=9, minute=30
        )

        friday_candle = fetch_coinbase_candles(
            friday_et, friday_et + timedelta(minutes=5), granularity=300
        )
        monday_candle = fetch_coinbase_candles(
            monday_et, monday_et + timedelta(minutes=5), granularity=300
        )
        btc_start = exact_open(friday_candle, friday_et)
        btc_end = exact_open(monday_candle, monday_et)
        records.append(
            {
                "friday": friday,
                "monday": monday,
                "btc_friday_1600_et": btc_start,
                "btc_monday_0930_et": btc_end,
                "scan_btc_return": btc_end / btc_start - 1,
            }
        )
    return pd.DataFrame(records).sort_values(
        "scan_btc_return", key=lambda values: values.abs(), ascending=False
    )


def calculate_cases(
    ibit: pd.DataFrame, selected: pd.DataFrame
) -> tuple[pd.DataFrame, dict[str, pd.DataFrame]]:
    records: list[dict[str, object]] = []
    timelines: dict[str, pd.DataFrame] = {}

    for _, candidate in selected.iterrows():
        friday = pd.Timestamp(candidate["friday"])
        monday = pd.Timestamp(candidate["monday"])
        friday_et = datetime.combine(friday.date(), datetime.min.time(), NY).replace(
            hour=16
        )
        monday_et = datetime.combine(monday.date(), datetime.min.time(), NY).replace(
            hour=9, minute=30
        )
        candles = fetch_coinbase_candles(
            friday_et - timedelta(minutes=10),
            monday_et + timedelta(minutes=10),
            granularity=300,
        )
        btc_friday = exact_open(candles, friday_et)
        btc_monday = exact_open(candles, monday_et)
        btc_return = btc_monday / btc_friday - 1
        ibit_friday_close = float(ibit.loc[friday, "close"])
        ibit_monday_open = float(ibit.loc[monday, "open"])
        ibit_gap = ibit_monday_open / ibit_friday_close - 1

        label = f"{friday.date()} to {monday.date()}"
        normalized = candles.loc[
            pd.Timestamp(friday_et.astimezone(timezone.utc)) : pd.Timestamp(
                monday_et.astimezone(timezone.utc)
            )
        ].copy()
        normalized["normalized"] = normalized["close"] / btc_friday * 100
        timelines[label] = normalized
        records.append(
            {
                "friday": friday.date().isoformat(),
                "monday": monday.date().isoformat(),
                "btc_friday_1600_et": round(btc_friday, 2),
                "btc_monday_0930_et": round(btc_monday, 2),
                "btc_weekend_return_pct": round(btc_return * 100, 3),
                "ibit_friday_close": round(ibit_friday_close, 4),
                "ibit_monday_open": round(ibit_monday_open, 4),
                "ibit_monday_gap_pct": round(ibit_gap * 100, 3),
                "tracking_residual_pp": round((ibit_gap - btc_return) * 100, 3),
            }
        )

    return pd.DataFrame(records), timelines


def plot_comparison(cases: pd.DataFrame) -> None:
    labels = [f"{row.friday}\n→ {row.monday}" for row in cases.itertuples()]
    x = range(len(cases))
    width = 0.36

    fig, ax = plt.subplots(figsize=(10, 5.8))
    btc_bars = ax.bar(
        [value - width / 2 for value in x],
        cases["btc_weekend_return_pct"] / 100,
        width,
        label="BTC: Fri 16:00 → Mon 09:30 ET",
        color="#F7931A",
    )
    ibit_bars = ax.bar(
        [value + width / 2 for value in x],
        cases["ibit_monday_gap_pct"] / 100,
        width,
        label="IBIT: Fri close → Mon open",
        color="#163B65",
    )
    ax.bar_label(
        btc_bars,
        labels=[f"{value:.2f}%" for value in cases["btc_weekend_return_pct"]],
        padding=3,
        fontsize=8,
    )
    ax.bar_label(
        ibit_bars,
        labels=[f"{value:.2f}%" for value in cases["ibit_monday_gap_pct"]],
        padding=3,
        fontsize=8,
    )
    ax.axhline(0, color="#303030", linewidth=0.8)
    ax.set_xticks(list(x), labels)
    ax.yaxis.set_major_formatter(mtick.PercentFormatter(1.0))
    ax.set_ylabel("Return")
    ax.set_title("Weekend BTC move and IBIT's Monday opening gap")
    ax.legend(frameon=False, loc="best")
    ax.grid(axis="y", alpha=0.2)
    fig.tight_layout()
    fig.savefig(IMAGE_DIR / "weekend-gap-comparison.png", dpi=180)
    plt.close(fig)


def plot_timelines(cases: pd.DataFrame, timelines: dict[str, pd.DataFrame]) -> None:
    fig, axes = plt.subplots(len(cases), 1, figsize=(11, 8.4), sharex=False)
    if len(cases) == 1:
        axes = [axes]

    for ax, row, (label, timeline) in zip(axes, cases.itertuples(), timelines.items()):
        local_index = timeline.index.tz_convert(NY)
        ax.plot(local_index, timeline["normalized"], color="#F7931A", linewidth=1.8)
        ax.scatter(
            [local_index[0], local_index[-1]],
            [100, 100 * (1 + row.ibit_monday_gap_pct / 100)],
            color="#163B65",
            zorder=3,
            label="IBIT endpoints (Fri close = 100)",
        )
        ax.axhline(100, color="#777777", linewidth=0.8, linestyle="--")
        ax.set_title(label)
        ax.set_ylabel("Fri 16:00 = 100")
        ax.grid(alpha=0.18)

    axes[0].legend(frameon=False, loc="best")
    axes[-1].set_xlabel("America/New_York time")
    fig.suptitle("BTC kept trading while IBIT was closed", y=0.995, fontsize=14)
    fig.tight_layout()
    fig.savefig(IMAGE_DIR / "weekend-btc-timelines.png", dpi=180)
    plt.close(fig)


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)

    ibit = fetch_ibit_daily()
    scan = scan_weekends(ibit)
    selected = scan.head(3).copy()
    cases, timelines = calculate_cases(ibit, selected)

    cases.to_csv(DATA_DIR / "top-weekend-cases.csv", index=False)
    scan.assign(
        friday=scan["friday"].dt.date,
        monday=scan["monday"].dt.date,
        scan_btc_return_pct=scan["scan_btc_return"] * 100,
    )[
        [
            "friday",
            "monday",
            "btc_friday_1600_et",
            "btc_monday_0930_et",
            "scan_btc_return_pct",
        ]
    ].to_csv(
        DATA_DIR / "all-weekends-scan.csv", index=False
    )
    plot_comparison(cases)
    plot_timelines(cases, timelines)
    print(cases.to_string(index=False))


if __name__ == "__main__":
    main()
