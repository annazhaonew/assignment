"""
Workflow runner – orchestrates Doc Intelligence → Azure OpenAI pipeline.
Supports figure vision analysis and section-based chunking.
Caches figure descriptions per document to avoid re-analysing on subsequent runs.
Includes grounding validation with self-correction loop for regulatory compliance.
"""

import os
import json

from app.services.aoai import generate_structured_output, describe_figures
from app.services.grounding import validate_grounding, correct_ungrounded_claims

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data")
FIG_CACHE_DIR = os.path.join(DATA_DIR, "figure_descriptions")

MAX_CORRECTION_ROUNDS = 1  # Max self-correction attempts before giving up


def _load_cached_descriptions(doc_id: str) -> list[dict] | None:
    """Return cached figure descriptions for doc_id, or None if not cached."""
    path = os.path.join(FIG_CACHE_DIR, f"{doc_id}.json")
    if os.path.exists(path):
        with open(path, "r") as f:
            return json.load(f)
    return None


def _save_cached_descriptions(doc_id: str, descriptions: list[dict]) -> None:
    os.makedirs(FIG_CACHE_DIR, exist_ok=True)
    path = os.path.join(FIG_CACHE_DIR, f"{doc_id}.json")
    with open(path, "w") as f:
        json.dump(descriptions, f, indent=2)


async def run_workflow(
    prompt_template: str,
    output_schema_json: str,
    input_text: str,
    sections: list[dict] | None = None,
    figure_images: list[dict] | None = None,
    doc_id: str | None = None,
) -> dict:
    """
    Execute a workflow:
    1. (Optional) Analyse figure images with GPT-4o vision (cached per doc)
    2. Send text through LLM with section-based chunking
    3. Synthesise final structured output
    """
    # Step 1: Describe figures — use cache if available
    figure_descriptions = []
    if figure_images:
        if doc_id:
            cached = _load_cached_descriptions(doc_id)
            if cached is not None:
                figure_descriptions = cached
                print(f"⚡ Loaded {len(cached)} cached figure descriptions for doc {doc_id[:8]}")

        if not figure_descriptions:
            print(f"🖼️  Analysing {len(figure_images)} figures with GPT-4o vision (parallel)...")
            figure_descriptions = await describe_figures(figure_images)
            if doc_id:
                _save_cached_descriptions(doc_id, figure_descriptions)
                print(f"💾 Cached {len(figure_descriptions)} figure descriptions for doc {doc_id[:8]}")

    # Step 2: Generate structured output with chunking
    result = await generate_structured_output(
        prompt_template=prompt_template,
        schema_json=output_schema_json,
        text=input_text,
        sections=sections,
        figure_descriptions=figure_descriptions,
    )

    result["figure_descriptions"] = figure_descriptions

    # Step 3: Grounding validation with self-correction loop
    if result.get("parsed") and isinstance(result["parsed"], dict):
        print("🔍 Starting grounding validation...")
        grounding_result = validate_grounding(result["parsed"], input_text)
        all_corrections = []

        # Self-correction loop: if there are errors, try to fix them
        correction_round = 0
        while (
            grounding_result.get("errors", 0) > 0
            and correction_round < MAX_CORRECTION_ROUNDS
        ):
            correction_round += 1
            print(f"\n🔄 Self-correction round {correction_round}/{MAX_CORRECTION_ROUNDS}...")

            corrected_output, corrections_applied = correct_ungrounded_claims(
                result["parsed"], input_text, grounding_result
            )

            if not corrections_applied:
                print("  ⏸️  No corrections could be applied, stopping.")
                break

            all_corrections.extend(corrections_applied)
            result["parsed"] = corrected_output

            # Re-validate the corrected output (fast mode — skip LLM-as-judge)
            print("🔍 Re-validating corrected output (fast)...")
            grounding_result = validate_grounding(corrected_output, input_text, skip_llm=True)

        # Attach correction metadata
        if all_corrections:
            grounding_result["corrections_applied"] = all_corrections
            grounding_result["correction_rounds"] = correction_round
            print(f"\n✅ Self-correction complete after {correction_round} round(s): "
                  f"{len(all_corrections)} total changes")
        else:
            grounding_result["corrections_applied"] = []
            grounding_result["correction_rounds"] = 0

        result["grounding"] = grounding_result
    else:
        result["grounding"] = None

    return result
