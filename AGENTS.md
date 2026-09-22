# Project agent instructions

## General rules

- Read the existing implementation before making changes.
- Follow the existing project structure, architecture, naming, and conventions.
- Prefer generic solutions over special cases.
- Do not hardcode behavior for specific companies, customers, names, URLs, domains, or test fixtures unless the task
  explicitly requires it.
- Do not weaken existing validation, verification, or security semantics merely to make a test pass.
- Do not modify unrelated code.
- Do not rename, move, or delete files unless it is necessary for the requested task.
- Keep changes focused on the actual task.
- Prefer the smallest correct change.
- Do not introduce workarounds when the underlying problem can be fixed directly.
- Do not silently change runtime behavior when the task only asks for documentation, formatting, tests, or refactoring.

## Git and change scope

Before making changes:

1. Inspect the relevant files.
2. Check the current working tree when useful:

   ```bash
   git status --short
   ```

3. Be aware of any pre-existing modifications and do not overwrite or revert them unless the task explicitly requires
   it.

After making changes:

1. Review the diff.
2. Verify that only files related to the task were modified.
3. Verify that formatting or tooling did not introduce unrelated changes.

Useful commands:

```bash
git status --short
git diff --stat
git diff
```

A large formatting-only diff outside the requested change counts as an unrelated modification.

Do not commit changes unless the user explicitly asks for a commit.

## Backend

The backend is located in:

```text
backend/
```

Python source code is located in:

```text
backend/src/
```

When working on backend Python code, run backend commands from the `backend/` directory unless there is a specific
reason not to.

The project uses a `src` layout.

Imports should use the application package normally, for example:

```python
from app...
```

Do not:

- import through `src.app`,
- add manual `sys.path` modifications,
- add `PYTHONPATH` workarounds when the project configuration already supports the `src` layout,
- introduce import hacks to make tests pass.

Pytest is configured through `backend/pyproject.toml` with the source directory available on the Python path.

## Tests

After modifying backend implementation or backend tests:

1. Identify the tests relevant to the changed behavior.
2. Run those tests before finishing the task.
3. Run any required regression tests described below.
4. If a test fails:
    - read the complete failure,
    - inspect the root cause,
    - determine whether the implementation or the test is wrong,
    - fix only what is genuinely incorrect,
    - do not weaken assertions merely to make tests pass,
    - do not bypass validation or verification logic,
    - do not introduce company-specific exceptions.

After fixing a failure, rerun the affected tests until they pass or until a genuine external/blocking issue is
identified.

Do not claim that tests passed unless they were actually executed.

## Claim / evidence verification

If the task touches any of the following:

- claim verification,
- evidence verification,
- claim evidence verification,
- evidence candidate evaluation,
- evidence discovery,
- evidence providers,
- evidence scoring,
- evidence source recovery,
- related verification behavior,

always run:

```bash
uv run pytest tests/services/test_claim_evidence_verification.py tests/providers/test_evidence_candidate_evaluator.py -q
```

The verification implementation must remain generic.

Never introduce production behavior that depends specifically on:

- BOS
- Blachotrapez

These names may appear in fixtures, tests, examples, or regression cases, but production behavior must not depend on
them.

A regression test involving a specific company is evidence of a generic behavior that must remain correct, not
permission to special-case that company.

## Python quality checks

For every changed Python file, run Ruff linting:

```bash
uv run ruff check <changed-python-files>
```

Then check formatting without modifying files:

```bash
uv run ruff format --check <changed-python-files>
```

### If Ruff formatting already passes

Do not run the formatter unnecessarily.

### If Ruff reports that formatting is required

Before applying formatting:

1. Review the current task scope.
2. Review the current Git diff.
3. Determine whether formatting would affect only the lines or code reasonably related to the task.

Only run:

```bash
uv run ruff format <changed-python-files>
```

when formatting changes are reasonably within the scope of the task or the affected file is already consistently
Ruff-formatted.

If applying Ruff would create a substantial unrelated formatting diff:

- do not apply it automatically,
- preserve the requested functional/documentation change,
- report that the file has pre-existing Ruff formatting differences,
- report the result of `ruff format --check`,
- do not claim that formatting passes.

Do not reformat substantial pre-existing code merely because the task touched the same file.

Do not run Ruff formatting across the entire backend unless the task explicitly asks for repository-wide formatting.

Do not use automatic lint fixes such as:

```bash
ruff check --fix
```

unless the task explicitly calls for automatic fixes or the required fix has been reviewed and is clearly safe.

Prefer understanding and correcting lint issues deliberately.

## Formatting

Respect the formatting configuration already present in the project.

Do not manually reformat unrelated code.

Do not change indentation, wrapping, imports, quoting, or layout outside the requested scope unless required by the
configured formatter and the resulting change remains appropriately scoped.

WebStorm may automatically reformat files on save. Treat such changes like any other changes:

- inspect them,
- keep them if they are correct and reasonably scoped,
- do not allow IDE formatting to create a large unrelated diff,
- revert unrelated formatting changes when necessary.

Formatting must never obscure the actual behavioral change being made.

## Fixing failures

When tests, Ruff, imports, or other quality checks fail:

1. Read the complete error or failure.
2. Identify the root cause.
3. Inspect the implementation involved.
4. Prefer correcting the actual implementation problem over adding exceptions or workarounds.
5. Modify tests only when:
    - the test itself is incorrect, or
    - the intended behavior has explicitly changed.
6. Never make an assertion less strict solely to obtain a passing test suite.
7. Never hardcode a fixture value solely to satisfy a regression test.
8. Rerun the relevant command after every fix.
9. Stop and report the blocker if passing the check would require an unrelated or unsafe change.

## Dependencies and project configuration

Do not install packages globally.

Use the project's existing dependency management.

For backend Python commands, use `uv`, for example:

```bash
uv run python ...
uv run pytest ...
uv run ruff ...
```

Do not add or update dependencies unless the task requires it.

Do not modify:

- `pyproject.toml`,
- `uv.lock`,
- Docker configuration,
- Alembic configuration,
- environment configuration,

unless the task requires such a change.

If a dependency or configuration change is necessary, explain why it is required.

## Database and migrations

Do not create, modify, delete, or regenerate Alembic migrations unless the task requires a database schema change.

Do not rewrite existing migrations merely to make current code pass.

When a schema change is required:

- inspect the existing models and migrations,
- make the smallest appropriate migration,
- preserve compatibility with the intended migration history.

## Tests versus production behavior

Tests describe expected behavior but are not themselves the production specification.

When a test and implementation disagree:

1. Determine the intended generic behavior.
2. Inspect surrounding implementation and existing tests.
3. Fix the component that is actually wrong.

Do not:

- special-case test inputs,
- branch on fixture names,
- branch on known company names,
- branch on known URLs solely because they appear in tests,
- reduce verification strictness merely to satisfy a test.

## Documentation-only tasks

If a task explicitly asks only for:

- a comment,
- a docstring,
- documentation,
- wording clarification,

do not change runtime behavior.

For such tasks:

- keep the code diff minimal,
- do not refactor surrounding code,
- do not reformat an entire legacy file merely because Ruff detects pre-existing formatting differences,
- still run the relevant tests when the documentation change touches an area with required regression tests,
- still run Ruff linting and formatting checks,
- report pre-existing formatting issues instead of generating a large unrelated diff.

## Refactoring

Refactor only when:

- the task explicitly requests it, or
- a small local refactor is necessary to implement the requested behavior correctly.

Do not perform opportunistic cleanup of unrelated code.

Do not combine a behavioral change with a repository-wide cleanup or formatting pass.

If broader cleanup would be beneficial, mention it separately instead of including it in the current task.

## Final verification

Before declaring a backend implementation task complete:

1. Review:

   ```bash
   git status --short
   git diff --stat
   git diff
   ```

2. Confirm that only intended files were changed.
3. Confirm that the diff is proportional to the task.
4. Run the relevant pytest tests.
5. Run the required claim/evidence regression tests when applicable.
6. Run Ruff linting on changed Python files.
7. Run Ruff formatting checks on changed Python files.
8. If formatting cannot be applied without creating unrelated changes, leave it unapplied and report that fact
   explicitly.
9. Check that no debug code, temporary files, hardcoded fixture behavior, or accidental changes remain.

Do not declare the task fully clean if a required check failed.

A task may still be reported as implemented when a check exposes a clearly pre-existing issue that should not be
modified within the task scope, but the issue and the exact failing check must be stated explicitly.

## Final response

At the end of every implementation task, report:

- what was changed,
- every file changed,
- whether runtime behavior changed,
- which tests were run,
- the final pytest result,
- the Ruff lint result,
- the Ruff formatting check result,
- any remaining issue, warning, blocker, or limitation.

When relevant, include the exact test summary, for example:

```text
7 passed
```

Do not claim that:

- tests passed,
- Ruff passed,
- formatting passed,
- no unrelated changes exist,

unless those statements were actually verified.

If a formatter or tool attempted to modify unrelated code, mention it and ensure the unrelated changes are not left in
the final diff.