"""
Enriched Markdown builder.

Takes the ORIGINAL result.content from Document Intelligence, plus:
  - table_spans  → inline HTML tables at their original positions
  - figure_spans → inline AI-generated figure descriptions where figures appear
  - tables_html  → pre-built HTML for each table
  - figure_descriptions → GPT-4o vision descriptions for kept figures

Produces a single, rich .md file that serves as the digitised deliverable.
"""

from __future__ import annotations

import os
import re
from datetime import datetime

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data")


def build_enriched_markdown(
    original_content: str,
    table_spans: list[dict],
    tables_html: list[str],
    figure_spans: list[dict],
    figure_descriptions: list[dict],
    filename: str = "document.pdf",
) -> str:
    """
    Build a fully enriched Markdown document:
    - Tables rendered as HTML inline where they appeared in the original PDF
    - Figures replaced with AI-generated descriptions (or a placeholder)
    """
    # ── Map figure descriptions by kept_index ──
    fig_desc_by_kept = {}
    for fd in figure_descriptions:
        fig_desc_by_kept[fd["index"]] = fd

    # ── Collect replacement regions ──
    # Each entry: (offset, length, replacement_text)
    replacements: list[tuple[int, int, str]] = []

    # Tables: group spans by table_index, use the earliest offset
    table_groups: dict[int, list[dict]] = {}
    for ts in table_spans:
        idx = ts["table_index"]
        table_groups.setdefault(idx, []).append(ts)

    for table_idx, spans in table_groups.items():
        if table_idx >= len(tables_html):
            continue
        # Use the full range covered by all spans of this table
        min_offset = min(s["offset"] for s in spans)
        max_end = max(s["offset"] + s["length"] for s in spans)
        total_length = max_end - min_offset
        html = tables_html[table_idx]
        replacements.append((min_offset, total_length, f"\n\n{html}\n\n"))

    # Figures: group spans by di_index
    figure_groups: dict[int, list[dict]] = {}
    for fs in figure_spans:
        di_idx = fs["di_index"]
        figure_groups.setdefault(di_idx, []).append(fs)

    for di_idx, spans in figure_groups.items():
        min_offset = min(s["offset"] for s in spans)
        max_end = max(s["offset"] + s["length"] for s in spans)
        total_length = max_end - min_offset

        # Check if this figure was kept (sent to GPT-4o vision)
        kept_index = spans[0].get("kept_index")
        caption = spans[0].get("caption", "")

        if kept_index and kept_index in fig_desc_by_kept:
            desc = fig_desc_by_kept[kept_index]
            label = caption or f"Figure {kept_index}"
            page = desc.get("page", "?")
            description = desc.get("description", "")
            block = (
                f"\n\n---\n\n"
                f"> 🖼️ **{label}** *(Page {page})*\n>\n"
                f"> {description}\n"
                f"\n---\n\n"
            )
            replacements.append((min_offset, total_length, block))
        elif caption:
            # Figure detected but too small / not analysed — insert caption only
            replacements.append((
                min_offset,
                total_length,
                f"\n\n> 🖼️ *{caption}* *(decorative / small image — not analysed)*\n\n",
            ))
        else:
            # Unknown small figure — just remove the OCR noise
            replacements.append((min_offset, total_length, "\n\n"))

    # ── Sort descending by offset so replacements don't shift positions ──
    replacements.sort(key=lambda r: r[0], reverse=True)

    # ── Handle overlaps: if a later replacement overlaps an earlier one, skip it ──
    filtered: list[tuple[int, int, str]] = []
    occupied_until = len(original_content)  # track the start of the first accepted region
    for offset, length, text in replacements:
        end = offset + length
        if end <= occupied_until:
            filtered.append((offset, length, text))
            occupied_until = offset
        # else: this region overlaps with an already-accepted one → skip

    # ── Apply replacements ──
    enriched = original_content
    for offset, length, text in filtered:
        enriched = enriched[:offset] + text + enriched[offset + length:]

    # ── Clean up excessive whitespace left over ──
    enriched = re.sub(r"\n{4,}", "\n\n\n", enriched)

    # ── Build final document ──
    clean_name = filename.replace(".pdf", "").replace(".PDF", "")
    header = (
        f"# {clean_name}\n\n"
        f"_Enriched document — tables as HTML, figures described by AI_  \n"
        f"_Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}_\n\n"
        f"---\n\n"
    )

    return header + enriched


def save_enriched_markdown(content: str, run_id: str) -> str:
    """Save the enriched .md to data/runs/{run_id}_enriched.md and return the path."""
    runs_dir = os.path.join(DATA_DIR, "runs")
    os.makedirs(runs_dir, exist_ok=True)
    path = os.path.join(runs_dir, f"{run_id}_enriched.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"📄 Saved enriched .md: {path}")
    return path
