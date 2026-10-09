import os
import time
import json
import re
from typing import List, Dict, Any, Tuple
from shared.utils import sample_data

MODEL_NAME = "gemini-2.5-flash"
MODEL_PROVIDER = "google"
PROMPT_VERSION = "3.0.0"
SYSTEM_PROMPT = (
    "You are an Amazon FBA prep compliance inspection assistant. "
    "Analyze the images for polybag sealing, suffocation warning, barcode coverage, and label placement."
)

RULES = [
    ("polybag_sealed", "polybag_present_sealed", {"yes"}, {"not_sealed", "missing"}),
    ("suffocation_warning", "suffocation_warning", {"legible"}, {"obscured_by_fold", "missing"}),
    ("fnsku_label_placement", "fnsku_label_placement", {"flat"}, {"on_seam", "on_curve", "on_edge", "missing"}),
    ("original_barcode_covered", "original_barcode_covered", {"yes"}, {"no"}),
    ("expiry_legible", "expiry_date", {"legible"}, {"illegible_after_wrap"}),
    ("handling_marks", "handling_marks", {"all_present"}, {"some_missing"}),
]

def verdict_from(value: str, ok: set, bad: set) -> str:
    if value in ok:
        return "PASS"
    if value in bad:
        return "FAIL"
    return "UNCERTAIN"


def _unit_in_sample(kind: str, unit_id: str) -> bool:
    try:
        return any(row["unit_id"] == unit_id for row in sample_data.rows(kind))
    except Exception:
        return False


def validate_tenant_and_extract_refs(request: Dict[str, Any]) -> Tuple[List[str], Dict[str, Any]]:
    subject = request.get("subject", {})
    org_id = subject.get("org_id")
    subject_id = subject.get("subject_id")

    if not org_id or not subject_id:
        raise LookupError("Missing subject org_id or subject_id")

    # Sample CSV Row lookup for sample dataset integration
    try:
        r = sample_data.row("prep", subject_id, org_id)
    except LookupError:
        r = None

    # Refuse a known sample subject owned by another organisation instead of
    # falling through to a generic offline answer.
    if r is None and (_unit_in_sample("prep", subject_id) or _unit_in_sample("receiving", subject_id)):
        raise LookupError(f"subject {subject_id} belongs to another tenant")

    upstream_refs = []
    for ev in request.get("previous_evidence", []):
        ev_org = ev.get("subject", {}).get("org_id")
        if ev_org and ev_org != org_id:
            raise LookupError(f"Cross-tenant evidence rejected: expected org_id='{org_id}', found '{ev_org}'")
        
        rec_id = ev.get("record_id")
        if rec_id:
            upstream_refs.append(rec_id)
            
    return upstream_refs, r


def call_gemini_vision(request: Dict[str, Any], sample_row: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], str, float, float, Any]:
    api_key = os.getenv("GEMINI_API_KEY")
    inputs = request.get("inputs", [])
    context = request.get("context", {})

    usable_inputs = [item for item in inputs if os.path.isfile(item.get("ref", ""))]

    # Use recorded observations when live vision is unavailable or there are no
    # actual captures. A key alone must never turn a text-only prompt into visual
    # evidence.
    if not api_key or not usable_inputs:
        if sample_row:
            checks = []
            for key, col, ok, bad in RULES:
                val = sample_row.get(col, "not_required")
                if val != "not_required":
                    checks.append({
                        "check_key": key,
                        "verdict": verdict_from(val, ok, bad),
                        "confidence": 0.95,
                        "detail": f"Sample dataset observation: {val}"
                    })
            price = float(sample_row.get("prep_price_usd", 0.50))
            return checks, "prep-r2-rules", 10.0, price, None

        # No observation source means unknown, never a synthetic PASS.
        return [
            {
                "check_key": "prep_observation",
                "verdict": "UNCERTAIN",
                "confidence": 0.0,
                "detail": "No recorded Prep observation or readable image capture was supplied.",
                "uncertain_reason": "insufficient_evidence",
            }
        ], "prep-r2-rules", 0.0, 0.50, None

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=api_key)
        pkg_type = context.get("packaging", "unspecified")
        parts = [f"Packaging Context: {pkg_type}\n\nPerform all relevant Amazon FBA prep compliance checks."]

        for item in usable_inputs:
            ref_path = item.get("ref", "")
            if os.path.exists(ref_path):
                with open(ref_path, "rb") as f:
                    data = f.read()
                    mime = "image/png" if ref_path.lower().endswith(".png") else "image/jpeg"
                    parts.append(types.Part.from_bytes(data=data, mime_type=mime))

        start_time = time.perf_counter()
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=parts,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                response_mime_type="application/json"
            )
        )
        latency_ms = (time.perf_counter() - start_time) * 1000

        raw = json.loads(response.text)
        checks = raw.get("checks", [])
        price = float(sample_row.get("prep_price_usd", 0.50)) if sample_row else 0.50
        return checks, MODEL_NAME, latency_ms, price, None

    except Exception as e:
        error_payload = {
            "code": "model_error",
            "message": str(e),
            "retryable": True
        }
        fallback_checks = [
            {
                "check_key": "polybag_sealed",
                "verdict": "UNCERTAIN",
                "confidence": 0.0,
                "detail": f"Model call failed: {str(e)}",
                "uncertain_reason": "model_error"
            }
        ]
        return fallback_checks, MODEL_NAME, 0.0, 0.50, error_payload
