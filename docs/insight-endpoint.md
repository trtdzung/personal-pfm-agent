# Proactive PFM insight endpoint

`POST /insight` requires `X-API-Key: <SERVER_API_KEY>` and, through GreenNode Runtime, the gateway Bearer token. This endpoint creates a fresh, stateless model call with no checkpointer or conversation thread. It never uses `/chat` or `/chat/history`.

PFM sends `user_id`, `insight_id`, `snapshot_id`, `as_of`, `trigger_type`, and `metrics`. Supported trigger types are `jar_burn` and `investment_nudge`. The optional `task` field is accepted for compatibility but ignored; the backend owns the system prompt.

For `jar_burn`, metrics contain the jar ID and label, severity, period end, balance, days remaining, recent daily burn, safe daily spend, days to empty, projected shortfall, active spending days, and `source: "estimated"`. For `investment_nudge`, metrics contain the financial features defined by PFM's `InvestmentFeatures`: unallocated balance, cashflow, monthly trend, jar utilization, net worth, liabilities, runway, savings rate, goals, `as_of`, and `source: "estimated"`.

Response example:

```json
{
  "snapshot_id": "<same as request>",
  "product_id": null,
  "explanation": "Cần xem thêm các nghĩa vụ tài chính trước khi phân bổ tiền.",
  "suggested_action": "Xem lại kế hoạch chi tiêu và khoản dự phòng."
}
```

`product_id` can be `m-sinh-loi`, `tiet-kiem`, or `null`. The model chooses only when the available metrics provide enough basis; unknown obligations or reserve needs lead to `null`. For `jar_burn`, it is always `null`. Both text fields must be nonempty, bounded, and contain no digits. Model failures return 503; invalid model output returns 502. The PFM widget retains its deterministic warning or neutral fallback in either case.
