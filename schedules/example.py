from managed_deepagents import define_schedule

# Runs once a day and asks the agent to produce a short digest.
# Schedule declarations require static literals (no env vars, no function
# calls) because they're evaluated at deploy time.
daily_digest = define_schedule(
    name="daily-digest",
    cron="0 9 * * *",
    timezone="UTC",
    prompt="Summarize anything noteworthy from the last 24 hours in 3 bullet points.",
)
