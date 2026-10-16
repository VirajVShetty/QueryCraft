# Reference study: PandasAI → Querycraft

User reference: https://github.com/sinaptik-ai/pandas-ai

Reviewed primary source files on the main branch:

- README.md: natural-language access to data, multiple data sources, provider configuration, optional sandboxing.
- pandasai/agent/base.py: separate generation and execution responsibilities; SQL query execution against registered data; retry/correction workflow; conversational state.
- pandasai/core/code_generation/base.py: a generation pipeline that cleans and validates output before execution.
- LICENSE: core licensing and separate terms for enterprise directories. No enterprise code was used.

This is an architectural reference, **not a fork, clone, or PandasAI integration**. No implementation code was copied. Querycraft's modules and UI were written independently.

## Adopted ideas, changed implementation

| General idea | Querycraft decision |
| --- | --- |
| Ask questions about structured data | A question composer beside discovered SQLite schema |
| Ground generation in the available data | Send schema metadata to an explicitly configured provider; never send rows |
| Separate generation, validation, execution | Generate one SQL statement, validate its AST and database compatibility, require user action to run |
| Explain/inspect generated work | Editable SQL, explanation, explicit assumptions, results grid |
| Support different model backends | Small OpenAI-compatible HTTP adapter, server-side environment configuration |
| Recover from generation errors | Surface actionable errors and allow editing/retry; no hidden execution-and-repair loop |

## Intentionally different

PandasAI can generate Python and supports broader dataframe workflows. Querycraft is SQL-only and SQLite-only: it never evaluates generated Python. It has no plotting runtime, dataframe execution environment, vector store, conversational agent memory, or automatic self-correction. Its offline demo uses five exact, transparent templates rather than claiming to perform model inference.

The local read-only connection, AST validation, authorizer, resource budget, and review-before-run workflow are separate layers. None is described as a full security sandbox. SQL safety is not semantic correctness.

## Provider contract

The HTTP adapter uses the Chat Completions JSON request fields `model` and `messages` and reads `choices[0].message.content`. Primary API schema inspected in OpenAI's official client source:
https://github.com/openai/openai-python/blob/main/src/openai/types/chat/completion_create_params.py

The provider must return JSON containing SQL, explanation, and assumptions. Results are validated locally regardless of model output. Tests use explicitly labeled controlled transport responses for deterministic error-path coverage; a live model call requires user-configured credentials and is not implied by those tests.
