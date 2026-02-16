"""
Azure OpenAI – structured JSON output + GPT-4o vision for figure analysis.
Supports section-based chunking for full-paper processing.
"""

import os
import json
from openai import AzureOpenAI
from dotenv import load_dotenv

load_dotenv()

ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT", "")
API_KEY = os.getenv("AZURE_OPENAI_API_KEY", "")
DEPLOYMENT = os.getenv("AZURE_OPENAI_MODEL_DEPLOYMENT", "")
API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION", "2025-01-01-preview")
MAX_CHUNK_CHARS = int(os.getenv("MAX_CHUNK_CHARS", "30000"))


def get_client() -> AzureOpenAI:
    return AzureOpenAI(
        azure_endpoint=ENDPOINT,
        api_key=API_KEY,
        api_version=API_VERSION,
    )


# ─── Figure analysis via GPT-4o vision ───


async def describe_figures(figure_images: list[dict]) -> list[dict]:
    """Send all figure images to GPT-4o vision in parallel."""
    import asyncio

    if not figure_images:
        return []

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _describe_figures_parallel, figure_images)


def _describe_single_figure(client: "AzureOpenAI", fig: dict) -> dict | None:
    """Describe one figure with GPT-4o vision. Returns dict or None if not a figure."""
    caption = fig.get("caption", "")
    b64 = fig.get("image_base64", "")
    if not b64:
        return None

    try:
        response = client.chat.completions.create(
            model=DEPLOYMENT,
            messages=[
                {
                    "role": "system",
                    "content": "You are a biomedical research assistant. Describe the figure/diagram/graph in detail. Include all data points, labels, axes, relationships, and conclusions that can be drawn. Be precise with numbers and terminology. If the image is not a scientific figure (e.g. it is an icon, logo, geometric shape, or decorative element with no data or labels), say exactly: 'NOT_A_FIGURE'.",
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": f"Describe this figure from a scientific paper in detail.{f' Caption: {caption}' if caption else ''}",
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{b64}",
                                "detail": "high",
                            },
                        },
                    ],
                },
            ],
            temperature=0.2,
            max_tokens=1000,
        )
        description = response.choices[0].message.content or ""

        if "NOT_A_FIGURE" in description:
            print(f"  ⏭️  Skipping figure {fig['index']} (page {fig['page']}): GPT-4o says not a figure")
            return None

        print(f"  🖼️  Described figure {fig['index']} (page {fig['page']})")
        return {
            "index": fig["index"],
            "page": fig["page"],
            "caption": caption,
            "description": description,
        }
    except Exception as e:
        print(f"  ⚠️ Failed to describe figure {fig['index']}: {e}")
        return {
            "index": fig["index"],
            "page": fig["page"],
            "caption": caption,
            "description": f"[Figure analysis failed: {str(e)}]",
        }


def _describe_figures_parallel(figure_images: list[dict]) -> list[dict]:
    """Describe all figures in parallel using a thread pool."""
    from concurrent.futures import ThreadPoolExecutor, as_completed
    import time

    client = get_client()
    results = []
    start = time.time()

    # Run all vision calls in parallel (max 6 concurrent to respect rate limits)
    with ThreadPoolExecutor(max_workers=6) as executor:
        futures = {
            executor.submit(_describe_single_figure, client, fig): fig["index"]
            for fig in figure_images
        }
        for future in as_completed(futures):
            result = future.result()
            if result is not None:
                results.append(result)

    # Sort by index to maintain order
    results.sort(key=lambda r: r["index"])
    elapsed = time.time() - start
    print(f"  ⚡ {len(results)} figures described in {elapsed:.1f}s (parallel)")
    return results


# ─── Figure-to-paper matching ───

import re

def _match_figures_to_paper(text: str, figure_descriptions: list[dict]) -> list[dict]:
    """
    Match extracted images to the paper's own figure numbers using page proximity
    AND content similarity between the GPT-4o vision description and the paper's
    figure captions.
    """
    if not figure_descriptions:
        return []

    # Find all figure references in text with their character offset and caption
    fig_refs = []
    for m in re.finditer(
        r'(?:Fig\.?\s*|Figure\s*)(\d+)\s*[.:\s]([^\n]{0,200})',
        text, re.IGNORECASE
    ):
        fig_num = int(m.group(1))
        caption_snippet = m.group(2).strip()
        offset = m.start()
        fig_refs.append({
            "fig_num": fig_num,
            "caption": caption_snippet,
            "offset": offset,
        })

    # Deduplicate: keep the first (usually caption) occurrence per figure number
    seen_nums = set()
    unique_refs = []
    for ref in fig_refs:
        if ref["fig_num"] not in seen_nums:
            seen_nums.add(ref["fig_num"])
            unique_refs.append(ref)

    if not unique_refs:
        return [
            {"label": f"Image from Page {fd['page']}", "page": fd["page"],
             "description": fd["description"]}
            for fd in figure_descriptions
        ]

    # ── Strategy: figure numbers are sequential, images are in page order ──
    # In academic papers, Fig 1 is always the first figure, Fig 2 the second, etc.
    # Images extracted by PyMuPDF are already in page order.
    # So the simplest and most reliable matching: sort both by their natural order
    # and pair them 1:1. Fall back to content similarity only when counts differ.

    sorted_images = sorted(figure_descriptions, key=lambda x: (x["page"], x.get("index", 0)))
    sorted_refs = sorted(unique_refs, key=lambda x: x["fig_num"])

    # If counts match exactly, direct sequential pairing is the most reliable
    if len(sorted_images) == len(sorted_refs):
        matched = []
        for img, ref in zip(sorted_images, sorted_refs):
            label = f"Fig. {ref['fig_num']}"
            matched.append({
                "label": label,
                "page": img["page"],
                "description": img["description"],
            })
            print(f"  🔗 Matched image (page {img['page']}) → {label} "
                  f"(caption: {ref['caption'][:50]})")
        return matched

    # Counts differ → use greedy content-similarity matching
    print(f"  ⚠️  Image count ({len(sorted_images)}) ≠ figure refs ({len(sorted_refs)}), "
          f"using content-similarity matching")

    # Estimate page for each figure reference using character offset ratio
    total_len = max(len(text), 1)
    max_page = max(fd["page"] for fd in figure_descriptions) if figure_descriptions else 8
    for ref in unique_refs:
        ref["est_page"] = max(1, round((ref["offset"] / total_len) * max_page))

    def _match_score(img: dict, ref: dict) -> float:
        """Score how well an image matches a figure reference. Higher = better."""
        score = 0.0

        # Page proximity: 0 distance = 1.0, 1 page away = 0.5, 2+ = 0.1
        page_dist = abs(img["page"] - ref["est_page"])
        if page_dist == 0:
            score += 3.0
        elif page_dist == 1:
            score += 1.5
        else:
            score += 0.1

        # Content similarity: compare GPT-4o description vs paper caption
        desc_lower = img.get("description", "").lower()
        caption_lower = ref.get("caption", "").lower()

        # Extract key terms from caption for matching
        caption_terms = set(re.findall(r'\b\w{4,}\b', caption_lower))
        desc_terms = set(re.findall(r'\b\w{4,}\b', desc_lower))
        if caption_terms:
            overlap = len(caption_terms & desc_terms)
            score += overlap * 0.5

        # Bonus for specific matches
        specific_keywords = {
            "prisma": 2.0, "flowchart": 1.5, "flow diagram": 1.5,
            "forest plot": 1.5, "funnel plot": 1.0,
            "overall survival": 2.0, "progression": 2.0,
            "toxicit": 2.0, "hematolog": 2.0,
            "bias": 2.0, "cochrane": 1.5, "risk of bias": 2.0,
        }
        for keyword, bonus in specific_keywords.items():
            if keyword in caption_lower and keyword in desc_lower:
                score += bonus

        return score

    # Greedy best-match assignment: for each image, find best unmatched ref
    matched = []
    used_refs = set()
    used_images = set()

    # Build score matrix
    scores = []
    for i, img in enumerate(sorted_images):
        for j, ref in enumerate(sorted_refs):
            scores.append((i, j, _match_score(img, ref)))

    # Sort by score descending, greedily assign best pairs
    scores.sort(key=lambda x: -x[2])

    assignments = {}  # image_idx -> ref_idx
    for i, j, score in scores:
        if i not in used_images and j not in used_refs:
            assignments[i] = j
            used_images.add(i)
            used_refs.add(j)

    # Build result in image order
    for i, img in enumerate(sorted_images):
        if i in assignments:
            ref = sorted_refs[assignments[i]]
            label = f"Fig. {ref['fig_num']}"
            matched.append({
                "label": label,
                "page": img["page"],
                "description": img["description"],
            })
            print(f"  🔗 Matched image (page {img['page']}) → {label} (caption: {ref['caption'][:50]})")
        else:
            matched.append({
                "label": f"Image from Page {img['page']}",
                "page": img["page"],
                "description": img["description"],
            })
            print(f"  ❓ Unmatched image (page {img['page']})")

    return matched


# ─── Section-based chunking ───


def split_into_sections(text: str, sections: list[dict]) -> list[dict]:
    """
    Split text by section headings from Document Intelligence.
    Returns list of {heading, content} chunks.
    """
    if not sections or len(sections) < 2:
        # No section info → chunk by character limit
        return _chunk_by_size(text)

    # Sort sections by offset
    sorted_sections = sorted(
        [s for s in sections if s.get("offset") is not None],
        key=lambda s: s["offset"],
    )

    if not sorted_sections:
        return _chunk_by_size(text)

    chunks = []

    # Text before first section
    first_offset = sorted_sections[0]["offset"]
    if first_offset > 0:
        preamble = text[:first_offset].strip()
        if preamble:
            chunks.append({"heading": "Preamble / Title", "content": preamble})

    # Each section
    for i, sec in enumerate(sorted_sections):
        start = sec["offset"]
        end = sorted_sections[i + 1]["offset"] if i + 1 < len(sorted_sections) else len(text)
        content = text[start:end].strip()
        if content:
            chunks.append({"heading": sec["heading"], "content": content})

    # Merge small chunks to avoid too many LLM calls
    merged = _merge_small_chunks(chunks, MAX_CHUNK_CHARS)
    return merged


def _chunk_by_size(text: str) -> list[dict]:
    """Fallback: split text into chunks by character count."""
    chunks = []
    for i in range(0, len(text), MAX_CHUNK_CHARS):
        chunk_text = text[i : i + MAX_CHUNK_CHARS]
        chunks.append({
            "heading": f"Part {len(chunks) + 1}",
            "content": chunk_text,
        })
    return chunks


def _merge_small_chunks(chunks: list[dict], max_size: int) -> list[dict]:
    """Merge consecutive small chunks to reduce LLM calls."""
    merged = []
    buffer_heading = ""
    buffer_content = ""

    for chunk in chunks:
        if len(buffer_content) + len(chunk["content"]) < max_size:
            if buffer_heading:
                buffer_heading += " + " + chunk["heading"]
            else:
                buffer_heading = chunk["heading"]
            buffer_content += "\n\n" + chunk["content"]
        else:
            if buffer_content:
                merged.append({"heading": buffer_heading, "content": buffer_content.strip()})
            buffer_heading = chunk["heading"]
            buffer_content = chunk["content"]

    if buffer_content:
        merged.append({"heading": buffer_heading, "content": buffer_content.strip()})

    return merged


# ─── Main generation with chunking + synthesis ───


async def generate_structured_output(
    prompt_template: str,
    schema_json: str,
    text: str,
    sections: list[dict] | None = None,
    figure_descriptions: list[dict] | None = None,
) -> dict:
    """
    Process full paper text through section-based chunking:
    1. Append figure descriptions to text
    2. Split into sections
    3. Process each chunk with LLM
    4. Synthesize final output
    """
    import asyncio

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None, _generate_with_chunking, prompt_template, schema_json, text,
        sections or [], figure_descriptions or []
    )


def _generate_with_chunking(
    prompt_template: str,
    schema_json: str,
    text: str,
    sections: list[dict],
    figure_descriptions: list[dict],
) -> dict:
    # Match extracted images to the paper's own figure numbers by page
    matched_fds = _match_figures_to_paper(text, figure_descriptions)

    # Enrich text with figure descriptions
    enriched_text = text
    if matched_fds:
        enriched_text += "\n\n" + "=" * 60 + "\n"
        enriched_text += "AI VISION ANALYSIS OF FIGURES IN THIS PAPER\n"
        enriched_text += "=" * 60 + "\n\n"
        for mfd in matched_fds:
            enriched_text += f"### {mfd['label']} (PDF Page {mfd['page']})\n"
            enriched_text += f"Description: {mfd['description']}\n\n"

    # Split into chunks
    chunks = split_into_sections(enriched_text, sections)
    print(f"📊 Processing {len(chunks)} section chunk(s)")

    client = get_client()

    if len(chunks) == 1:
        # Single chunk → direct processing (no synthesis needed)
        result = _process_single_chunk(
            client, prompt_template, schema_json, chunks[0]["content"]
        )
        return result

    # Multiple chunks → process each in parallel, then synthesize
    from concurrent.futures import ThreadPoolExecutor, as_completed
    import time

    chunk_outputs = []
    start = time.time()
    print(f"  📄 Processing {len(chunks)} chunks in parallel...")

    def _process_chunk_wrapper(i, chunk):
        print(f"  📄 Chunk {i+1}/{len(chunks)}: {chunk['heading'][:50]}...")
        return i, _process_single_chunk(
            client, prompt_template, schema_json, chunk["content"],
            chunk_context=f"This is section '{chunk['heading']}' (part {i+1} of {len(chunks)} from the full paper)."
        )

    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(_process_chunk_wrapper, i, chunk) for i, chunk in enumerate(chunks)]
        for future in as_completed(futures):
            i, chunk_result = future.result()
            if chunk_result["parsed"]:
                chunk_outputs.append({
                    "section": chunks[i]["heading"],
                    "output": chunk_result["parsed"],
                })

    # Sort by original chunk order
    chunk_outputs.sort(key=lambda c: next(
        (i for i, ch in enumerate(chunks) if ch["heading"] == c["section"]), 0
    ))
    elapsed = time.time() - start
    print(f"  ⚡ {len(chunk_outputs)} chunks processed in {elapsed:.1f}s (parallel)")

    # Synthesize all chunk outputs into final result
    print(f"  🔄 Synthesizing {len(chunk_outputs)} chunk outputs...")
    final = _synthesize_outputs(client, schema_json, chunk_outputs)
    return final


def _process_single_chunk(
    client: AzureOpenAI,
    prompt_template: str,
    schema_json: str,
    text: str,
    chunk_context: str = "",
) -> dict:
    """Process a single text chunk through the LLM."""
    user_message = prompt_template.replace("{schema_json}", schema_json).replace(
        "{text}", text
    )
    if chunk_context:
        user_message = chunk_context + "\n\n" + user_message

    response = client.chat.completions.create(
        model=DEPLOYMENT,
        messages=[
            {
                "role": "system",
                "content": "You are an R&D assistant for biomedical researchers. Return valid JSON only.",
            },
            {"role": "user", "content": user_message},
        ],
        temperature=0.2,
        max_tokens=4096,
        response_format={"type": "json_object"},
    )

    raw = response.choices[0].message.content or ""
    from app.utils.json_safe import safe_parse_json
    parsed = safe_parse_json(raw)

    return {"parsed": parsed, "raw": raw}


def _synthesize_outputs(
    client: AzureOpenAI,
    schema_json: str,
    chunk_outputs: list[dict],
) -> dict:
    """Merge multiple chunk outputs into a single coherent result."""
    synthesis_prompt = f"""You are given multiple partial analyses of different sections of the same scientific paper.
Merge them into ONE final comprehensive JSON output using the exact schema below.

Rules:
- Combine all key_findings, biomarkers, patient_population, follow_up_hypotheses, and supporting_quotes from all sections.
- Remove duplicates but keep all unique information.
- Write a single cohesive tldr that covers the entire paper.
- For trial_phase_signals: use the most specific phase mentioned across all sections.
- For confidence: use the overall confidence level considering all evidence.
- supporting_quotes: select the 4-6 most impactful quotes across all sections.
- **CRITICAL**: For figures_and_tables_summary, use the paper's OWN figure and table numbering (e.g. Figure 1, Figure 2, Table 1) — NOT extraction image numbers. Include EVERY figure and table referenced in the paper text. Do NOT invent figure/table numbers that don't exist in the paper.
- Return JSON only (no markdown).

SCHEMA:
{schema_json}

PARTIAL ANALYSES:
{json.dumps(chunk_outputs, indent=2)}"""

    response = client.chat.completions.create(
        model=DEPLOYMENT,
        messages=[
            {
                "role": "system",
                "content": "You are an R&D assistant for biomedical researchers. Return valid JSON only.",
            },
            {"role": "user", "content": synthesis_prompt},
        ],
        temperature=0.2,
        max_tokens=4096,
        response_format={"type": "json_object"},
    )

    raw = response.choices[0].message.content or ""
    from app.utils.json_safe import safe_parse_json
    parsed = safe_parse_json(raw)

    return {"parsed": parsed, "raw": raw}
