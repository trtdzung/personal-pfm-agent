"""POST /goal-coach: auth, validation, error mapping. No internal detail leaks."""

from __future__ import annotations

import asyncio
import hmac
import json
import logging
import os

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from .contracts import CoachRequest
from .nlu import ModelUnavailableError
from .service import new_request_id, run_turn

logger = logging.getLogger("goal_coach.api")
router = APIRouter()


def _error(status: int, error: str, **extra: object) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": error, **extra})


@router.post("/goal-coach")
async def goal_coach(request: Request) -> JSONResponse:
    expected = os.environ.get("SERVER_API_KEY")
    if not expected:
        logger.error("SERVER_API_KEY is not set; refusing all goal-coach requests")
        return _error(503, "model_unavailable")
    given = request.headers.get("x-api-key", "")
    if not hmac.compare_digest(given.encode(), expected.encode()):
        return _error(401, "unauthorized")

    try:
        body = CoachRequest.model_validate(await request.json())
    except ValidationError as exc:
        detail = [{"loc": list(e["loc"]), "msg": e["msg"], "type": e["type"]} for e in exc.errors()]
        return _error(422, "invalid_request", detail=json.loads(json.dumps(detail, default=str)))
    except ValueError:  # malformed JSON
        return _error(422, "invalid_request", detail=[{"loc": ["body"], "msg": "invalid JSON", "type": "json_invalid"}])

    request_id = new_request_id()
    try:
        resp = await asyncio.to_thread(run_turn, body, request_id=request_id)
    except ModelUnavailableError:
        return _error(503, "model_unavailable", request_id=request_id)
    except Exception:  # never a 500 with internals
        logger.exception("goal_coach unexpected failure request_id=%s", request_id)
        return _error(503, "model_unavailable", request_id=request_id)
    return JSONResponse(status_code=200, content=resp.model_dump(mode="json"))
