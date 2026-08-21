from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator

FORECAST_PATH = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "forecast_next_7_days.parquet"
)

router = APIRouter(prefix="/api/v1", tags=["optimize"])


class OptimizeRequest(BaseModel):
    location: tuple[float, float] = Field(
        ...,
        description="User/warehouse/kitchen location as (lat, lon).",
    )
    commodities: dict[int, float] = Field(
        ...,
        description="Mapping commodity_no to qty_needed in kg.",
    )
    deadline: date
    max_markets: int | None = Field(default=2, ge=1)
    risk_aversion: float = Field(default=0.5, ge=0)
    allow_split: bool = False
    max_trips: int | None = Field(default=2, ge=1)

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "location": [-6.2, 106.8],
                "commodities": {
                    "1": 10,
                    "2": 5,
                },
                "deadline": "2026-08-28",
                "max_markets": 2,
                "risk_aversion": 0.5,
                "allow_split": False,
                "max_trips": 2,
            }
        }
    )

    @field_validator("location")
    @classmethod
    def validate_location(
        cls,
        value: tuple[float, float],
    ) -> tuple[float, float]:
        lat, lon = value

        if not -90 <= lat <= 90:
            raise ValueError("location latitude harus di antara -90 dan 90.")

        if not -180 <= lon <= 180:
            raise ValueError("location longitude harus di antara -180 dan 180.")

        return value

    @field_validator("commodities")
    @classmethod
    def validate_commodities(
        cls,
        value: dict[int, float],
    ) -> dict[int, float]:
        if not value:
            raise ValueError("commodities tidak boleh kosong.")

        invalid = {
            commodity_no: qty
            for commodity_no, qty in value.items()
            if commodity_no <= 0 or qty <= 0
        }

        if invalid:
            raise ValueError(
                "commodity_no dan qty harus > 0. "
                f"Invalid: {invalid}"
            )

        return value


@lru_cache(maxsize=1)
def _load_forecast() -> Any:
    import pandas as pd

    return pd.read_parquet(FORECAST_PATH)


@router.post("/optimize")
def optimize_endpoint(payload: OptimizeRequest) -> dict[str, Any]:
    try:
        from app.optimizer.service import UserRequest, optimize

        user_request = UserRequest(
            location=payload.location,
            commodities=payload.commodities,
            deadline=payload.deadline.isoformat(),
            max_markets=payload.max_markets,
            max_trips=payload.max_trips,
            risk_aversion=payload.risk_aversion,
            allow_split=payload.allow_split,
        )

        return optimize(
            _load_forecast(),
            user_request,
        )
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Forecast file tidak ditemukan: {FORECAST_PATH}",
        ) from exc
    except ImportError as exc:
        raise HTTPException(
            status_code=500,
            detail=(
                "Dependency optimizer belum terinstall. "
                "Jalankan pip install -r requirements.txt."
            ),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc
