# large-transactions-question

A Harbor task checking that the personal-card-agent correctly filters and
lists transactions above a threshold from `data/customer_data.json`.

- **instruction**: `instruction.md`
- **environment**: `environment/` (empty — the agent starts from a blank
  working directory; its customer data comes from the `SeedCustomerContext`
  middleware, not from this directory)
- **grading**: `tests/test_answer.py` checks that `answer.md` mentions all
  three July 2026 transactions over 2,000,000 VNĐ (Vietnam Airlines, Điện
  Máy Xanh, Lotte Mart) and does not mistakenly include a smaller one

Run it with `mda evals init -i` to get Harbor set up, then execute this task
through Harbor once your environment/tests match the schema in the
[Harbor docs](https://www.harborframework.com/docs/tasks) — the exact
Task.md schema is still evolving in beta, so treat this file as a starting
point rather than a guaranteed-correct reference.

**Known caveat:** this repo has no `sandbox/` (deleted — not needed by the
agent itself). It's unconfirmed whether Harbor's grading step gives the
agent a real host filesystem to write `answer.md` into without one, versus
an in-memory virtual filesystem the grader can't see. If this eval task
never produces a gradable `answer.md`, that's the first thing to check.
