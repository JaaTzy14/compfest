from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


BASE_URL = "https://infopangan.jakarta.go.id/api2/v1/public/report/download"

DATA_PATH = Path(__file__).resolve().parents[2] / "data" / "prices_split_base.parquet"

TARGET_MARKETS = {
    8: "Pasar Glodok",
    12: "Pasar Kramat Jati",
    14: "Pasar Perumnas Klender",
    28: "Pasar Kebayoran Lama",
    38: "Pasar Kalideres",
    41: "Pasar Jembatan Lima",
}

TARGET_COMMODITIES = {
    8: "Cabe Merah Keriting",
    10: "Cabe Rawit Merah",
    12: "Bawang Merah",
    17: "Telur Ayam Ras",
    22: "Tomat Buah",
}

MODEL_BASE_COLUMNS = [
    "date",
    "market_id",
    "market_name",
    "commodity_no",
    "commodity",
    "price_clean",
]

DATA_COLUMNS = [
    "date",
    "market_id",
    "market_name",
    "commodity_no",
    "commodity",
    "price_clean",
    "is_observed_raw",
    "is_observed_clean",
    "is_gross_outlier",
    "is_cross_market_anomaly",
    "is_temporal_anomaly",
    "split",
    "last_observed_price",
    "days_since_last_observation",
    "pred_last_observed",
    "pred_seasonal_7",
    "pred_rolling_median_7",
]

FLAG_COLUMNS = [
    "is_observed_raw",
    "is_observed_clean",
    "is_gross_outlier",
    "is_cross_market_anomaly",
    "is_temporal_anomaly",
]

FEATURE_COLUMNS = [
    "last_observed_price",
    "days_since_last_observation",
    "pred_last_observed",
    "pred_seasonal_7",
    "pred_rolling_median_7",
]

KEY_COLUMNS = ["date", "market_id", "commodity_no"]


@dataclass(frozen=True)
class RefreshResult:
    year_month: str
    downloaded_markets: int
    failed_market_ids: tuple[int, ...]
    parsed_observations: int
    gross_outliers_removed: int
    calendar_rows_inserted: int
    observations_inserted: int
    observations_updated: int
    observations_unchanged: int
    latest_date_before: str | None
    latest_date_after: str | None
    data_changed: bool


def current_year_month() -> str:
    return datetime.now(ZoneInfo("Asia/Jakarta")).strftime("%Y-%m")


def make_session() -> requests.Session:
    session = requests.Session()

    retry = Retry(
        total=4,
        connect=4,
        read=4,
        status=4,
        backoff_factor=1.2,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
        respect_retry_after_header=True,
    )

    session.mount("https://", HTTPAdapter(max_retries=retry))

    session.headers.update(
        {
            "Accept": (
                "application/vnd.openxmlformats-officedocument."
                "spreadsheetml.sheet,application/octet-stream,*/*"
            ),
            "Referer": "https://infopangan.jakarta.go.id/statistic",
            "User-Agent": "Mozilla/5.0 (compatible; AIC-daily-refresh/2.0)",
        }
    )

    return session


def download_market_report(
    session: requests.Session,
    market_id: int,
    year_month: str,
) -> bytes:
    response = session.get(
        BASE_URL,
        params={
            "filterBy": "market",
            "Id": market_id,
            "yearMonth": year_month,
            "fullname": "ja",
            "organization_name": "UI",
        },
        timeout=60,
    )

    response.raise_for_status()

    # XLSX = ZIP container, magic bytes "PK".
    if not response.content.startswith(b"PK"):
        raise ValueError(
            f"market_id={market_id} {year_month}: response bukan XLSX"
        )

    return response.content


def _day_number(value: Any) -> int | None:
    """Convert header cell ke nomor hari 1..31 jika memang daily column."""
    if pd.isna(value):
        return None

    if isinstance(value, (int, np.integer)):
        day = int(value)
    elif isinstance(value, (float, np.floating)) and float(value).is_integer():
        day = int(value)
    else:
        return None

    return day if 1 <= day <= 31 else None


def parse_market_report(
    content: bytes,
    market_id: int,
    year_month: str,
) -> pd.DataFrame:
    """
    Support dua format:
    A) No | Nama | 1 | 2 | ... | Minimal | Rata-rata | Maksimal
    B) No | Nama | Minimal | Rata-rata | Maksimal

    Format B dikembalikan sebagai empty karena tidak punya observasi harian.
    """
    raw = pd.read_excel(BytesIO(content), sheet_name=0, header=None)

    header_mask = raw.eq("No").any(axis=1)
    if not header_mask.any():
        return pd.DataFrame(
            columns=MODEL_BASE_COLUMNS[:-1] + ["price_raw"]
        )

    header_idx = int(header_mask.idxmax())
    headers = raw.iloc[header_idx].tolist()

    data = raw.iloc[header_idx + 1 :].copy()
    data.columns = headers
    data = data.dropna(how="all")

    if "No" not in data.columns or "Nama" not in data.columns:
        return pd.DataFrame(
            columns=MODEL_BASE_COLUMNS[:-1] + ["price_raw"]
        )

    daily_cols: list[tuple[Any, int]] = []
    for col in data.columns:
        day = _day_number(col)
        if day is not None:
            daily_cols.append((col, day))

    # Summary-only XLSX.
    if not daily_cols:
        return pd.DataFrame(
            columns=MODEL_BASE_COLUMNS[:-1] + ["price_raw"]
        )

    commodity_no_numeric = pd.to_numeric(data["No"], errors="coerce")
    wanted = data[
        commodity_no_numeric.isin(TARGET_COMMODITIES.keys())
    ].copy()

    if wanted.empty:
        return pd.DataFrame(
            columns=MODEL_BASE_COLUMNS[:-1] + ["price_raw"]
        )

    rows: list[dict[str, Any]] = []

    for idx, row in wanted.iterrows():
        commodity_no = int(pd.to_numeric(row["No"]))

        for raw_col, day in daily_cols:
            date = pd.to_datetime(
                f"{year_month}-{day:02d}",
                errors="coerce",
            )

            if pd.isna(date):
                continue

            price = pd.to_numeric(row[raw_col], errors="coerce")

            # Blank / zero / negative bukan clean observation.
            if pd.isna(price) or float(price) <= 0:
                continue

            rows.append(
                {
                    "date": date.normalize(),
                    "market_id": int(market_id),
                    "market_name": TARGET_MARKETS[market_id],
                    "commodity_no": commodity_no,
                    "commodity": TARGET_COMMODITIES[commodity_no],
                    "price_raw": float(price),
                }
            )

    return pd.DataFrame(
        rows,
        columns=MODEL_BASE_COLUMNS[:-1] + ["price_raw"],
    )


def clean_incoming_prices(
    base: pd.DataFrame,
    incoming: pd.DataFrame,
) -> tuple[pd.DataFrame, int]:
    """
    Conservative gross-outlier cleaning yang mengikuti rule cleaning project:
    hapus hanya bila nilai ekstrem terhadap BOTH:
      - median commodity-wide
      - median market x commodity

    threshold:
      < 0.2x median atau > 5x median
    """
    if incoming.empty:
        out = incoming.copy()
        out["price_clean"] = pd.Series(dtype=float)
        return out, 0

    history = base[base["price_clean"].notna() & (base["price_clean"] > 0)].copy()

    commodity_median = (
        history.groupby("commodity_no")["price_clean"]
        .median()
        .to_dict()
    )

    pair_median = (
        history.groupby(["market_id", "commodity_no"])["price_clean"]
        .median()
        .to_dict()
    )

    cleaned = incoming.copy()
    flags = []

    for row in cleaned.itertuples(index=False):
        price = float(row.price_raw)
        cm = commodity_median.get(row.commodity_no)
        pm = pair_median.get((row.market_id, row.commodity_no))

        # Kalau median historis belum tersedia, jangan invent threshold.
        if cm is None or pm is None or pd.isna(cm) or pd.isna(pm):
            gross = False
        else:
            too_low = (price < 0.2 * cm) and (price < 0.2 * pm)
            too_high = (price > 5.0 * cm) and (price > 5.0 * pm)
            gross = too_low or too_high

        flags.append(gross)

    cleaned["_gross_outlier"] = flags
    cleaned["price_clean"] = cleaned["price_raw"].where(
        ~cleaned["_gross_outlier"],
        np.nan,
    )

    removed = int(cleaned["_gross_outlier"].sum())

    return cleaned, removed


def _validate_model_base(df: pd.DataFrame) -> None:
    missing = set(DATA_COLUMNS) - set(df.columns)
    if missing:
        raise ValueError(
            "Dataset kehilangan kolom wajib: "
            + ", ".join(sorted(missing))
        )

    if df.duplicated(KEY_COLUMNS).any():
        raise ValueError("Ada duplicate date × market × commodity.")

    check = df.sort_values(["market_id", "commodity_no", "date"])
    gaps = (
        check.groupby(["market_id", "commodity_no"])["date"]
        .diff()
        .dt.days
        .dropna()
    )

    if not gaps.eq(1).all():
        bad = gaps[~gaps.eq(1)].head().tolist()
        raise ValueError(
            f"Calendar grid tidak daily-continuous. Contoh gap: {bad}"
        )


def _recompute_features(df: pd.DataFrame) -> pd.DataFrame:
    out = df.sort_values(["market_id", "commodity_no", "date"]).copy()
    group = out.groupby(["market_id", "commodity_no"], sort=False)

    out["last_observed_price"] = group["price_clean"].shift(1)
    out["days_since_last_observation"] = group["date"].diff().dt.days
    out["pred_last_observed"] = out["last_observed_price"]
    out["pred_seasonal_7"] = group["price_clean"].shift(7)
    out["pred_rolling_median_7"] = group["price_clean"].transform(
        lambda value: value.shift(1).rolling(7, min_periods=1).median()
    )

    return out


def _dense_month_grid(
    start_date: pd.Timestamp,
    end_date: pd.Timestamp,
) -> pd.DataFrame:
    dates = pd.date_range(start_date, end_date, freq="D")

    rows = []
    for date in dates:
        for market_id, market_name in TARGET_MARKETS.items():
            for commodity_no, commodity in TARGET_COMMODITIES.items():
                rows.append(
                    {
                        "date": date,
                        "market_id": market_id,
                        "market_name": market_name,
                        "commodity_no": commodity_no,
                        "commodity": commodity,
                    }
                )

    return pd.DataFrame(rows)


def _same_value(a: Any, b: Any) -> bool:
    if pd.isna(a) and pd.isna(b):
        return True
    if pd.isna(a) or pd.isna(b):
        return False
    return bool(np.isclose(float(a), float(b), rtol=0, atol=1e-9))


def refresh_prices(year_month: str | None = None) -> RefreshResult:
    """
    Refresh current month untuk 6 market.

    Important:
    - existing current-month rows BUKAN di-skip
    - incoming observation meng-override key yang sama
    - daily calendar grid tetap lengkap untuk semua 30 pair
    - file ditulis atomic via temporary parquet
    """
    target_month = year_month or current_year_month()
    month_start = pd.Timestamp(f"{target_month}-01")

    base = pd.read_parquet(DATA_PATH)
    base = base.copy()
    base["date"] = pd.to_datetime(base["date"]).dt.normalize()

    missing = set(DATA_COLUMNS) - set(base.columns)
    if missing:
        raise ValueError(
            "prices_split_base.parquet kehilangan kolom: "
            + ", ".join(sorted(missing))
        )

    base = base[DATA_COLUMNS].copy()

    # Model live memang hanya memakai selected market/commodity.
    base = base[
        base["market_id"].isin(TARGET_MARKETS)
        & base["commodity_no"].isin(TARGET_COMMODITIES)
    ].copy()

    base = base.sort_values(KEY_COLUMNS).reset_index(drop=True)
    _validate_model_base(base)

    latest_before = base["date"].max() if not base.empty else pd.NaT

    # -----------------------------
    # Download + parse
    # -----------------------------
    session = make_session()

    frames: list[pd.DataFrame] = []
    failed_market_ids: list[int] = []
    downloaded = 0

    for market_id in TARGET_MARKETS:
        try:
            content = download_market_report(
                session,
                market_id,
                target_month,
            )
            downloaded += 1

            parsed = parse_market_report(
                content,
                market_id,
                target_month,
            )

            if not parsed.empty:
                frames.append(parsed)

        except Exception as exc:
            failed_market_ids.append(market_id)
            print(
                f"[WARN] market_id={market_id} gagal refresh: "
                f"{type(exc).__name__}: {exc}"
            )

    if frames:
        incoming_raw = pd.concat(frames, ignore_index=True)
        incoming_raw = incoming_raw.sort_values(KEY_COLUMNS)
        incoming_raw = incoming_raw.drop_duplicates(
            KEY_COLUMNS,
            keep="last",
        )
    else:
        incoming_raw = pd.DataFrame(
            columns=MODEL_BASE_COLUMNS[:-1] + ["price_raw"]
        )

    if incoming_raw.empty:
        return RefreshResult(
            year_month=target_month,
            downloaded_markets=downloaded,
            failed_market_ids=tuple(failed_market_ids),
            parsed_observations=0,
            gross_outliers_removed=0,
            calendar_rows_inserted=0,
            observations_inserted=0,
            observations_updated=0,
            observations_unchanged=0,
            latest_date_before=(
                latest_before.strftime("%Y-%m-%d")
                if pd.notna(latest_before)
                else None
            ),
            latest_date_after=(
                latest_before.strftime("%Y-%m-%d")
                if pd.notna(latest_before)
                else None
            ),
            data_changed=False,
        )

    incoming, gross_removed = clean_incoming_prices(
        base,
        incoming_raw,
    )

    latest_incoming = incoming["date"].max()

    # Jangan pernah memendekkan existing month.
    base_same_month = base[
        base["date"].dt.strftime("%Y-%m") == target_month
    ]
    latest_existing_month = (
        base_same_month["date"].max()
        if not base_same_month.empty
        else pd.NaT
    )

    dense_end = latest_incoming
    if pd.notna(latest_existing_month):
        dense_end = max(dense_end, latest_existing_month)

    # -----------------------------
    # Rebuild current month only
    # -----------------------------
    before_month = base[base["date"] < month_start].copy()
    after_month = base[
        base["date"] > dense_end
    ].copy()

    old_month = base[
        base["date"].between(month_start, dense_end)
    ].copy()

    grid = _dense_month_grid(month_start, dense_end)

    old_values = old_month.rename(
        columns={
            column: f"{column}_old"
            for column in DATA_COLUMNS
            if column not in KEY_COLUMNS
        }
    )

    incoming_prices = incoming[
        KEY_COLUMNS + ["price_clean", "_gross_outlier"]
    ].copy()
    incoming_prices["_has_incoming"] = True
    incoming_prices = incoming_prices.rename(
        columns={
            "price_clean": "incoming_price",
            "_gross_outlier": "incoming_gross_outlier",
        }
    )

    month_new = (
        grid
        .merge(old_values, on=KEY_COLUMNS, how="left")
        .merge(incoming_prices, on=KEY_COLUMNS, how="left")
    )

    month_new["_has_incoming"] = (
        month_new["_has_incoming"].fillna(False)
    )

    # Incoming menang, termasuk jika hasil cleaning = NaN.
    month_new["price_clean"] = np.where(
        month_new["_has_incoming"],
        month_new["incoming_price"],
        month_new["price_clean_old"],
    )

    existing_mask = month_new["price_clean_old"].notna()
    incoming_clean_mask = (
        month_new["_has_incoming"] & month_new["incoming_price"].notna()
    )
    incoming_outlier_mask = (
        month_new["_has_incoming"]
        & month_new["incoming_gross_outlier"].fillna(False)
    )

    for column in FLAG_COLUMNS:
        month_new[column] = month_new[f"{column}_old"]

    month_new["is_observed_raw"] = np.where(
        month_new["_has_incoming"],
        1,
        month_new["is_observed_raw"].where(existing_mask, 0),
    )
    month_new["is_observed_clean"] = np.where(
        month_new["_has_incoming"],
        incoming_clean_mask.astype(int),
        month_new["is_observed_clean"].where(existing_mask, 0),
    )
    month_new["is_gross_outlier"] = np.where(
        month_new["_has_incoming"],
        incoming_outlier_mask.astype(int),
        month_new["is_gross_outlier"].where(existing_mask, 0),
    )
    month_new["is_cross_market_anomaly"] = month_new[
        "is_cross_market_anomaly"
    ].where(existing_mask, 0)
    month_new["is_temporal_anomaly"] = month_new[
        "is_temporal_anomaly"
    ].where(existing_mask, 0)
    month_new["split"] = month_new["split_old"].where(existing_mask, "refresh")

    month_new = month_new[
        MODEL_BASE_COLUMNS + FLAG_COLUMNS + ["split"]
    ].copy()

    # -----------------------------
    # Audit inserted / updated
    # -----------------------------
    old_lookup = {
        (r.date, int(r.market_id), int(r.commodity_no)): r.price_clean
        for r in old_month.itertuples(index=False)
    }

    old_keys = set(old_lookup)

    calendar_rows_inserted = 0
    obs_inserted = 0
    obs_updated = 0
    obs_unchanged = 0

    incoming_clean_lookup = {
        (r.date, int(r.market_id), int(r.commodity_no)): r.price_clean
        for r in incoming.itertuples(index=False)
    }

    for key, new_price in incoming_clean_lookup.items():
        if key not in old_keys:
            if pd.notna(new_price):
                obs_inserted += 1
        else:
            old_price = old_lookup[key]
            if _same_value(old_price, new_price):
                obs_unchanged += 1
            else:
                obs_updated += 1

    for row in month_new.itertuples(index=False):
        key = (row.date, int(row.market_id), int(row.commodity_no))
        if key not in old_keys:
            calendar_rows_inserted += 1

    updated = pd.concat(
        [before_month, month_new, after_month],
        ignore_index=True,
    )

    updated = (
        updated[MODEL_BASE_COLUMNS + FLAG_COLUMNS + ["split"]]
        .sort_values(KEY_COLUMNS)
        .reset_index(drop=True)
    )
    updated = _recompute_features(updated)
    updated = updated[DATA_COLUMNS].reset_index(drop=True)

    _validate_model_base(updated)

    latest_after = updated["date"].max()

    # -----------------------------
    # Atomic save
    # -----------------------------
    temp_path = DATA_PATH.with_name(
        DATA_PATH.stem + ".tmp.parquet"
    )

    updated.to_parquet(temp_path, index=False)

    # Read-back validation sebelum replace.
    check = pd.read_parquet(temp_path)
    check["date"] = pd.to_datetime(check["date"]).dt.normalize()
    _validate_model_base(check)

    temp_path.replace(DATA_PATH)

    changed = (
        calendar_rows_inserted > 0
        or obs_inserted > 0
        or obs_updated > 0
    )

    return RefreshResult(
        year_month=target_month,
        downloaded_markets=downloaded,
        failed_market_ids=tuple(failed_market_ids),
        parsed_observations=len(incoming_raw),
        gross_outliers_removed=gross_removed,
        calendar_rows_inserted=calendar_rows_inserted,
        observations_inserted=obs_inserted,
        observations_updated=obs_updated,
        observations_unchanged=obs_unchanged,
        latest_date_before=(
            latest_before.strftime("%Y-%m-%d")
            if pd.notna(latest_before)
            else None
        ),
        latest_date_after=(
            latest_after.strftime("%Y-%m-%d")
            if pd.notna(latest_after)
            else None
        ),
        data_changed=changed,
    )


if __name__ == "__main__":
    result = refresh_prices()
    print(asdict(result))
