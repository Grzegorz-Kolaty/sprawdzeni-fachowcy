# Project agent instructions

## General rules

* Read the existing implementation before making changes.
* Follow the existing project structure and conventions.
* Prefer generic solutions over special cases.
* Do not hardcode behavior for specific companies, customers, names, URLs, or test fixtures unless the task explicitly
  requires it.
* Do not weaken existing validation or verification semantics just to make a test pass.
* Do not modify unrelated code.
* Do not rename or move files unless it is necessary for the requested change.
* Keep changes focused on the actual task.

## Backend

The backend is located in `backend/`.

Python source code is located in:

`backend/src/`

When working on backend Python code, run commands from the `backend/` directory unless there is a specific reason not
to.

The project uses a `src` layout. Imports should use the application package normally, for example:

`from app...`

Do not add manual `sys.path` modifications or import hacks.

## Tests

After modifying backend implementation or backend tests:

1. Identify and run the tests relevant to the changed behavior.
2. Do not finish the task without running the relevant regression tests.
3. If a test fails:

    * inspect the actual failure,
    * determine whether the implementation or the test is wrong,
    * fix only what is genuinely incorrect,
    * do not weaken assertions merely to make tests pass,
    * do not bypass validation or verification logic.

After fixing a failure, rerun the affected tests until they pass.

### Claim / evidence verification

If the task touches claim verification, evidence verification, evidence candidate evaluation, provider evidence, or
related behavior, always run:

```bash
uv run pytest tests/services/test_claim_evidence_verification.py tests/providers/test_evidence_candidate_evaluator.py -q
```

The verification implementation must remain generic.

Never introduce special-case behavior for:

* BOS
* Blachotrapez

These names may appear in fixtures or regression tests, but production behavior must not depend on them.

## Python quality checks

For every changed Python file:

1. Format the changed files with Ruff:

   uv run ruff format <changed-files>

2. Run Ruff linting:

   uv run ruff check <changed-files>

3. Fix legitimate linting issues if necessary.

4. Rerun Ruff until it passes.

Do not format or modify unrelated files.

Before finishing a backend task, ensure:

- relevant pytest tests pass,
- Ruff reports no errors,
- changed Python files are formatted.

## Formatting

Respect the existing formatting configuration of the project.

Do not manually reformat unrelated files.

WebStorm may automatically format files on save. Do not undo formatting changes produced by the configured project
formatter unless they are incorrect.

## Fixing failures

When tests or quality checks fail:

1. Read the complete error.
2. Find the root cause.
3. Prefer correcting the implementation over adding exceptions or workarounds.
4. Modify tests only when the test itself is incorrect or the intended behavior has explicitly changed.
5. Never make assertions less strict solely to obtain a passing test suite.
6. Rerun the relevant command after every fix.

## Final verification

Before declaring an implementation task complete:

1. Review the diff.
2. Make sure no unrelated files were changed.
3. Run the relevant tests.
4. Run Ruff on changed Python files.
5. Confirm all checks pass.

## Final response

At the end of every implementation task, report:

* what was changed,
* every file changed,
* which tests were run,
* the final pytest result,
* the Ruff result,
* any remaining issue or limitation.

Do not claim that tests or Ruff passed unless they were actually executed.
