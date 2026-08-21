from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional, Literal

import pandas as pd
import pulp


# ---------------------------------------------------------------------------
# 1. MARKET METADATA
#    Koordinat approx; idealnya dioverride dengan data resmi/lebih akurat.
# ---------------------------------------------------------------------------
MARKET_COORDS = {
    8:  (-6.1467, 106.8156),   # Pasar Glodok
    12: (-6.2635, 106.8646),   # Pasar Kramat Jati
    14: (-6.2183, 106.9096),   # Pasar Perumnas Klender
    28: (-6.2440, 106.7825),   # Pasar Kebayoran Lama
    38: (-6.1500, 106.7025),   # Pasar Kalideres
    41: (-6.1435, 106.8073),   # Pasar Jembatan Lima
}


def haversine_km(lat1, lon1, lat2, lon2) -> float:
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)

    a = (
        math.sin(dphi / 2) ** 2
        + math.cos(p1)
        * math.cos(p2)
        * math.sin(dlambda / 2) ** 2
    )
    return 2 * R * math.asin(math.sqrt(a))


@dataclass
class RoutingParams:
    avg_speed_kmh: float = 22.0
    cost_per_km: float = 3000.0
    fixed_trip_cost: float = 15000.0
    round_trip: bool = True


def build_routing_table(
    user_lat: float,
    user_lon: float,
    market_ids: list[int],
    market_coords: dict[int, tuple[float, float]] = MARKET_COORDS,
    params: RoutingParams = RoutingParams(),
) -> pd.DataFrame:
    """Estimasi distance/time/cost dari user ke tiap pasar."""
    if params.avg_speed_kmh <= 0:
        raise ValueError("avg_speed_kmh harus > 0.")
    if params.cost_per_km < 0 or params.fixed_trip_cost < 0:
        raise ValueError("Biaya routing tidak boleh negatif.")

    rows = []

    for mid in market_ids:
        if mid not in market_coords:
            raise ValueError(
                f"Koordinat market_id={mid} tidak ditemukan. "
                "Supply via market_coords override."
            )

        mlat, mlon = market_coords[mid]

        dist_one_way = haversine_km(
            user_lat,
            user_lon,
            mlat,
            mlon,
        )

        dist = dist_one_way * (2 if params.round_trip else 1)
        travel_time_hr = dist / params.avg_speed_kmh
        transport_cost = (
            dist * params.cost_per_km
            + params.fixed_trip_cost
        )

        rows.append(
            {
                "market_id": mid,
                "distance_km": round(dist, 2),
                "travel_time_min": round(travel_time_hr * 60, 1),
                "transport_cost": round(transport_cost, 0),
            }
        )

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# 2. USER REQUEST
# ---------------------------------------------------------------------------
@dataclass
class UserRequest:
    location: tuple[float, float]
    commodities: dict[int, float]  # {commodity_no: qty_kg}
    deadline: str

    max_markets: Optional[int] = 2
    max_trips: Optional[int] = 2

    # Dipakai khusus strategy balanced.
    risk_aversion: float = 0.5

    # False = satu commodity dipilih di satu market-date saja.
    # True = boleh split proporsi lintas market/date.
    allow_split: bool = False

    market_coords: dict = field(
        default_factory=lambda: MARKET_COORDS
    )
    routing_params: RoutingParams = field(
        default_factory=RoutingParams
    )


PricingMode = Literal["expected", "balanced", "upper_bound"]


# ---------------------------------------------------------------------------
# 3. PREP / VALIDATION
# ---------------------------------------------------------------------------
REQUIRED_FORECAST_COLS = {
    "target_date",
    "market_id",
    "market_name",
    "commodity_no",
    "commodity",
    "expected_price",
    "lower_bound",
    "upper_bound",
    "uncertainty_half_width",
    "uncertainty_ratio",
}


def _prepare_forecast(
    forecast: pd.DataFrame,
    req: UserRequest,
) -> pd.DataFrame:
    missing_cols = REQUIRED_FORECAST_COLS - set(forecast.columns)

    if missing_cols:
        raise ValueError(
            "Forecast kehilangan kolom wajib: "
            + ", ".join(sorted(missing_cols))
        )

    if not req.commodities:
        raise ValueError("commodities tidak boleh kosong.")

    bad_qty = {
        c: q
        for c, q in req.commodities.items()
        if q is None or q <= 0
    }
    if bad_qty:
        raise ValueError(
            f"Semua quantity harus > 0. Invalid: {bad_qty}"
        )

    if req.risk_aversion < 0:
        raise ValueError("risk_aversion harus >= 0.")

    if req.max_markets is not None and req.max_markets < 1:
        raise ValueError("max_markets harus >= 1 atau None.")

    if req.max_trips is not None and req.max_trips < 1:
        raise ValueError("max_trips harus >= 1 atau None.")

    df = forecast.copy()

    # FIX #5 — pakai hanya forecast run terbaru.
    if "origin_date" in df.columns:
        df["origin_date"] = pd.to_datetime(
            df["origin_date"],
            errors="coerce",
        )
        latest_origin = df["origin_date"].max()

        if pd.isna(latest_origin):
            raise ValueError(
                "origin_date ada tetapi tidak bisa diparse."
            )

        df = df[df["origin_date"] == latest_origin].copy()

    df["target_date"] = pd.to_datetime(
        df["target_date"],
        errors="coerce",
    )

    if df["target_date"].isna().any():
        raise ValueError(
            "Ada target_date yang tidak valid."
        )

    deadline = pd.to_datetime(
        req.deadline,
        errors="raise",
    )

    # Horizon valid.
    df = df[df["target_date"] <= deadline].copy()

    if df.empty:
        raise ValueError(
            "Tidak ada forecast yang jatuh sebelum / pada deadline."
        )

    requested_commodities = set(req.commodities.keys())
    available_commodities = set(df["commodity_no"].unique())

    missing_commodities = (
        requested_commodities - available_commodities
    )

    if missing_commodities:
        raise ValueError(
            "Komoditas berikut tidak tersedia di forecast "
            f"sampai deadline: {sorted(missing_commodities)}"
        )

    # Hanya komoditas yang diminta.
    df = df[
        df["commodity_no"].isin(requested_commodities)
    ].copy()

    # Harga forecast harus valid.
    price_cols = [
        "expected_price",
        "lower_bound",
        "upper_bound",
        "uncertainty_half_width",
    ]

    for col in price_cols:
        if df[col].isna().any():
            raise ValueError(
                f"Ada nilai NaN pada forecast column '{col}'."
            )

    if (df["expected_price"] <= 0).any():
        raise ValueError(
            "expected_price harus > 0."
        )

    if (df["uncertainty_half_width"] < 0).any():
        raise ValueError(
            "uncertainty_half_width tidak boleh negatif."
        )

    # FIX #4 — jangan izinkan duplicate lookup key.
    lookup_key = [
        "commodity_no",
        "market_id",
        "target_date",
    ]

    duplicates = df.duplicated(
        lookup_key,
        keep=False,
    )

    if duplicates.any():
        example = (
            df.loc[duplicates, lookup_key]
            .head(10)
            .to_dict("records")
        )
        raise ValueError(
            "Forecast memiliki duplicate "
            "commodity_no × market_id × target_date. "
            f"Contoh: {example}"
        )

    return df


def _add_optimization_unit_cost(
    df: pd.DataFrame,
    mode: PricingMode,
    risk_aversion: float,
) -> pd.DataFrame:
    df = df.copy()

    if mode == "expected":
        # Cheapest: percaya point forecast.
        df["optimization_price"] = df["expected_price"]

    elif mode == "balanced":
        # Balanced: expected + lambda * uncertainty.
        df["optimization_price"] = (
            df["expected_price"]
            + risk_aversion
            * df["uncertainty_half_width"]
        )

    elif mode == "upper_bound":
        # FIX #3 — low-risk langsung pakai upper bound.
        df["optimization_price"] = df["upper_bound"]

    else:
        raise ValueError(f"Unknown pricing mode: {mode}")

    return df


# ---------------------------------------------------------------------------
# 4. CORE MILP
# ---------------------------------------------------------------------------
def _solve(
    forecast: pd.DataFrame,
    req: UserRequest,
    routing: pd.DataFrame,
    pricing_mode: PricingMode,
    max_markets: Optional[int],
    max_trips: Optional[int],
    force_one_trip: bool = False,
) -> Optional[dict]:

    df = _add_optimization_unit_cost(
        forecast,
        mode=pricing_mode,
        risk_aversion=req.risk_aversion,
    )

    markets = sorted(df["market_id"].unique())
    dates = sorted(df["target_date"].unique())
    commodities = list(req.commodities.keys())

    route_map = (
        routing.set_index("market_id")
        .to_dict(orient="index")
    )

    prob = pulp.LpProblem(
        "purchase_plan",
        pulp.LpMinimize,
    )

    # visit[m,d] = 1 jika ada trip ke pasar m pada tanggal d.
    visit = {
        (m, d): pulp.LpVariable(
            f"visit_{m}_{pd.Timestamp(d).strftime('%Y%m%d')}",
            cat="Binary",
        )
        for m in markets
        for d in dates
    }

    # Allocation.
    frac = {}

    for c in commodities:
        sub = df[df["commodity_no"] == c]

        for _, row in sub.iterrows():
            m = int(row["market_id"])
            d = row["target_date"]

            key = (c, m, d)

            if req.allow_split:
                frac[key] = pulp.LpVariable(
                    f"frac_{c}_{m}_{pd.Timestamp(d).strftime('%Y%m%d')}",
                    lowBound=0,
                    upBound=1,
                )
            else:
                frac[key] = pulp.LpVariable(
                    f"choose_{c}_{m}_{pd.Timestamp(d).strftime('%Y%m%d')}",
                    cat="Binary",
                )

    price_lookup = df.set_index(
        ["commodity_no", "market_id", "target_date"]
    )

    # Setiap commodity harus terpenuhi 100%.
    for c in commodities:
        keys = [k for k in frac if k[0] == c]

        if not keys:
            return None

        prob += (
            pulp.lpSum(frac[k] for k in keys) == 1,
            f"fulfil_{c}",
        )

    # Allocation hanya bisa di market-date yang dikunjungi.
    for (c, m, d), var in frac.items():
        prob += (
            var <= visit[(m, d)],
            f"link_{c}_{m}_{pd.Timestamp(d).strftime('%Y%m%d')}",
        )

    # market_used[m] = 1 jika market m pernah dikunjungi.
    market_used = {
        m: pulp.LpVariable(
            f"used_{m}",
            cat="Binary",
        )
        for m in markets
    }

    for m in markets:
        visits_m = pulp.lpSum(
            visit[(m, d)]
            for d in dates
        )

        prob += (
            market_used[m] <= visits_m,
            f"used_lb_{m}",
        )

        prob += (
            visits_m
            <= len(dates) * market_used[m],
            f"used_ub_{m}",
        )

    # Max pasar berbeda.
    if max_markets is not None:
        prob += (
            pulp.lpSum(
                market_used[m]
                for m in markets
            )
            <= max_markets,
            "max_markets",
        )

    total_visits = pulp.lpSum(
        visit.values()
    )

    # FIX #2 — max_trips terpisah.
    if max_trips is not None:
        prob += (
            total_visits <= max_trips,
            "max_trips",
        )

    # FIX #2 — alternative one-stop benar-benar satu trip.
    if force_one_trip:
        prob += (
            total_visits == 1,
            "force_exactly_one_trip",
        )

    # Objective purchase cost.
    purchase_terms = []

    for (c, m, d), var in frac.items():
        qty = req.commodities[c]

        unit_cost = price_lookup.loc[
            (c, m, d),
            "optimization_price",
        ]

        purchase_terms.append(
            unit_cost * qty * var
        )

    # Transport dikenakan sekali per visit market-date.
    transport_terms = [
        visit[(m, d)]
        * route_map[m]["transport_cost"]
        for m in markets
        for d in dates
    ]

    prob += (
        pulp.lpSum(purchase_terms)
        + pulp.lpSum(transport_terms)
    )

    solver = pulp.PULP_CBC_CMD(msg=False)
    status = prob.solve(solver)

    if pulp.LpStatus[status] != "Optimal":
        return None

    # -----------------------------------------------------------------------
    # Build result
    # -----------------------------------------------------------------------
    lines = []
    purchase_cost = 0.0
    optimization_purchase_cost = 0.0

    weighted_abs_uncertainty = 0.0
    weighted_uncertainty_ratio = 0.0

    visited = set()

    for (c, m, d), var in frac.items():
        v = var.value()

        if not v or v <= 1e-6:
            continue

        row = price_lookup.loc[(c, m, d)]

        qty = req.commodities[c] * v
        exp_price = float(row["expected_price"])
        low = float(row["lower_bound"])
        high = float(row["upper_bound"])
        unc = float(row["uncertainty_half_width"])

        unc_ratio = row.get(
            "uncertainty_ratio",
            None,
        )

        opt_price = float(
            row["optimization_price"]
        )

        cost = exp_price * qty

        purchase_cost += cost
        optimization_purchase_cost += (
            opt_price * qty
        )

        weighted_abs_uncertainty += (
            unc * qty
        )

        if pd.notna(unc_ratio):
            weighted_uncertainty_ratio += (
                float(unc_ratio) * qty
            )

        visited.add((m, d))

        commodity_name = (
            df.loc[
                df["commodity_no"] == c,
                "commodity",
            ]
            .iloc[0]
        )

        market_name = (
            df.loc[
                df["market_id"] == m,
                "market_name",
            ]
            .iloc[0]
        )

        lines.append(
            {
                "commodity": commodity_name,
                "commodity_no": c,
                "market_id": m,
                "market_name": market_name,
                "target_date": pd.Timestamp(d).strftime(
                    "%Y-%m-%d"
                ),
                "qty_kg": round(qty, 2),
                "expected_price_per_kg": round(
                    exp_price,
                    0,
                ),
                "lower_bound_per_kg": round(
                    low,
                    0,
                ),
                "upper_bound_per_kg": round(
                    high,
                    0,
                ),
                "line_purchase_cost": round(
                    cost,
                    0,
                ),
            }
        )

    transport_cost = sum(
        route_map[m]["transport_cost"]
        for m, d in visited
    )

    total_expected_cost = (
        purchase_cost + transport_cost
    )

    optimization_objective_cost = (
        optimization_purchase_cost
        + transport_cost
    )

    total_qty = sum(req.commodities.values())

    avg_uncertainty_per_kg = (
        weighted_abs_uncertainty / total_qty
        if total_qty
        else 0
    )

    avg_uncertainty_ratio = (
        weighted_uncertainty_ratio / total_qty
        if total_qty
        else 0
    )

    # Worst-case-ish total menggunakan upper bound
    # pada allocation yang dipilih.
    worst_case_purchase = 0.0

    for line in lines:
        worst_case_purchase += (
            line["upper_bound_per_kg"]
            * line["qty_kg"]
        )

    worst_case_total = (
        worst_case_purchase
        + transport_cost
    )

    plan = {
        "strategy": pricing_mode,
        "lines": sorted(
            lines,
            key=lambda x: (
                x["target_date"],
                x["market_name"],
                x["commodity"],
            ),
        ),
        "markets_visited": sorted(
            {m for m, _ in visited}
        ),
        "visit_dates": sorted(
            {
                pd.Timestamp(d).strftime("%Y-%m-%d")
                for _, d in visited
            }
        ),
        "n_markets": len(
            {m for m, _ in visited}
        ),
        "n_trips": len(visited),
        "purchase_cost": round(
            purchase_cost,
            0,
        ),
        "transport_cost": round(
            transport_cost,
            0,
        ),
        "total_expected_cost": round(
            total_expected_cost,
            0,
        ),
        "optimization_objective_cost": round(
            optimization_objective_cost,
            0,
        ),
        "worst_case_total_cost": round(
            worst_case_total,
            0,
        ),
        "avg_uncertainty_per_kg": round(
            avg_uncertainty_per_kg,
            0,
        ),
        "avg_uncertainty_ratio": round(
            avg_uncertainty_ratio,
            4,
        ),
    }

    return plan


# ---------------------------------------------------------------------------
# 5. FAIR BASELINE
# ---------------------------------------------------------------------------
def _baseline_cost(
    forecast: pd.DataFrame,
    req: UserRequest,
    routing: pd.DataFrame,
) -> Optional[dict]:
    """
    FIX #1

    Baseline:
    - cari tanggal paling awal
    - pada tanggal itu, cari pasar yang punya SEMUA commodity user
    - dari pasar feasible itu, pilih yang PALING DEKAT
    - beli semua di sana
    - masukkan transport cost

    Ini lebih fair daripada membandingkan dengan pasar termahal.
    """

    required = set(req.commodities.keys())

    route_map = (
        routing.set_index("market_id")
        .to_dict(orient="index")
    )

    for date_value in sorted(
        forecast["target_date"].unique()
    ):
        day = forecast[
            forecast["target_date"] == date_value
        ]

        feasible_markets = []

        for mid, market_df in day.groupby(
            "market_id"
        ):
            available = set(
                market_df["commodity_no"].unique()
            )

            if required.issubset(available):
                feasible_markets.append(int(mid))

        if not feasible_markets:
            continue

        nearest_market = min(
            feasible_markets,
            key=lambda m: route_map[m]["distance_km"],
        )

        chosen = day[
            day["market_id"] == nearest_market
        ].set_index("commodity_no")

        purchase_cost = 0.0

        for c, qty in req.commodities.items():
            unit_price = float(
                chosen.loc[c, "expected_price"]
            )
            purchase_cost += unit_price * qty

        transport_cost = float(
            route_map[nearest_market][
                "transport_cost"
            ]
        )

        total_cost = (
            purchase_cost + transport_cost
        )

        market_name = (
            day.loc[
                day["market_id"] == nearest_market,
                "market_name",
            ]
            .iloc[0]
        )

        return {
            "date": pd.Timestamp(
                date_value
            ).strftime("%Y-%m-%d"),
            "market_id": nearest_market,
            "market_name": market_name,
            "purchase_cost": round(
                purchase_cost,
                0,
            ),
            "transport_cost": round(
                transport_cost,
                0,
            ),
            "total_cost": round(
                total_cost,
                0,
            ),
        }

    return None


# ---------------------------------------------------------------------------
# 6. PUBLIC ENTRY POINT
# ---------------------------------------------------------------------------
def optimize(
    forecast: pd.DataFrame,
    req: UserRequest,
) -> dict:

    prepared = _prepare_forecast(
        forecast,
        req,
    )

    relevant_markets = sorted(
        prepared["market_id"].unique()
    )

    routing = build_routing_table(
        req.location[0],
        req.location[1],
        relevant_markets,
        market_coords=req.market_coords,
        params=req.routing_params,
    )

    # Main plan = Balanced.
    main_plan = _solve(
        prepared,
        req,
        routing,
        pricing_mode="balanced",
        max_markets=req.max_markets,
        max_trips=req.max_trips,
    )

    if main_plan is None:
        raise RuntimeError(
            "Tidak ditemukan solusi feasible untuk "
            "kombinasi komoditas / deadline / "
            "max_markets / max_trips."
        )

    # Alternative 1: Cheapest.
    alt_cheapest = _solve(
        prepared,
        req,
        routing,
        pricing_mode="expected",
        max_markets=req.max_markets,
        max_trips=req.max_trips,
    )

    # Alternative 2: Low Risk.
    alt_low_risk = _solve(
        prepared,
        req,
        routing,
        pricing_mode="upper_bound",
        max_markets=req.max_markets,
        max_trips=req.max_trips,
    )

    # Alternative 3: One-stop / exactly 1 trip.
    alt_one_stop = _solve(
        prepared,
        req,
        routing,
        pricing_mode="balanced",
        max_markets=1,
        max_trips=1,
        force_one_trip=True,
    )

    baseline = _baseline_cost(
        prepared,
        req,
        routing,
    )

    if baseline is not None:
        saving = (
            baseline["total_cost"]
            - main_plan["total_expected_cost"]
        )

        main_plan[
            "estimated_saving_vs_baseline"
        ] = round(saving, 0)

        main_plan[
            "estimated_saving_pct"
        ] = (
            round(
                100
                * saving
                / baseline["total_cost"],
                1,
            )
            if baseline["total_cost"]
            else None
        )
    else:
        main_plan[
            "estimated_saving_vs_baseline"
        ] = None

        main_plan[
            "estimated_saving_pct"
        ] = None

    alternatives = {}

    for name, plan in [
        ("cheapest", alt_cheapest),
        ("low_risk", alt_low_risk),
        ("one_stop_one_trip", alt_one_stop),
    ]:
        if (
            plan is not None
            and plan["lines"] != main_plan["lines"]
        ):
            alternatives[name] = plan

    main_plan["alternative_plans"] = alternatives
    main_plan["baseline"] = baseline
    main_plan["deadline"] = pd.to_datetime(
        req.deadline
    ).strftime("%Y-%m-%d")
    main_plan["user_location"] = req.location

    # Useful debugging / frontend metadata.
    if "origin_date" in prepared.columns:
        main_plan["forecast_origin_date"] = (
            prepared["origin_date"]
            .max()
            .strftime("%Y-%m-%d")
        )

    return main_plan


# ---------------------------------------------------------------------------
# 7. PRINT HELPER
# ---------------------------------------------------------------------------
def print_plan(
    plan: dict,
    title: str = "RECOMMENDED PLAN",
):
    print(
        f"\n{'=' * 72}\n"
        f"{title}\n"
        f"{'=' * 72}"
    )

    for line in plan["lines"]:
        print(
            f"[{line['target_date']}] "
            f"{line['commodity']:<22s} "
            f"{line['qty_kg']:>7.1f} kg "
            f"@ Rp{line['expected_price_per_kg']:>9,.0f}/kg "
            f"-> {line['market_name']}"
        )

    print()
    print(
        f"Markets          : {plan['n_markets']}"
    )
    print(
        f"Trips            : {plan['n_trips']}"
    )
    print(
        f"Purchase cost    : Rp{plan['purchase_cost']:,.0f}"
    )
    print(
        f"Transport cost   : Rp{plan['transport_cost']:,.0f}"
    )
    print(
        f"Expected total   : Rp{plan['total_expected_cost']:,.0f}"
    )
    print(
        f"Worst-case total : Rp{plan['worst_case_total_cost']:,.0f}"
    )
    print(
        f"Avg uncertainty  : ±Rp{plan['avg_uncertainty_per_kg']:,.0f}/kg"
    )

    if plan.get("estimated_saving_vs_baseline") is not None:
        print(
            f"Saving vs baseline: "
            f"Rp{plan['estimated_saving_vs_baseline']:,.0f} "
            f"({plan['estimated_saving_pct']}%)"
        )

    if plan.get("baseline"):
        b = plan["baseline"]
        print(
            "Baseline          : "
            f"{b['market_name']} on {b['date']} "
            f"(Rp{b['total_cost']:,.0f})"
        )
