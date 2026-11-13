# Contributing

AATM is under active foundational development. Keep changes scoped, tested, and honest about what is and is not functional.

## Guidelines

- Read `AATM_MASTER_DEVELOPMENT_PROMPT.md`, `STATUS.txt`, `IMPLEMENTATION_STATUS.md`, `BLOCKERS.txt`, and `NEXT_ACTIONS.txt` before taking on work.
- Keep local services loopback-bound by default.
- Never commit credentials, `.env` files, browser profiles, local databases, or generated build output.
- Do not invent external provider endpoints; inspect authoritative documentation first.
- Add tests for behavior and report only tests actually run.
- Do not mark a phase verified based on file creation alone.
- Preserve approval boundaries around destructive/external actions and protected branches.
- Keep progress updates factual; the heartbeat updates timestamps and idle state, not evidence of coding progress.

## Verification commands

```bash
(cd backend && ../.venv/bin/python -m pytest)
(cd web && npm run build)
bash -n scripts/*.sh
```

Windows PowerShell script testing must be performed on Windows 11.
