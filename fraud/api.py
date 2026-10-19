"""Fraud routes: auth first, strict validation, no execution capabilities."""
import hmac
import os
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from .contracts import InterveneRequest, DiagnoseRequest, ScanRequest, CaseRequest, EducateRequest, ChatSignalRequest

router = APIRouter(prefix="/fraud")


def _auth_error(request: Request) -> JSONResponse | None:
    expected = os.environ.get("SERVER_API_KEY", "")
    given = request.headers.get("x-api-key", "")
    if not expected or not given or not hmac.compare_digest(given.encode(), expected.encode()):
        return JSONResponse(status_code=401, content={"error": "unauthorized"})
    return None


@router.post("/intervene")
async def intervene(request: Request) -> JSONResponse:
    if (error := _auth_error(request)) is not None:
        return error
    try:
        body = InterveneRequest.model_validate(await request.json())
    except (ValidationError, ValueError):
        return JSONResponse(status_code=422, content={"error": "invalid_request"})
    from .intervene import propose
    from .guard import GuardViolation
    try:
        result = await propose(body)
    except GuardViolation:
        return JSONResponse(status_code=502, content={"error": "invalid_model_output"})
    except Exception:
        return JSONResponse(status_code=503, content={"error": "model_unavailable"})
    return JSONResponse(content=result.model_dump())


@router.post("/diagnose")
async def diagnose(request: Request) -> JSONResponse:
    if (error := _auth_error(request)) is not None:
        return error
    try:
        body = DiagnoseRequest.model_validate(await request.json())
    except (ValidationError, ValueError):
        return JSONResponse(status_code=422, content={"error": "invalid_request"})
    from .diagnose import propose
    from .guard import GuardViolation
    try:
        result = await propose(body)
    except GuardViolation:
        return JSONResponse(status_code=502, content={"error": "invalid_model_output"})
    except Exception:
        return JSONResponse(status_code=503, content={"error": "model_unavailable"})
    return JSONResponse(content=result.model_dump())


@router.post("/scan")
async def scan(request: Request) -> JSONResponse:
    if (error := _auth_error(request)) is not None:
        return error
    try:
        body = ScanRequest.model_validate(await request.json())
    except (ValidationError, ValueError):
        return JSONResponse(status_code=422, content={"error": "invalid_request"})
    from .scan import propose
    from .guard import GuardViolation
    try:
        result = await propose(body)
    except GuardViolation:
        return JSONResponse(status_code=502, content={"error": "invalid_model_output"})
    except Exception:
        return JSONResponse(status_code=503, content={"error": "model_unavailable"})
    return JSONResponse(content=result.model_dump())


@router.post("/case")
async def case(request: Request) -> JSONResponse:
    if (error := _auth_error(request)) is not None:
        return error
    try:
        body = CaseRequest.model_validate(await request.json())
    except (ValidationError, ValueError):
        return JSONResponse(status_code=422, content={"error": "invalid_request"})
    from .case_interview import propose
    from .guard import GuardViolation
    try:
        result = await propose(body)
    except GuardViolation:
        return JSONResponse(status_code=502, content={"error": "invalid_model_output"})
    except Exception:
        return JSONResponse(status_code=503, content={"error": "model_unavailable"})
    return JSONResponse(content=result.model_dump())


@router.post("/educate")
async def educate(request: Request) -> JSONResponse:
    if (error := _auth_error(request)) is not None:
        return error
    try:
        body = EducateRequest.model_validate(await request.json())
    except (ValidationError, ValueError):
        return JSONResponse(status_code=422, content={"error": "invalid_request"})
    from .educate import propose
    from .guard import GuardViolation
    try:
        result = await propose(body)
    except GuardViolation:
        return JSONResponse(status_code=502, content={"error": "invalid_model_output"})
    except Exception:
        return JSONResponse(status_code=503, content={"error": "model_unavailable"})
    return JSONResponse(content=result.model_dump())


@router.post("/chat-signal")
async def chat_signal(request: Request) -> JSONResponse:
    if (error := _auth_error(request)) is not None:
        return error
    try:
        body = ChatSignalRequest.model_validate(await request.json())
    except (ValidationError, ValueError):
        return JSONResponse(status_code=422, content={"error": "invalid_request"})
    from .chat_signal import propose
    from .guard import GuardViolation
    try:
        result = await propose(body)
    except GuardViolation:
        return JSONResponse(status_code=502, content={"error": "invalid_model_output"})
    except Exception:
        return JSONResponse(status_code=503, content={"error": "model_unavailable"})
    return JSONResponse(content=result.model_dump())
