from managed_deepagents import auth, define_identity

# Default: callers must present a valid LangSmith workspace API key
# (checked against LangSmith Cloud, sent as the `x-api-key` header).
# This secures the deployment but does not isolate individual users'
# conversations from one another.
#
# For per-user thread isolation in browser-based apps, swap in Supabase:
#   identity = define_identity(auth=auth.supabase(project_ref="your-project-ref"))
identity = define_identity(auth=auth.langsmith_api_key())
