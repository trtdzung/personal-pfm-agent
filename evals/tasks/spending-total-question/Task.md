# spending-total-question

A Harbor task checking that the personal-card-agent correctly sums a
month's transactions from `data/customer_data.json`.

- **instruction**: `instruction.md`
- **environment**: `environment/` (empty — the agent starts from a blank
  working directory; its customer data comes from the `SeedCustomerContext`
  middleware, not from this directory)
- **grading**: `tests/test_answer.py` checks that `answer.md` contains the
  correct August 2026 total (11.324.000 VNĐ), derived by hand from
  `data/customer_data.json`

Run it with `mda evals init -i` to get Harbor set up, then execute this task
through Harbor once your environment/tests match the schema in the
[Harbor docs](https://www.harborframework.com/docs/tasks) — the exact
Task.md schema is still evolving in beta, so treat this file as a starting
point rather than a guaranteed-correct reference.
