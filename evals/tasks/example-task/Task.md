# example-task

A minimal Harbor task for smoke-testing the research-assistant agent.

- **instruction**: `instruction.md`
- **environment**: `environment/` (empty — the agent starts from a blank
  working directory)
- **grading**: `tests/test_answer.py` checks that `answer.md` was created
  and is non-empty

Run it with `mda evals init -i` to get Harbor set up, then execute this
task through Harbor once your environment/tests match the schema in the
[Harbor docs](https://www.harborframework.com/docs/tasks) — the exact
Task.md schema is still evolving in beta, so treat this file as a
starting point rather than a guaranteed-correct reference.
