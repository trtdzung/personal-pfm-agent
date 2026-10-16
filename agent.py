from managed_deepagents import define_deep_agent

from middleware.audit import log_tool_calls
from middleware.seed_customer_context import SeedCustomerContext

# define_deep_agent has no `checkpointer` parameter in managed-deepagents==0.6.1;
# relying on the platform's own default checkpointing instead.
agent = define_deep_agent(
    name="personal-card-agent",
    model="openai:gpt-5.5",
    tools=[],
    middleware=[log_tool_calls, SeedCustomerContext()],
)
