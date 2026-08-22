from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.forecasting.service import write_forecast_next_7_days
from app.api.optimize import _load_forecast
from app.refresh.service import refresh_prices

router = APIRouter(prefix="/api/v1", tags=["refresh"])


class RefreshRequest(BaseModel):
    year_month: str | None = Field(
        default=None,
        pattern=r"^\d{4}-\d{2}$",
        description="Optional override. Defaults to current month in Asia/Bangkok.",
    )


@router.post("/refresh")
def refresh_endpoint(payload: RefreshRequest | None = None) -> dict[str, Any]:
    try:
        result = refresh_prices(
            year_month=payload.year_month if payload else None,
        )
        forecast = write_forecast_next_7_days()
        _load_forecast.cache_clear()

        return {
            "status": "success",
            **result.__dict__,
            "forecast_rows": len(forecast),
            "forecast_origin_date": (
                forecast["origin_date"].max().strftime("%Y-%m-%d")
            ),
            "forecast_start_date": (
                forecast["target_date"].min().strftime("%Y-%m-%d")
            ),
            "forecast_end_date": (
                forecast["target_date"].max().strftime("%Y-%m-%d")
            ),
        }
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
