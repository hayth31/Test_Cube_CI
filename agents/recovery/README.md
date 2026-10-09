# agents/recovery/  ·  Recovery Manager

**Owner:** @hayth31

This is the integrated Recovery agent. It evaluates fee lines against the complete upstream evidence chain and recommends only claims supported by explicit contradictions.

| | |
|---|---|
| **Reads (inputs)** | Channel fee / reimbursement report lines (no camera) |
| **Reads (previous evidence)** | **All** earlier records |
| **Produces** | per-charge position (supports / contradicts / silent), a claim with attached evidence and a dollar figure, and an explicit list of what cannot be claimed and why |
| **Recommended `check_key`s** | one `charge_<line_id>` check per fee line |
| **`decision.outcome` values** | `claim_recommended, no_claim, insufficient_evidence, pending_review` |

Your check semantics are the one place verdicts read differently: the condition is *"this charge is supported by evidence"*, so `FAIL` = contradicted = **claim**, `UNCERTAIN` = SILENT = **never a claim**. A wrongly filed claim costs a seller standing; a missed one costs only money, so report **precision**. You will meet every contract and data problem first (findings F-07 to F-12): raise them early. In a **Specialist Pod** there is no Prep evidence: inbound-defect charges must be SILENT, not guessed.

## Implementation

```text
agents/recovery/
├── app.py          ← expose  handle(agent_input: dict) -> dict  (an Agent Output). Keep `app = make_app(...)` to serve over HTTP.
├── agent.json      ← stage · agent_id · owner · mode (inproc | http) · url · an honest `implementation` description
├── PROVENANCE.md   ← your Round 2 repo URL + commit this came from (create it)
├── engine.py       ← deterministic fee/evidence evaluator
└── README.md       ← operation and limits
```

The deterministic engine treats the assertion "this charge is supported" as the check condition: `FAIL` means upstream evidence contradicts the charge and can support a claim; `UNCERTAIN` means silent/no claim. Missing evidence is never upgraded into a claim.

## Run on its own

```sh
.venv/bin/uvicorn agents.recovery.app:app --port 8105
curl localhost:8105/health
```
Then set `"mode": "http"` in `agent.json` if you want the orchestrator to call it over HTTP.

## Limits

- Weight-tier charges remain silent unless upstream evidence contains measured weight or dimensions.
- The current synthetic evaluation demonstrates routing and evidence reasoning, not production claim precision.
