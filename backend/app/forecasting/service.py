from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
from catboost import CatBoostRegressor
import lightgbm as lgb


# =========================================================
# Paths
# =========================================================

BASE_DIR = Path(__file__).resolve().parent
CONFIG_DIR = BASE_DIR / "config"
MODEL_DIR = BASE_DIR / "models"

FINAL_CONFIG_PATH = CONFIG_DIR / "final_model_config.json"
UNCERTAINTY_PATH = CONFIG_DIR / "commodity_horizon_uncertainty.csv"
DATA_DIR = BASE_DIR.parents[1] / "data"
DEFAULT_HISTORY_PATH = DATA_DIR / "prices_split_base.parquet"
DEFAULT_FORECAST_PATH = DATA_DIR / "forecast_next_7_days.parquet"

REQUIRED_HISTORY_COLUMNS = {
    "date",
    "market_id",
    "market_name",
    "commodity_no",
    "commodity",
    "price_clean",
}

CAT_COLS = ["market_cat", "commodity_cat"]

def build_inference_features(history: pd.DataFrame) -> pd.DataFrame:
    df = history.copy()

    missing = REQUIRED_HISTORY_COLUMNS - set(df.columns)
    if missing:
        raise ValueError(
            f"Missing history columns: {sorted(missing)}"
        )

    df["date"] = pd.to_datetime(df["date"])

    df = (
        df.sort_values(
            ["market_id", "commodity_no", "date"]
        )
        .reset_index(drop=True)
    )

    if df.duplicated(
        ["market_id", "commodity_no", "date"]
    ).any():
        raise ValueError(
            "Duplicate market × commodity × date ditemukan."
        )

    # Pastikan calendar grid per pair tetap daily.
    date_diff = (
        df.groupby(
            ["market_id", "commodity_no"],
            observed=True,
        )["date"]
        .diff()
        .dt.days
        .dropna()
    )

    if not date_diff.eq(1).all():
        raise ValueError(
            "Calendar grid tidak daily-continuous."
        )

    G = ["market_id", "commodity_no"]

    # -----------------------------------------------------
    # 1. Own-market history
    # -----------------------------------------------------

    # Harga terakhir yang benar-benar tersedia.
    df["anchor_price"] = (
        df.groupby(G, observed=True)["price_clean"]
        .transform(lambda s: s.ffill())
    )

    observed_date = df["date"].where(
        df["price_clean"].notna()
    )

    df["_anchor_date"] = (
        observed_date.groupby(
            [df["market_id"], df["commodity_no"]],
            observed=True,
        )
        .transform(lambda s: s.ffill())
    )

    df["days_since_anchor"] = (
        df["date"] - df["_anchor_date"]
    ).dt.days

    df.drop(columns="_anchor_date", inplace=True)

    # Raw observed-price lags.
    for lag in [1, 2, 3, 5, 7, 10, 14, 21, 30]:
        df[f"lag_{lag}"] = (
            df.groupby(G, observed=True)["price_clean"]
            .shift(lag)
        )

    # Forward-filled anchor lags.
    for lag in [1, 3, 7, 14, 30]:
        df[f"anchor_lag_{lag}"] = (
            df.groupby(G, observed=True)["anchor_price"]
            .shift(lag)
        )

    # Rolling stats.
    for w in [3, 7, 14, 30]:
        gp = df.groupby(
            G,
            observed=True,
        )["anchor_price"]

        df[f"roll_mean_{w}"] = gp.transform(
            lambda s: s.rolling(
                w,
                min_periods=min(3, w),
            ).mean()
        )

        df[f"roll_median_{w}"] = gp.transform(
            lambda s: s.rolling(
                w,
                min_periods=min(3, w),
            ).median()
        )

        df[f"roll_min_{w}"] = gp.transform(
            lambda s: s.rolling(
                w,
                min_periods=min(3, w),
            ).min()
        )

        df[f"roll_max_{w}"] = gp.transform(
            lambda s: s.rolling(
                w,
                min_periods=min(3, w),
            ).max()
        )

        df[f"roll_q25_{w}"] = gp.transform(
            lambda s: s.rolling(
                w,
                min_periods=min(3, w),
            ).quantile(0.25)
        )

        df[f"roll_q75_{w}"] = gp.transform(
            lambda s: s.rolling(
                w,
                min_periods=min(3, w),
            ).quantile(0.75)
        )

        df[f"roll_range_{w}"] = (
            df[f"roll_max_{w}"]
            - df[f"roll_min_{w}"]
        )

        df[f"roll_iqr_{w}"] = (
            df[f"roll_q75_{w}"]
            - df[f"roll_q25_{w}"]
        )

    for w in [7, 14, 30]:
        df[f"roll_std_{w}"] = (
            df.groupby(
                G,
                observed=True,
            )["anchor_price"]
            .transform(
                lambda s: s.rolling(
                    w,
                    min_periods=3,
                ).std()
            )
        )

        df[f"roll_cv_{w}"] = (
            df[f"roll_std_{w}"]
            / df[f"roll_mean_{w}"].replace(
                0,
                np.nan,
            )
        )

    # EWM.
    for span in [3, 7, 14, 30]:
        df[f"ewm_{span}"] = (
            df.groupby(
                G,
                observed=True,
            )["anchor_price"]
            .transform(
                lambda s: s.ewm(
                    span=span,
                    adjust=False,
                    min_periods=1,
                ).mean()
            )
        )

    # Movement / slope features.
    for lag in [1, 3, 7, 14, 30]:
        b = df[f"anchor_lag_{lag}"]

        df[f"change_{lag}d"] = (
            df["anchor_price"] - b
        )

        df[f"pct_change_{lag}d"] = (
            (df["anchor_price"] - b)
            / b.replace(0, np.nan)
        )

        df[f"slope_{lag}d"] = (
            (df["anchor_price"] - b) / lag
        )

    df["anchor_minus_ewm7"] = (
        df["anchor_price"] - df["ewm_7"]
    )

    df["anchor_minus_ewm30"] = (
        df["anchor_price"] - df["ewm_30"]
    )

    df["ewm7_minus_ewm30"] = (
        df["ewm_7"] - df["ewm_30"]
    )

    # -----------------------------------------------------
    # 2. Stickiness / movement regime
    # -----------------------------------------------------

    df["anchor_diff_1"] = (
        df.groupby(G, observed=True)["anchor_price"]
        .diff()
    )

    df["_up"] = (
        df["anchor_diff_1"] > 0
    ).astype(float)

    df["_down"] = (
        df["anchor_diff_1"] < 0
    ).astype(float)

    df["_abs"] = (
        df["anchor_diff_1"].abs()
    )

    for w in [7, 14]:
        df[f"share_up_{w}"] = (
            df.groupby(
                G,
                observed=True,
            )["_up"]
            .transform(
                lambda s: s.rolling(
                    w,
                    min_periods=3,
                ).mean()
            )
        )

        df[f"share_down_{w}"] = (
            df.groupby(
                G,
                observed=True,
            )["_down"]
            .transform(
                lambda s: s.rolling(
                    w,
                    min_periods=3,
                ).mean()
            )
        )

        df[f"median_abs_move_{w}"] = (
            df.groupby(
                G,
                observed=True,
            )["_abs"]
            .transform(
                lambda s: s.rolling(
                    w,
                    min_periods=3,
                ).median()
            )
        )

    def unchanged_streak(s: pd.Series) -> pd.Series:
        a = s.to_numpy()
        out = np.zeros(
            len(a),
            dtype=np.int16,
        )

        n = 0

        for i in range(len(a)):
            if (
                i == 0
                or pd.isna(a[i])
                or pd.isna(a[i - 1])
                or a[i] != a[i - 1]
            ):
                n = 0
            else:
                n += 1

            out[i] = n

        return pd.Series(
            out,
            index=s.index,
        )

    df["unchanged_streak"] = (
        df.groupby(
            G,
            observed=True,
        )["anchor_price"]
        .transform(unchanged_streak)
    )

    df.drop(
        columns=["_up", "_down", "_abs"],
        inplace=True,
    )

    # -----------------------------------------------------
    # 3. Cross-market features
    # -----------------------------------------------------

    cross = (
        df.groupby(
            ["date", "commodity_no"],
            observed=True,
        )
        .agg(
            cross_median=(
                "anchor_price",
                "median",
            ),
            cross_mean=(
                "anchor_price",
                "mean",
            ),
            cross_min=(
                "anchor_price",
                "min",
            ),
            cross_max=(
                "anchor_price",
                "max",
            ),
            cross_std=(
                "anchor_price",
                "std",
            ),
            cross_q25=(
                "anchor_price",
                lambda s: s.quantile(0.25),
            ),
            cross_q75=(
                "anchor_price",
                lambda s: s.quantile(0.75),
            ),
            cross_market_count=(
                "anchor_price",
                "count",
            ),
            cross_fresh_count=(
                "price_clean",
                "count",
            ),
        )
        .reset_index()
    )

    cross["cross_range"] = (
        cross["cross_max"]
        - cross["cross_min"]
    )

    cross["cross_iqr"] = (
        cross["cross_q75"]
        - cross["cross_q25"]
    )

    cross["cross_cv"] = (
        cross["cross_std"]
        / cross["cross_mean"].replace(
            0,
            np.nan,
        )
    )

    cross["cross_fresh_ratio"] = (
        cross["cross_fresh_count"]
        / cross["cross_market_count"].replace(
            0,
            np.nan,
        )
    )

    df = df.merge(
        cross,
        on=["date", "commodity_no"],
        how="left",
    )

    df["price_minus_cross_median"] = (
        df["anchor_price"]
        - df["cross_median"]
    )

    df["price_minus_cross_mean"] = (
        df["anchor_price"]
        - df["cross_mean"]
    )

    df["price_ratio_cross_median"] = (
        df["anchor_price"]
        / df["cross_median"].replace(
            0,
            np.nan,
        )
    )

    df["distance_from_cross_min"] = (
        df["anchor_price"]
        - df["cross_min"]
    )

    df["distance_from_cross_max"] = (
        df["cross_max"]
        - df["anchor_price"]
    )

    df["cross_zscore"] = (
        (df["anchor_price"] - df["cross_mean"])
        / df["cross_std"].replace(
            0,
            np.nan,
        )
    )

    df["price_rank_pct"] = (
        df.groupby(
            ["date", "commodity_no"],
            observed=True,
        )["anchor_price"]
        .rank(
            method="average",
            pct=True,
        )
    )

    cts = cross.sort_values(
        ["commodity_no", "date"]
    ).copy()

    for lag in [1, 3, 7, 14]:
        for col in [
            "cross_median",
            "cross_mean",
            "cross_std",
            "cross_range",
        ]:
            cts[f"{col}_lag{lag}"] = (
                cts.groupby(
                    "commodity_no",
                    observed=True,
                )[col]
                .shift(lag)
            )

        cts[f"cross_median_change_{lag}d"] = (
            cts["cross_median"]
            - cts[f"cross_median_lag{lag}"]
        )

    cts["cross_median_pct_change_7d"] = (
        cts["cross_median_change_7d"]
        / cts["cross_median_lag7"].replace(
            0,
            np.nan,
        )
    )

    trend_cols = (
        ["date", "commodity_no"]
        + [
            c
            for c in cts.columns
            if (
                "_lag" in c
                or "_change_" in c
                or c
                == "cross_median_pct_change_7d"
            )
        ]
    )

    trend_cols = list(
        dict.fromkeys(trend_cols)
    )

    df = df.merge(
        cts[trend_cols],
        on=["date", "commodity_no"],
        how="left",
    )

    df["member_prev"] = (
        df.groupby(
            G,
            observed=True,
        )["anchor_price"]
        .shift(1)
    )

    df["member_move"] = (
        df["anchor_price"]
        - df["member_prev"]
    )

    df["_cu"] = (
        df["member_move"] > 0
    ).astype(float)

    df["_cd"] = (
        df["member_move"] < 0
    ).astype(float)

    df["_cf"] = (
        df["member_move"] == 0
    ).astype(float)

    breadth = (
        df.groupby(
            ["date", "commodity_no"],
            observed=True,
        )
        .agg(
            cross_share_up=(
                "_cu",
                "mean",
            ),
            cross_share_down=(
                "_cd",
                "mean",
            ),
            cross_share_flat=(
                "_cf",
                "mean",
            ),
            cross_median_member_move=(
                "member_move",
                "median",
            ),
            cross_mean_member_move=(
                "member_move",
                "mean",
            ),
        )
        .reset_index()
    )

    df = df.merge(
        breadth,
        on=["date", "commodity_no"],
        how="left",
    )

    df.drop(
        columns=["_cu", "_cd", "_cf"],
        inplace=True,
    )

    # -----------------------------------------------------
    # 4. Calendar + categorical features
    # -----------------------------------------------------

    df["day_of_week"] = (
        df["date"].dt.dayofweek.astype("int8")
    )

    df["day_of_month"] = (
        df["date"].dt.day.astype("int8")
    )

    df["week_of_year"] = (
        df["date"]
        .dt.isocalendar()
        .week.astype("int16")
    )

    df["month"] = (
        df["date"].dt.month.astype("int8")
    )

    df["quarter"] = (
        df["date"].dt.quarter.astype("int8")
    )

    df["day_of_year"] = (
        df["date"].dt.dayofyear.astype("int16")
    )

    df["is_weekend"] = (
        df["day_of_week"]
        .isin([5, 6])
        .astype("int8")
    )

    df["dow_sin"] = np.sin(
        2
        * np.pi
        * df["day_of_week"]
        / 7
    )

    df["dow_cos"] = np.cos(
        2
        * np.pi
        * df["day_of_week"]
        / 7
    )

    df["month_sin"] = np.sin(
        2
        * np.pi
        * (df["month"] - 1)
        / 12
    )

    df["month_cos"] = np.cos(
        2
        * np.pi
        * (df["month"] - 1)
        / 12
    )

    df["market_cat"] = (
        df["market_id"].astype(str)
    )

    df["commodity_cat"] = (
        df["commodity_no"].astype(str)
    )

    return df


# =========================================================
# Inference service
# =========================================================

class ForecastInferenceService:
    def __init__(
        self,
        config_path: Path = FINAL_CONFIG_PATH,
        uncertainty_path: Path = UNCERTAINTY_PATH,
        model_dir: Path = MODEL_DIR,
    ):
        self.config_path = Path(config_path)
        self.uncertainty_path = Path(
            uncertainty_path
        )
        self.model_dir = Path(model_dir)

        self._load_config()
        self._load_uncertainty()
        self._load_models()

    def _load_config(self) -> None:
        with open(
            self.config_path,
            "r",
            encoding="utf-8",
        ) as f:
            config = json.load(f)

        # JSON mengubah integer dict keys menjadi string.
        self.final_policy = {
            int(h): cfg
            for h, cfg in config[
                "final_policy"
            ].items()
        }

        self.feature_sets = (
            config["feature_sets"]
        )

        self.max_allowed_anchor_age_days = int(
            config.get(
                "max_allowed_anchor_age_days",
                7,
            )
        )

        self.horizons = sorted(
            self.final_policy.keys()
        )

    def _load_uncertainty(self) -> None:
        uncertainty_df = pd.read_csv(
            self.uncertainty_path
        )

        required = {
            "horizon",
            "commodity",
            "uncertainty_half_width",
        }

        missing = (
            required
            - set(uncertainty_df.columns)
        )

        if missing:
            raise ValueError(
                "Uncertainty artifact missing "
                f"columns: {sorted(missing)}"
            )

        self.uncertainty_map = {
            (
                int(row.horizon),
                str(row.commodity),
            ): float(
                row.uncertainty_half_width
            )
            for row in uncertainty_df.itertuples()
        }

    def _load_models(self) -> None:
        self.models = {}

        for h in self.horizons:
            cfg = self.final_policy[h]

            if (
                cfg["model_used"]
                == "persistence_baseline"
            ):
                continue

            family = cfg["model_family"]

            if family == "catboost":
                path = (
                    self.model_dir
                    / f"h{h}_catboost_residual.cbm"
                )

                model = CatBoostRegressor()
                model.load_model(str(path))

            elif family == "lightgbm":
                path = (
                    self.model_dir
                    / f"h{h}_lightgbm_residual.txt"
                )

                model = lgb.Booster(
                    model_file=str(path)
                )

            else:
                raise ValueError(
                    f"Unsupported model family: "
                    f"{family}"
                )

            self.models[h] = model

    def _predict_residual(
        self,
        h: int,
        frame: pd.DataFrame,
    ) -> np.ndarray:
        cfg = self.final_policy[h]
        family = cfg["model_family"]

        feature_cols = self.feature_sets[
            cfg["feature_set"]
        ]

        missing_features = [
            c
            for c in feature_cols
            if c not in frame.columns
        ]

        if missing_features:
            raise ValueError(
                f"H+{h} missing features: "
                f"{missing_features[:20]}"
            )

        if family == "catboost":
            X = frame[
                feature_cols
            ].copy()

            for c in CAT_COLS:
                if c in X.columns:
                    X[c] = X[c].astype(str)

            pred = self.models[h].predict(X)

        elif family == "lightgbm":
            numeric_cols = [
                c
                for c in feature_cols
                if c not in CAT_COLS
            ]

            X = frame[
                numeric_cols
            ].copy()

            pred = self.models[h].predict(X)

        else:
            raise ValueError(
                f"Unsupported model family: "
                f"{family}"
            )

        return np.asarray(
            pred,
            dtype=float,
        )

    def forecast(
        self,
        history: pd.DataFrame,
        origin_date: Optional[str | pd.Timestamp] = None,
    ) -> pd.DataFrame:

        raw = history.copy()
        raw["date"] = pd.to_datetime(
            raw["date"]
        )

        if origin_date is None:
            resolved_origin = raw["date"].max()
        else:
            resolved_origin = pd.Timestamp(
                origin_date
            )

        # Safety: jangan biarkan future rows ikut
        # membentuk feature untuk origin tertentu.
        raw = raw[
            raw["date"] <= resolved_origin
        ].copy()

        df = build_inference_features(raw)

        origin_rows = df[
            df["date"] == resolved_origin
        ].copy()

        expected_pairs = (
            df[
                ["market_id", "commodity_no"]
            ]
            .drop_duplicates()
            .shape[0]
        )

        if len(origin_rows) != expected_pairs:
            raise ValueError(
                f"Origin {resolved_origin.date()} "
                "tidak punya calendar row "
                "untuk semua pair: "
                f"{len(origin_rows)} "
                f"vs {expected_pairs}"
            )

        if (
            origin_rows[
                "anchor_price"
            ]
            .isna()
            .any()
        ):
            raise ValueError(
                "Ada pair tanpa historical "
                "anchor price."
            )

        max_anchor_age = int(
            origin_rows[
                "days_since_anchor"
            ].max()
        )

        if (
            max_anchor_age
            > self.max_allowed_anchor_age_days
        ):
            raise ValueError(
                "Forecast dibatalkan: "
                f"anchor paling stale = "
                f"{max_anchor_age} hari, "
                "melebihi limit "
                f"{self.max_allowed_anchor_age_days}."
            )

        forecast_rows = []

        for h in self.horizons:
            cfg = self.final_policy[h]

            part = (
                origin_rows
                .copy()
                .reset_index(drop=True)
            )

            # H+1 di final policy notebook:
            # persistence baseline.
            if (
                cfg["model_used"]
                == "persistence_baseline"
            ):
                point = (
                    part["anchor_price"]
                    .to_numpy(dtype=float)
                )

            else:
                residual = (
                    self._predict_residual(
                        h=h,
                        frame=part,
                    )
                )

                point = (
                    part["anchor_price"]
                    .to_numpy(dtype=float)
                    + residual
                )

            point = np.maximum(
                point,
                1.0,
            )

            for i, row in part.iterrows():
                commodity = str(
                    row["commodity"]
                )

                key = (
                    h,
                    commodity,
                )

                if key not in self.uncertainty_map:
                    raise KeyError(
                        "Uncertainty width "
                        "tidak ditemukan untuk "
                        f"H+{h}, {commodity}"
                    )

                q = self.uncertainty_map[key]

                expected_price = float(
                    point[i]
                )

                lower = max(
                    expected_price - q,
                    1.0,
                )

                upper = (
                    expected_price + q
                )

                forecast_rows.append({
                    "origin_date":
                        resolved_origin,
                    "target_date":
                        resolved_origin
                        + pd.Timedelta(
                            days=h
                        ),
                    "horizon":
                        h,
                    "market_id":
                        int(row["market_id"]),
                    "market_name":
                        row["market_name"],
                    "commodity_no":
                        int(
                            row[
                                "commodity_no"
                            ]
                        ),
                    "commodity":
                        commodity,
                    "expected_price":
                        expected_price,
                    "lower_bound":
                        lower,
                    "upper_bound":
                        upper,
                    "uncertainty_half_width":
                        q,
                    "uncertainty_ratio":
                        (
                            q / expected_price
                            if expected_price > 0
                            else np.nan
                        ),
                })

        forecast = (
            pd.DataFrame(forecast_rows)
            .sort_values(
                [
                    "target_date",
                    "market_id",
                    "commodity_no",
                ]
            )
            .reset_index(drop=True)
        )

        expected_rows = (
            expected_pairs
            * len(self.horizons)
        )

        if len(forecast) != expected_rows:
            raise RuntimeError(
                f"Forecast rows "
                f"{len(forecast)} "
                f"!= expected "
                f"{expected_rows}"
            )

        return forecast[
            [
                "origin_date",
                "target_date",
                "horizon",
                "market_id",
                "market_name",
                "commodity_no",
                "commodity",
                "expected_price",
                "lower_bound",
                "upper_bound",
                "uncertainty_half_width",
                "uncertainty_ratio",
            ]
        ]

_service: ForecastInferenceService | None = None

def get_forecast_service() -> ForecastInferenceService:
    global _service

    if _service is None:
        _service = ForecastInferenceService()

    return _service


def forecast_from_parquet(
    history_path: str | Path,
    origin_date: Optional[str] = None,
) -> pd.DataFrame:
    history = pd.read_parquet(
        history_path
    )

    service = get_forecast_service()

    return service.forecast(
        history=history,
        origin_date=origin_date,
    )


def write_forecast_next_7_days(
    history_path: str | Path = DEFAULT_HISTORY_PATH,
    forecast_path: str | Path = DEFAULT_FORECAST_PATH,
    origin_date: Optional[str] = None,
) -> pd.DataFrame:
    forecast = forecast_from_parquet(
        history_path=history_path,
        origin_date=origin_date,
    )

    target_path = Path(forecast_path)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = target_path.with_name(
        target_path.stem + ".tmp.parquet"
    )

    forecast.to_parquet(temp_path, index=False)

    check = pd.read_parquet(temp_path)
    expected_columns = list(forecast.columns)

    if list(check.columns) != expected_columns:
        raise RuntimeError(
            "Forecast write validation failed: schema berubah."
        )

    if len(check) != len(forecast):
        raise RuntimeError(
            "Forecast write validation failed: row count berubah."
        )

    temp_path.replace(target_path)
    return forecast


if __name__ == "__main__":
    # Contoh local test:
    #
    # python service.py
    #
    # Ganti path sesuai canonical history kalian.
    result = write_forecast_next_7_days()

    print(result.head(20))
    print()
    print(
        "Forecast:",
        result["target_date"].min().date(),
        "->",
        result["target_date"].max().date(),
    )
