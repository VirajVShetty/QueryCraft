# Verification

## Executed checks

- `python -m pytest -q` → **92 passed**.
- `python -m pip check` → **No broken requirements found**.
- Live local `GET /api/health` → **HTTP 200**, `{"status":"ok"}`.
- `tests/browser-smoke.js` → **11 checks passed** against the actual local demo API.
- `tests/browser-fidelity.js` → **7 checks passed**, including the full integer tests (`binaryOnly: false`).

The browser suites inspect real DOM state, SQLite responses, and actual CSV blobs. They do not substitute fabricated HTTP responses for server execution.

## Browser scenarios

### Workflow suite

1. Generate demo SQL without fetching query results.
2. Explicit execution returns the actual synthetic fixture revenue of 110.
3. Editing SQL clears previous results and disables stale CSV export.
4. DROP TABLE is rejected with a visible error.
5. A successful zero-row SELECT shows the empty state.
6. A 205-row recursive SELECT returns 200 rows with a truncation indicator.
7. HTML-like cell data is rendered as text, not executable markup.
8. CSV export escapes formulas and embedded quotes.
9. SQLite numeric overflow is represented as text so browser JSON parsing succeeds.
10. New query resets editors/results and disables execution/export.
11. No horizontal page overflow at the tested desktop viewport.

### Result-fidelity suite

1. Binary values retain their explicit hex-object API contract.
2. Binary cells display as `0x`-prefixed hex; null cells display `NULL`.
3. CSV preserves binary hex, empty null cells, quote escaping, and formula protection.
4. Scalar CSV behavior remains unchanged.
5. Integers outside JavaScript's safe range arrive as exact decimal strings, while safe integers remain numeric.
6. Table cells preserve exact integers, including SQLite minimum and maximum integer values.
7. CSV preserves exact integer values and existing negative-value formula protection.

CSV tests capture the generated Blob and suppress the OS download.

A separate, real temporary custom SQLite database was also exercised: schema discovery and manual SELECT returned its deliberately seeded QA fixture value 42.5. Generation was disabled because no provider was configured.

## Screenshots

Files in `docs/images/` are actual captures of the running application:

- `workbench.png`: full desktop question-to-SQL workflow and executed monthly results.
- `results.png`: SQL review, assumptions, and the results table.
- `mobile.png`: the mobile question composer and collapsed schema inspector.

Monthly results shown in the desktop captures are the synthetic fixture's actual values: January 40, February 30, and March 40. Mobile capture verification confirmed the page content width matches the 390-pixel viewport; schema is initially collapsed on mobile. No credentials or real customer records were used for these captures.

## Credential and distribution checks

The GitHub distribution is built from an explicit source/documentation allowlist. It excludes runtime databases, populated environment files, credentials, virtual environments, caches, Git history, and prior ZIP archives. The README uses portable paths rather than local user directories. `.env.example` contains no API key.

The packaged source was checked with both a targeted credential-pattern audit and `detect-secrets` in offline (`--no-verify`) mode: **neither reported credential findings**. No real embedded key was found to remove. Only blank configuration fields and deliberately fabricated test markers remain. The publication file set also passed the local-user-path audit. This is a publication check, not a guarantee that every possible secret format can be detected. Re-scan future changes before publishing.

## Important boundaries

- **No live LLM inference was performed.** Provider tests use controlled HTTP transports to validate request construction, response validation, and error handling; they do not prove model accuracy or availability.
- Demo and custom QA data are intentionally synthetic fixtures.
- Only SQLite support is claimed.
- Read-only restrictions and bounded handling are tested, but this is not an OS sandbox or a formal security audit. SQLite allocation is not absolutely bounded on every supported Python build.
- The entry point is a loopback-bound Flask development server, not a production deployment.
- The distribution is ready for the repository owner to upload; no remote repository or publication is implied.
