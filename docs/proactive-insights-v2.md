# Proactive insight v2

New stateless endpoint: `POST /proactive-insights`, implemented in `proactive_endpoint.py`, included by `server.py`. Existing `/chat`, `/insight`, memory and transfer tools retain their contracts.

PFM assembles a financial snapshot from its canonical engine. The model receives the full normalized domains plus the latest 500 transaction rows; aggregates use all eligible rows and coverage/truncation is explicit. Prompt and seven few-shot examples live in `prompts/proactive_insight.md`.

Input: `{ snapshot_id: <64 lowercase hex SHA-256>, snapshot: { schemaVersion: "2.0", asOf, timezone: "Asia/Ho_Chi_Minh", currency: "VND", dataQuality, candidates, ...financialDomains } }`.

Output: `{ snapshot_id, candidate_id, title, body }`. Candidate must have minimum priority in the input. No numerical values or URLs in prose; PFM renders numerical metrics and actions from the selected server-owned candidate. Reject invented candidate, invalid schema, longer copy or priority downgrade. Title ≤70 chars; body ≤240 chars; input snapshot ≤350k chars. Authentication uses `X-API-Key` matching `SERVER_API_KEY`.

The model is created with `default_model(AI_PLATFORM_API_KEY, timeout=15, max_retries=0)`. It has no tools/checkpointer, cannot write chat history and cannot initiate transactions. No raw snapshot is logged. Missing credentials or model failure return 503; PFM keeps a deterministic fallback. Invalid generated selection returns 502. This does not constitute semantic proof of generated copy: prompt adherence and copy quality still need evaluation with the live model.

Standalone local runner:

```powershell
# Set SERVER_API_KEY to match PFM's AGENT_API_KEY and configure AI_PLATFORM_API_KEY locally.
.venv\Scripts\python.exe -m uvicorn proactive_endpoint:app --host 127.0.0.1 --port 8081
```

`GET /health` on this standalone app is a liveness check, not model readiness. Set PFM `AGENT_PROACTIVE_API_URL=http://127.0.0.1:8081/proactive-insights` to test independently of the existing chat backend. The override uses API key authentication directly. In deployment, omit that override and PFM uses its existing agent base URL/auth path.

Validation command:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_server.py tests/test_proactive_endpoint.py tests/test_insight_endpoint.py -q --disable-warnings
```

On 23/09/2026: 47 related tests passed. Local model credentials are absent, so live model generation is not yet verified. The separate legacy managed-agent import test requires `managed_deepagents`, currently missing from the local venv.

Detailed product/data/threshold/cache/UI specification: sibling repo `pfm/docs/insights/PROACTIVE-V2.md`.
