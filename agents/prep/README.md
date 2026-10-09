# agents/prep/  ·  Prep Manager

**Owner:** @jpatty-vin

This is the integrated Prep agent. It evaluates recorded observations with deterministic rules for reproducible offline runs and can analyze image captures with Gemini when `GEMINI_API_KEY` is present.

| | |
|---|---|
| **Reads (inputs)** | Photos of the prepped unit and the work order |
| **Reads (previous evidence)** | Receiving |
| **Produces** | per-requirement compliance verdicts, plus measured weight/dimensions if you can |
| **Recommended `check_key`s** | `polybag_sealed, suffocation_warning, fnsku_label_placement, original_barcode_covered, expiry_legible, handling_marks` |
| **`decision.outcome` values** | `compliant, non_compliant, pending_review` |

**Specialist Pods have no Prep Manager: this folder is unused there** (the Specialist flow skips it). For Standard Pods: Recovery has asked Prep to record measured weight and dimensions in `payload.measurements`, because most sample fee lines are weight-tier fees with no evidence (finding F-07, see [`docs/decisions.md`](../../docs/decisions.md)). Look up Amazon's published prep requirements; do not infer them from the sample CSV. Your cost per check has to fit inside $0.40–$1.10 per unit.

## Implementation

```text
agents/prep/
├── app.py          ← expose  handle(agent_input: dict) -> dict  (an Agent Output). Keep `app = make_app(...)` to serve over HTTP.
├── agent.json      ← stage · agent_id · owner · mode (inproc | http) · url · an honest `implementation` description
├── PROVENANCE.md   ← your Round 2 repo URL + commit this came from (create it)
├── engine.py       ← tenant validation, rules and optional vision call
└── README.md       ← operation and limits
```

The adapter reads the subject, captures and previous evidence, validates tenant boundaries, emits the shared Agent Output contract and seals records with a content hash. In offline mode it records `prep-r2-rules` and zero model calls. Live vision performs at most one batched call per unit and fails open to `UNCERTAIN` when evidence is insufficient.

## Run on its own

```sh
.venv/bin/uvicorn agents.prep.app:app --port 8102
curl localhost:8102/health
```
Then set `"mode": "http"` in `agent.json` if you want the orchestrator to call it over HTTP.

## Limits

- The ten Pod cases are synthetic and do not measure visual perception accuracy.
- Live vision requires labelled images and `GEMINI_API_KEY`; CI intentionally runs offline.
- Weight and dimensions are only available when present in the captured observations.
