# Trying the AI with real Claude

`run_trial.py` runs the real pipeline (parse → clauses → Claude extraction → deadline
calculation) and optionally the chat, without the database or web app.

```bash
cd services/api
export ANTHROPIC_API_KEY=...        # or set it in services/api/.env
uv run python evals/run_trial.py                      # 4 sample contracts, scored
uv run python evals/run_trial.py --only commercial_lease --chat "Can the tenant extend?"
uv run python evals/run_trial.py --file /path/to/contract.pdf --chat "When must we give notice?"
```

- `contracts/` — fictional sample contracts (SaaS subscription, commercial lease, supply
  agreement, mutual NDA) chosen to cover auto-renewal, option windows, fixed review
  dates, deemed receipt, business days and different currencies and governing laws.
- `expected.json` — the answer key. Rules are matched on meaning (type, offset,
  direction, anchor), so equivalent phrasings score the same.
- `results/` — each run's raw output (git-ignored).

Deadlines are calculated as of a fixed date (7 Oct 2026) so runs are comparable. The
script prints token usage and an estimated cost (Claude Opus 5.5 list prices).

Adding real contracts you have already reviewed (with their correct values) to
`contracts/` and `expected.json` turns this into a regression test for prompt changes.
