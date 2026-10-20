"""POST /goal-suggestions: auth, validation, error mapping. Model trouble is never an error (200 with `insight: null`)."""

from __future__ import annotations

import hmac
import json
import logging
import os

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from .contracts import GoalSuggestionRequest
from .data import DataUnavailable
from .digest import GoalAmbiguous, GoalNotFound
from .service import suggest

logger = logging.getLogger("goal_suggest.api")
router = APIRouter()


def _error(status: int, error: str, **extra: object) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": error, **extra})


def _auth_error(request: Request) -> JSONResponse | None:
    expected = os.environ.get("SERVER_API_KEY")
    if not expected:
        logger.error("SERVER_API_KEY is not set; refusing all goal-suggestions requests")
        return _error(503, "unavailable")
    given = request.headers.get("x-api-key", "")
    if not hmac.compare_digest(given.encode(), expected.encode()):
        return _error(401, "unauthorized")
    return None


@router.post("/goal-suggestions")
async def goal_suggestions(request: Request) -> JSONResponse:
    if (denied := _auth_error(request)) is not None:
        return denied
    try:
        body = GoalSuggestionRequest.model_validate(await request.json())
    except ValidationError as exc:
        detail = [{"loc": list(e["loc"]), "msg": e["msg"], "type": e["type"]} for e in exc.errors()]
        return _error(422, "invalid_request", detail=json.loads(json.dumps(detail, default=str)))
    except ValueError:  # malformed JSON
        return _error(422, "invalid_request", detail=[{"loc": ["body"], "msg": "invalid JSON", "type": "json_invalid"}])
    try:
        resp = await suggest(body)
    except GoalNotFound:
        return _error(404, "goal_not_found")
    except GoalAmbiguous as exc:
        return _error(409, "goal_ambiguous", goal_ids=str(exc).split(", "))
    except DataUnavailable:
        return _error(503, "data_unavailable")
    return JSONResponse(status_code=200, content=resp.model_dump(mode="json"))
