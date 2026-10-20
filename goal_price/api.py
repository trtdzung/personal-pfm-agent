"""POST /goal-price-estimates: auth, validation. Model or search trouble is never an error (200 with `estimate: null`)."""

from __future__ import annotations

import json

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from goal_suggest.api import _auth_error, _error

from .contracts import PriceEstimateRequest
from .service import run

router = APIRouter()


@router.post("/goal-price-estimates")
async def goal_price_estimates(request: Request) -> JSONResponse:
    if (denied := _auth_error(request)) is not None:
        return denied
    try:
        body = PriceEstimateRequest.model_validate(await request.json())
    except ValidationError as exc:
        detail = [{"loc": list(e["loc"]), "msg": e["msg"], "type": e["type"]} for e in exc.errors()]
        return _error(422, "invalid_request", detail=json.loads(json.dumps(detail, default=str)))
    except ValueError:  # malformed JSON
        return _error(422, "invalid_request", detail=[{"loc": ["body"], "msg": "invalid JSON", "type": "json_invalid"}])
    resp = await run(body)
    return JSONResponse(status_code=200, content=resp.model_dump(mode="json", exclude_none=True))
