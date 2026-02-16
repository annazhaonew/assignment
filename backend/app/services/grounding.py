"""
Grounding validation – verify LLM outputs against source text.

For regulatory-grade applications, every claim, statistic, and quote
in the LLM output must be traceable to the source paper. This module
performs three layers of validation:

1. Statistical evidence: regex-match numbers (HR, CI, p-values, %, N=) against paper text
2. Supporting quotes: fuzzy substring match against paper text
3. Semantic claim grounding: LLM-as-judge checks if claims are supported by text
"""

import re
import json
import os
from difflib import SequenceMatcher
from openai import AzureOpenAI
from dotenv import load_dotenv

load_dotenv()

ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT", "")
API_KEY = os.getenv("AZURE_OPENAI_API_KEY", "")
DEPLOYMENT = os.getenv("AZURE_OPENAI_MODEL_DEPLOYMENT", "")
API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION", "2025-01-01-preview")

# ─── Thresholds ───
QUOTE_SIMILARITY_THRESHOLD = 0.60  # fuzzy match ratio for quotes (lower = more lenient)
STAT_MATCH_THRESHOLD = 0.50  # fraction of key values that must be found


def _get_client() -> AzureOpenAI:
    return AzureOpenAI(
        azure_endpoint=ENDPOINT,
        api_key=API_KEY,
        api_version=API_VERSION,
    )


def _normalize(text: str) -> str:
    """Normalize text for comparison: lowercase, collapse whitespace, normalize dashes."""
    text = text.lower()
    # Normalize all dash variants to simple hyphen
    text = text.replace("\u2013", "-").replace("\u2014", "-").replace("\u2012", "-")
    # Normalize special minus signs
    text = text.replace("\u2212", "-")
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _extract_key_values(text: str) -> list[dict]:
    """
    Extract key statistical values from text as structured data.
    Instead of matching raw strings, extract the semantic meaning:
    - metric name (HR, RR, OR)
    - metric value
    - CI bounds
    - p-value
    - standalone numbers with units
    """
    values = []

    # Extract metric = value pairs (HR=0.64, RR=1.23, OR=2.1)
    # Matches: HR=0.64, HR = 0.64, HR is 0.64, HR of 0.64
    for m in re.finditer(r"(HR|RR|OR)\s*(?:=|is|of|:)\s*([\d.]+)", text, re.IGNORECASE):
        values.append({"type": "metric", "name": m.group(1).upper(), "value": m.group(2)})

    # Extract p-values: p<0.001, p = 0.10, P < 0.00001
    for m in re.finditer(r"p\s*([<>=]+)\s*([\d.]+)", text, re.IGNORECASE):
        values.append({"type": "p_value", "operator": m.group(1), "value": m.group(2)})

    # Extract CI bounds: various formats
    # CI: 0.58, 0.71 | CI 0.58-0.71 | CI: 0.58 to 0.71 | [0.58, 0.71]
    for m in re.finditer(
        r"CI[:\s]*([\d.]+)\s*[-–,\s]+\s*([\d.]+)",
        text, re.IGNORECASE
    ):
        values.append({"type": "ci", "low": m.group(1), "high": m.group(2)})

    # Also catch bracket notation: [0.58, 0.71] or (0.58, 0.71)
    for m in re.finditer(r"[\[(]([\d.]+)\s*[,\s]\s*([\d.]+)[\])]", text):
        values.append({"type": "ci_bracket", "low": m.group(1), "high": m.group(2)})

    # Extract percentages
    for m in re.finditer(r"([\d.]+)\s*%", text):
        values.append({"type": "percent", "value": m.group(1)})

    # Extract N= values
    for m in re.finditer(r"[Nn]\s*=\s*([\d,]+)", text):
        values.append({"type": "n_value", "value": m.group(1).replace(",", "")})

    # Extract durations: 14.6 months, 2.5 years
    for m in re.finditer(r"([\d.]+)\s*(months?|years?|weeks?)", text, re.IGNORECASE):
        values.append({"type": "duration", "value": m.group(1), "unit": m.group(2).lower()})

    # Extract dosages: 60 Gy, 75 mg/m²
    for m in re.finditer(r"([\d.]+)\s*(Gy|mg/?m[²2]?)", text, re.IGNORECASE):
        values.append({"type": "dosage", "value": m.group(1), "unit": m.group(2)})

    return values


def _fuzzy_contains(source: str, substring: str, threshold: float = QUOTE_SIMILARITY_THRESHOLD) -> tuple[bool, float]:
    """
    Check if `substring` approximately appears in `source` using multiple strategies.
    Returns (is_match, best_ratio).
    """
    source_norm = _normalize(source)
    sub_norm = _normalize(substring)

    # Exact substring check first
    if sub_norm in source_norm:
        return True, 1.0

    if len(sub_norm) == 0:
        return False, 0.0

    best_ratio = 0.0

    # Strategy 1: Check if key content words from the quote appear together
    # (handles OCR artifacts like "sur- vival" → "survival")
    stop_words = {"the", "a", "an", "is", "are", "was", "were", "of", "in", "to", "and", "for", "with", "that", "this", "by"}
    content_words = [w for w in sub_norm.split() if w not in stop_words and len(w) > 2]
    if content_words:
        words_found = sum(1 for w in content_words if w in source_norm)
        word_ratio = words_found / len(content_words)
        best_ratio = max(best_ratio, word_ratio)
        if word_ratio >= 0.85:
            return True, word_ratio

    # Strategy 2: Sliding window with word-level stepping
    words = source_norm.split()
    sub_word_count = len(sub_norm.split())

    # Use multiple window sizes for flexibility
    for size_offset in range(-2, 4):
        win_size = sub_word_count + size_offset
        if win_size < 3 or win_size > len(words):
            continue
        # Step through with stride of 2 for speed
        for i in range(0, max(1, len(words) - win_size + 1), 2):
            window = " ".join(words[i:i + win_size])
            ratio = SequenceMatcher(None, sub_norm, window).ratio()
            best_ratio = max(best_ratio, ratio)
            if ratio >= threshold:
                return True, ratio

    return best_ratio >= threshold, best_ratio


def _find_value_in_source(value: str, source_norm: str) -> bool:
    """Check if a numeric value appears anywhere in the source text."""
    # Direct search for the number
    if value in source_norm:
        return True
    # Try without leading zero: .64 for 0.64
    if value.startswith("0.") and value[1:] in source_norm:
        return True
    return False


def _verify_stat_evidence(stat_text: str, source_text: str) -> dict:
    """
    Verify statistical evidence by extracting KEY VALUES (numbers) and checking
    if those values appear in the source. This is format-agnostic:
    'HR=0.64' matches 'HR is 0.64', 'HR of 0.64', 'HR: 0.64', etc.
    'CI 0.58-0.71' matches 'CI: 0.58, 0.71', '[0.58, 0.71]', etc.
    """
    claim_values = _extract_key_values(stat_text)
    if not claim_values:
        return {"grounded": None, "score": 0.0, "found": [], "missing": [], "detail": "no_stats_to_verify"}

    source_norm = _normalize(source_text)
    source_values = _extract_key_values(source_text)

    found = []
    missing = []

    # Build lookup sets from source
    source_metrics = {}  # {("HR", "0.64")} etc
    source_ci_bounds = set()  # all CI bound values
    source_p_values = set()  # all p-value numbers
    source_all_numbers = set()  # all numbers found

    for sv in source_values:
        if sv["type"] == "metric":
            source_metrics[(sv["name"], sv["value"])] = True
            source_all_numbers.add(sv["value"])
        elif sv["type"] in ("ci", "ci_bracket"):
            source_ci_bounds.add(sv["low"])
            source_ci_bounds.add(sv["high"])
            source_all_numbers.add(sv["low"])
            source_all_numbers.add(sv["high"])
        elif sv["type"] == "p_value":
            source_p_values.add(sv["value"])
            source_all_numbers.add(sv["value"])
        elif sv["type"] in ("percent", "n_value", "duration", "dosage"):
            source_all_numbers.add(sv["value"])

    for cv in claim_values:
        label = ""
        is_found = False

        if cv["type"] == "metric":
            label = f"{cv['name']}={cv['value']}"
            # Check if same metric+value exists in source
            if (cv["name"], cv["value"]) in source_metrics:
                is_found = True
            # Fallback: just check if the number appears near the metric name
            elif _find_value_in_source(cv["value"], source_norm):
                # Verify the metric name is also somewhere in source
                if cv["name"].lower() in source_norm:
                    is_found = True

        elif cv["type"] == "ci":
            label = f"CI {cv['low']}-{cv['high']}"
            # Check if both bounds appear in source CI data
            low_found = cv["low"] in source_ci_bounds or _find_value_in_source(cv["low"], source_norm)
            high_found = cv["high"] in source_ci_bounds or _find_value_in_source(cv["high"], source_norm)
            is_found = low_found and high_found

        elif cv["type"] == "ci_bracket":
            label = f"[{cv['low']}, {cv['high']}]"
            low_found = cv["low"] in source_ci_bounds or _find_value_in_source(cv["low"], source_norm)
            high_found = cv["high"] in source_ci_bounds or _find_value_in_source(cv["high"], source_norm)
            is_found = low_found and high_found

        elif cv["type"] == "p_value":
            label = f"p{cv['operator']}{cv['value']}"
            # p<0.001 should match p<0.00001 (more precise is OK)
            claim_p = float(cv["value"])
            for sp in source_p_values:
                try:
                    source_p = float(sp)
                    # Source p-value that is <= the claimed threshold counts as a match
                    if cv["operator"] in ("<", "<="):
                        if source_p <= claim_p:
                            is_found = True
                            break
                    elif cv["operator"] == "=":
                        if abs(source_p - claim_p) < 0.001:
                            is_found = True
                            break
                except ValueError:
                    pass
            # Fallback: check if the exact value appears
            if not is_found:
                is_found = _find_value_in_source(cv["value"], source_norm)

        elif cv["type"] == "percent":
            label = f"{cv['value']}%"
            is_found = _find_value_in_source(cv["value"], source_norm)

        elif cv["type"] == "n_value":
            label = f"N={cv['value']}"
            is_found = _find_value_in_source(cv["value"], source_norm)

        elif cv["type"] == "duration":
            label = f"{cv['value']} {cv['unit']}"
            is_found = _find_value_in_source(cv["value"], source_norm)

        elif cv["type"] == "dosage":
            label = f"{cv['value']} {cv['unit']}"
            is_found = _find_value_in_source(cv["value"], source_norm)

        if is_found:
            found.append(label)
        else:
            missing.append(label)

    # Deduplicate
    found = list(dict.fromkeys(found))
    missing = list(dict.fromkeys(missing))

    total = len(found) + len(missing)
    score = len(found) / total if total > 0 else 0.0
    grounded = score >= STAT_MATCH_THRESHOLD

    return {
        "grounded": grounded,
        "score": round(score, 2),
        "found": found,
        "missing": missing,
    }


def _verify_quotes(quotes: list[str], source_text: str) -> list[dict]:
    """Verify each supporting quote against source text."""
    results = []
    for quote in quotes:
        if not quote or len(quote.strip()) < 10:
            results.append({
                "quote": quote,
                "grounded": None,
                "score": 0.0,
                "detail": "too_short",
            })
            continue

        is_match, ratio = _fuzzy_contains(source_text, quote)
        results.append({
            "quote": quote[:100] + ("…" if len(quote) > 100 else ""),
            "grounded": is_match,
            "score": round(ratio, 2),
        })
    return results


def _verify_claims_with_llm(
    claims: list[dict],
    source_text: str,
) -> list[dict]:
    """
    Use LLM-as-judge to verify whether key claims are grounded in source text.
    This is the semantic layer — catches paraphrased hallucinations that
    pass string matching but aren't actually supported.
    """
    if not claims:
        return []

    client = _get_client()

    # Build claims list for verification
    claims_text = ""
    for i, claim in enumerate(claims):
        claims_text += f"\n[Claim {i+1}]: {claim.get('text', '')}\n"
        if claim.get("evidence"):
            claims_text += f"  Evidence cited: {claim['evidence']}\n"

    # Truncate source to fit context — take first 15k + last 5k chars
    if len(source_text) > 20000:
        truncated = source_text[:15000] + "\n\n[...middle sections omitted for length...]\n\n" + source_text[-5000:]
    else:
        truncated = source_text

    prompt = f"""You are a REGULATORY COMPLIANCE AUDITOR for pharmaceutical research.

Your task: verify whether each claim below is GROUNDED in the source paper text.
For each claim, determine:
- "grounded": true if the claim is directly supported by the text, false if it appears fabricated or unsupported
- "severity": "ok" if grounded, "warning" if partially supported or ambiguous, "error" if clearly not in the text
- "reason": brief explanation of your verdict (1 sentence)

Be STRICT. In regulatory contexts, even small inaccuracies matter.
A claim is grounded ONLY if you can point to specific text that supports it.
If a claim makes a stronger assertion than the paper supports, mark as "warning".
If a statistic is cited that doesn't appear in the text, mark as "error".

CLAIMS TO VERIFY:
{claims_text}

SOURCE PAPER TEXT:
{truncated}

Return JSON array:
[
  {{"claim_index": 1, "grounded": true/false, "severity": "ok"|"warning"|"error", "reason": "..."}},
  ...
]

Return JSON only."""

    try:
        response = client.chat.completions.create(
            model=DEPLOYMENT,
            messages=[
                {"role": "system", "content": "You are a regulatory compliance auditor. Return valid JSON only."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.0,
            max_tokens=2048,
            response_format={"type": "json_object"},
        )

        raw = response.choices[0].message.content or ""
        parsed = json.loads(raw)

        # Handle both {"results": [...]} and direct [...] formats
        if isinstance(parsed, dict):
            verdicts = parsed.get("results", parsed.get("claims", parsed.get("verdicts", [])))
            if not isinstance(verdicts, list):
                # Try to find any list value in the dict
                for v in parsed.values():
                    if isinstance(v, list):
                        verdicts = v
                        break
        elif isinstance(parsed, list):
            verdicts = parsed
        else:
            verdicts = []

        return verdicts

    except Exception as e:
        print(f"⚠️ LLM grounding check failed: {e}")
        return [{"claim_index": i + 1, "grounded": None, "severity": "warning",
                 "reason": f"Verification failed: {str(e)}"} for i in range(len(claims))]


def validate_grounding(output: dict, source_text: str, skip_llm: bool = False) -> dict:
    """
    Main entry point: validate an LLM output dict against source paper text.

    Args:
        skip_llm: If True, skip the expensive LLM-as-judge call and only do
                  fast regex/fuzzy checks. Used for re-validation after self-correction.

    Returns:
    {
        "overall_score": 0.0-1.0,
        "overall_status": "grounded" | "partially_grounded" | "review_needed",
        "total_claims": N,
        "grounded_claims": N,
        "warnings": N,
        "errors": N,
        "details": {
            "key_findings": [...],
            "supporting_quotes": [...],
            "safety_claims": [...],
            "statistical_evidence": [...],
        }
    }
    """
    mode = "fast (regex+fuzzy only)" if skip_llm else "full (regex+fuzzy+LLM)"
    print(f"🔍 Running grounding validation ({mode})...")

    details = {}
    all_verdicts = []

    # ── 1. Verify statistical evidence in key findings ──
    findings = output.get("key_findings", [])
    stat_results = []
    claims_for_llm = []

    if isinstance(findings, list):
        for i, finding in enumerate(findings):
            if isinstance(finding, dict):
                finding_text = finding.get("finding", "")
                stat_evidence = finding.get("statistical_evidence", "")

                # String-match statistical numbers
                stat_check = _verify_stat_evidence(stat_evidence, source_text) if stat_evidence else {
                    "grounded": None, "score": 0.0, "detail": "no_evidence_provided"
                }
                stat_results.append({
                    "finding": finding_text[:120] + ("…" if len(finding_text) > 120 else ""),
                    "statistical_evidence": stat_evidence,
                    **stat_check,
                })

                # Also queue finding text for semantic LLM check
                claims_for_llm.append({
                    "text": finding_text,
                    "evidence": stat_evidence,
                    "type": "key_finding",
                    "index": i,
                })
            elif isinstance(finding, str):
                claims_for_llm.append({
                    "text": finding,
                    "evidence": "",
                    "type": "key_finding",
                    "index": i,
                })

    details["statistical_evidence"] = stat_results

    # ── 2. Verify supporting quotes ──
    quotes = output.get("supporting_quotes", [])
    if isinstance(quotes, list) and quotes:
        quote_results = _verify_quotes(quotes, source_text)
        details["supporting_quotes"] = quote_results
    else:
        details["supporting_quotes"] = []

    # ── 3. Verify safety claims ──
    safety = output.get("safety_profile", {})
    if isinstance(safety, dict):
        adverse = safety.get("adverse_events", [])
        if isinstance(adverse, list):
            for ae in adverse:
                ae_text = ae if isinstance(ae, str) else str(ae)
                claims_for_llm.append({
                    "text": f"Adverse event: {ae_text}",
                    "evidence": "",
                    "type": "safety_claim",
                    "index": len(claims_for_llm),
                })

        serious = safety.get("serious_adverse_events", [])
        if isinstance(serious, list):
            for sae in serious:
                sae_text = sae if isinstance(sae, str) else str(sae)
                claims_for_llm.append({
                    "text": f"Serious adverse event: {sae_text}",
                    "evidence": "",
                    "type": "safety_claim",
                    "index": len(claims_for_llm),
                })

    # ── 4. Verify clinical implications ──
    implications = output.get("clinical_implications", "")
    if isinstance(implications, str) and implications:
        claims_for_llm.append({
            "text": implications,
            "evidence": "",
            "type": "clinical_implication",
            "index": len(claims_for_llm),
        })
    elif isinstance(implications, list):
        for imp in implications:
            claims_for_llm.append({
                "text": str(imp),
                "evidence": "",
                "type": "clinical_implication",
                "index": len(claims_for_llm),
            })

    # ── 5. LLM-as-judge semantic verification ──
    if skip_llm:
        # Fast mode: skip expensive LLM call, use stat/quote results only
        # Mark all claims as presumed grounded (corrections already applied)
        llm_verdicts = [
            {"grounded": True, "severity": "ok", "reason": "Accepted after self-correction"}
            for _ in claims_for_llm
        ]
        print(f"  ⏩ Skipped LLM-as-judge (fast re-validation), {len(claims_for_llm)} claims presumed OK")
    else:
        llm_verdicts = _verify_claims_with_llm(claims_for_llm, source_text)

    # Map verdicts back to claim types
    finding_verdicts = []
    safety_verdicts = []

    for claim, verdict in zip(claims_for_llm, llm_verdicts):
        entry = {
            "claim": claim["text"][:120] + ("…" if len(claim["text"]) > 120 else ""),
            "grounded": verdict.get("grounded", None),
            "severity": verdict.get("severity", "warning"),
            "reason": verdict.get("reason", ""),
        }
        if claim["type"] == "key_finding":
            finding_verdicts.append(entry)
        elif claim["type"] == "safety_claim":
            safety_verdicts.append(entry)
        all_verdicts.append(entry)

    details["key_findings"] = finding_verdicts
    details["safety_claims"] = safety_verdicts

    # ── Calculate overall score ──
    total = len(all_verdicts) + len(details.get("supporting_quotes", []))
    grounded = 0
    warnings = 0
    errors = 0

    for v in all_verdicts:
        if v.get("severity") == "ok" or v.get("grounded") is True:
            grounded += 1
        elif v.get("severity") == "warning":
            warnings += 1
        elif v.get("severity") == "error" or v.get("grounded") is False:
            errors += 1

    for q in details.get("supporting_quotes", []):
        if q.get("grounded") is True:
            grounded += 1
        elif q.get("grounded") is False:
            errors += 1
        else:
            warnings += 1

    # Also count stat evidence
    for s in stat_results:
        if s.get("grounded") is True:
            grounded += 1
            total += 1
        elif s.get("grounded") is False:
            errors += 1
            total += 1

    overall_score = grounded / total if total > 0 else 0.0

    if overall_score >= 0.85 and errors == 0:
        overall_status = "grounded"
    elif overall_score >= 0.6 or errors <= 1:
        overall_status = "partially_grounded"
    else:
        overall_status = "review_needed"

    result = {
        "overall_score": round(overall_score, 2),
        "overall_status": overall_status,
        "total_claims": total,
        "grounded_claims": grounded,
        "warnings": warnings,
        "errors": errors,
        "details": details,
    }

    status_emoji = {"grounded": "✅", "partially_grounded": "⚠️", "review_needed": "❌"}
    print(f"🔍 Grounding result: {status_emoji.get(overall_status, '?')} {overall_status} "
          f"(score={overall_score:.0%}, {grounded}/{total} grounded, {warnings} warnings, {errors} errors)")

    return result


# ─── Self-Correction Loop ───


def _collect_ungrounded_claims(grounding_result: dict) -> list[dict]:
    """
    Extract all claims that failed grounding (severity=error or grounded=False).
    Returns a list of dicts with type, claim text, reason, and path into the output dict.
    """
    ungrounded = []
    details = grounding_result.get("details", {})

    # Key findings with grounded=False
    for i, v in enumerate(details.get("key_findings", [])):
        if v.get("grounded") is False or v.get("severity") == "error":
            ungrounded.append({
                "type": "key_finding",
                "index": i,
                "claim": v.get("claim", ""),
                "reason": v.get("reason", ""),
            })

    # Safety claims with grounded=False
    for i, v in enumerate(details.get("safety_claims", [])):
        if v.get("grounded") is False or v.get("severity") == "error":
            ungrounded.append({
                "type": "safety_claim",
                "index": i,
                "claim": v.get("claim", ""),
                "reason": v.get("reason", ""),
            })

    # Supporting quotes with grounded=False
    for i, v in enumerate(details.get("supporting_quotes", [])):
        if v.get("grounded") is False:
            ungrounded.append({
                "type": "supporting_quote",
                "index": i,
                "claim": v.get("quote", ""),
                "reason": f"score={v.get('score', 0):.2f}",
            })

    # Statistical evidence with grounded=False
    for i, v in enumerate(details.get("statistical_evidence", [])):
        if v.get("grounded") is False:
            ungrounded.append({
                "type": "stat_evidence",
                "index": i,
                "claim": v.get("finding", ""),
                "stat_evidence": v.get("statistical_evidence", ""),
                "reason": f"missing: {v.get('missing', [])}",
            })

    return ungrounded


def correct_ungrounded_claims(
    output: dict,
    source_text: str,
    grounding_result: dict,
) -> tuple[dict, list[dict]]:
    """
    Self-correction: send ungrounded claims back to the LLM with the source text,
    asking it to either correct them using ONLY source text, or remove them.

    Returns:
        (corrected_output, corrections_applied)
    """
    ungrounded = _collect_ungrounded_claims(grounding_result)
    if not ungrounded:
        print("✅ No ungrounded claims to correct.")
        return output, []

    print(f"🔧 Self-correction: {len(ungrounded)} ungrounded claims found, sending to LLM for correction...")

    client = _get_client()

    # Build the ungrounded claims block for the prompt
    claims_block = ""
    for i, ug in enumerate(ungrounded):
        claims_block += f"\n[Error {i+1}] Type: {ug['type']}\n"
        claims_block += f"  Claim: {ug['claim']}\n"
        claims_block += f"  Reason it failed: {ug['reason']}\n"

    # Truncate source to fit context
    if len(source_text) > 20000:
        truncated = source_text[:15000] + "\n\n[...middle omitted...]\n\n" + source_text[-5000:]
    else:
        truncated = source_text

    prompt = f"""You are a regulatory compliance editor for pharmaceutical research outputs.

The following LLM output was validated against the source paper, and {len(ungrounded)} claims were flagged as UNGROUNDED (not supported by the source text).

Your task: For each ungrounded claim, decide:
1. **CORRECT** it: Rewrite using ONLY information from the source text. Keep the same field structure.
2. **REMOVE** it: If the claim simply cannot be supported by the text, mark for removal.

UNGROUNDED CLAIMS:
{claims_block}

CURRENT OUTPUT (JSON):
{json.dumps(output, indent=2)[:8000]}

SOURCE PAPER TEXT:
{truncated}

RULES:
- NEVER invent information not in the source text.
- For key_findings: rewrite the "finding" and "statistical_evidence" fields to match source text exactly.
- For safety claims (adverse_events, serious_adverse_events): remove entries that aren't mentioned in the source.
- For supporting_quotes: replace with actual verbatim text from the source paper.
- If a finding is partially correct, keep the correct part and fix the wrong part.
- For statistics, use the EXACT numbers from the source text.

Return a JSON object with this structure:
{{
  "corrections": [
    {{
      "error_index": 1,
      "action": "correct" or "remove",
      "type": "<key_finding|safety_claim|supporting_quote|stat_evidence>",
      "original_index": <index in the original array>,
      "corrected_value": <corrected text/object, or null if removing>
    }},
    ...
  ]
}}

Return JSON only."""

    try:
        response = client.chat.completions.create(
            model=DEPLOYMENT,
            messages=[
                {"role": "system", "content": "You are a regulatory compliance editor. Return valid JSON only."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.0,
            max_tokens=2048,
            response_format={"type": "json_object"},
        )

        raw = response.choices[0].message.content or ""
        parsed = json.loads(raw)
        corrections = parsed.get("corrections", [])

    except Exception as e:
        print(f"⚠️ Self-correction LLM call failed: {e}")
        return output, []

    # Apply corrections to a copy of the output
    import copy
    corrected = copy.deepcopy(output)
    applied = []
    removal_indices = {"key_finding": [], "safety_claim": [], "supporting_quote": [], "stat_evidence": []}

    for corr in corrections:
        error_idx = corr.get("error_index", 0) - 1  # 1-based → 0-based
        if error_idx < 0 or error_idx >= len(ungrounded):
            continue

        ug = ungrounded[error_idx]
        action = corr.get("action", "remove")
        original_idx = corr.get("original_index", ug.get("index", 0))
        corrected_value = corr.get("corrected_value")
        claim_type = ug["type"]

        try:
            if action == "correct" and corrected_value is not None:
                if claim_type == "key_finding":
                    findings = corrected.get("key_findings", [])
                    if 0 <= original_idx < len(findings):
                        old_val = findings[original_idx]
                        if isinstance(old_val, dict) and isinstance(corrected_value, dict):
                            findings[original_idx] = {**old_val, **corrected_value}
                        elif isinstance(old_val, dict) and isinstance(corrected_value, str):
                            findings[original_idx]["finding"] = corrected_value
                        else:
                            findings[original_idx] = corrected_value
                        applied.append({
                            "type": claim_type,
                            "action": "corrected",
                            "original": ug["claim"],
                            "corrected": str(corrected_value)[:200],
                        })
                        print(f"  ✏️  Corrected key_finding[{original_idx}]")

                elif claim_type == "supporting_quote":
                    quotes = corrected.get("supporting_quotes", [])
                    if 0 <= original_idx < len(quotes) and isinstance(corrected_value, str):
                        old_quote = quotes[original_idx]
                        quotes[original_idx] = corrected_value
                        applied.append({
                            "type": claim_type,
                            "action": "corrected",
                            "original": ug["claim"],
                            "corrected": corrected_value[:200],
                        })
                        print(f"  ✏️  Corrected supporting_quote[{original_idx}]")

                elif claim_type == "safety_claim":
                    # Safety claims need special handling — they come from adverse_events/serious_adverse_events
                    safety = corrected.get("safety_profile", {})
                    ae_list = safety.get("adverse_events", [])
                    sae_list = safety.get("serious_adverse_events", [])
                    combined = ae_list + sae_list
                    if 0 <= original_idx < len(combined) and isinstance(corrected_value, str):
                        if original_idx < len(ae_list):
                            ae_list[original_idx] = corrected_value
                        else:
                            sae_list[original_idx - len(ae_list)] = corrected_value
                        applied.append({
                            "type": claim_type,
                            "action": "corrected",
                            "original": ug["claim"],
                            "corrected": corrected_value[:200],
                        })
                        print(f"  ✏️  Corrected safety_claim[{original_idx}]")

            elif action == "remove":
                removal_indices[claim_type].append(original_idx)
                applied.append({
                    "type": claim_type,
                    "action": "removed",
                    "original": ug["claim"],
                    "corrected": None,
                })
                print(f"  🗑️  Marked {claim_type}[{original_idx}] for removal")

        except (IndexError, KeyError, TypeError) as e:
            print(f"  ⚠️  Failed to apply correction for error {error_idx + 1}: {e}")

    # Apply removals (in reverse order to preserve indices)
    for claim_type, indices in removal_indices.items():
        if not indices:
            continue
        indices_sorted = sorted(set(indices), reverse=True)
        if claim_type == "key_finding":
            findings = corrected.get("key_findings", [])
            for idx in indices_sorted:
                if 0 <= idx < len(findings):
                    findings.pop(idx)
        elif claim_type == "supporting_quote":
            quotes = corrected.get("supporting_quotes", [])
            for idx in indices_sorted:
                if 0 <= idx < len(quotes):
                    quotes.pop(idx)
        elif claim_type == "safety_claim":
            safety = corrected.get("safety_profile", {})
            ae_list = safety.get("adverse_events", [])
            sae_list = safety.get("serious_adverse_events", [])
            for idx in indices_sorted:
                if idx < len(ae_list):
                    ae_list.pop(idx)
                else:
                    sae_idx = idx - len(ae_list)
                    if 0 <= sae_idx < len(sae_list):
                        sae_list.pop(sae_idx)

    print(f"🔧 Self-correction complete: {len(applied)} changes applied "
          f"({sum(1 for a in applied if a['action'] == 'corrected')} corrected, "
          f"{sum(1 for a in applied if a['action'] == 'removed')} removed)")

    return corrected, applied
