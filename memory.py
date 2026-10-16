from managed_deepagents import define_memory

# Memory is off by default. This declares a shared, agent-scoped memory
# file: every caller reads and writes the same durable file, so never
# store per-user or credential data here. Delete this file to opt back
# out entirely.
memory = define_memory(scope="agent")
