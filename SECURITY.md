# Security and credential handling

Querycraft is a **local, single-user development application**. Its loopback binding and SQL safeguards do not make it a production-hosted or multi-tenant service.

## Credentials

- Configure provider credentials through the server environment, never through source code or the browser.
- `.env.example` documents configuration names only. `LLM_API_KEY` is intentionally blank.
- `.env` files are not loaded automatically and should never be committed if populated.
- Tests contain explicitly fabricated marker strings to verify that provider credentials do not leak into responses or error messages. They are not usable API keys.
- Application screenshots use the no-key synthetic demo and contain no provider credentials or private customer data.

The distribution package excludes local environment files, private-key files, databases, virtual environments, caches, generated archives, and Git history. `.gitignore` protects common local-secret paths, but does not replace review or secret scanning.

If a real key is ever committed or published, **revoke or rotate it with its provider immediately**. Removing it from a file or deleting a commit does not make the exposed key safe.

## Data and model boundary

AI mode sends the question and schema metadata to the configured provider. It does not send sample rows or query results. Questions and schema identifiers can still be sensitive; use only providers appropriate for your data.

Read-only execution does not hide results from the person using the application. Do not connect data that the local user should not access.

## Execution boundary

The engine layers SQL AST checks, read-only SQLite access, query-only mode, a SQLite authorizer, a query deadline, and result limits. These are risk-reduction measures, not an OS sandbox or an absolute memory/resource bound. Use trusted database files and preferably disposable copies.

Do not expose the development server to public networks. Authentication, TLS termination, process isolation, production serving, and tenant separation would require a separate deployment design.

## Reporting a vulnerability

Do not post real keys, private database content, or exploitable sensitive details in public issues. Share a minimal reproduction using synthetic data through a private reporting channel offered by the repository owner.
