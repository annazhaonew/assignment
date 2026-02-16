"""
Azure Document Intelligence – parse PDF using prebuilt-layout.
Extracts: text, tables (as HTML), section structure.
Figure images extracted directly from PDF via PyMuPDF (independent of DI).
Saves original content + span data for enriched .md generation after AI run.
"""

import os
import base64
import re
from datetime import datetime
from azure.ai.documentintelligence import DocumentIntelligenceClient
from azure.core.credentials import AzureKeyCredential
from dotenv import load_dotenv

load_dotenv()

ENDPOINT = os.getenv("AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT", "")
KEY = os.getenv("AZURE_DOCUMENT_INTELLIGENCE_KEY", "")

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data")

# ── Image extraction thresholds ──
MIN_IMAGE_WIDTH = 50    # pixels – skip tiny bullets/dots only
MIN_IMAGE_HEIGHT = 50   # pixels – skip tiny bullets/dots only
MIN_IMAGE_BYTES = 2_000  # raw image bytes – skip decorative elements
MAX_ASPECT_RATIO = 12   # skip extremely thin bars/lines (width/height or height/width)


def get_client() -> DocumentIntelligenceClient:
    return DocumentIntelligenceClient(
        endpoint=ENDPOINT, credential=AzureKeyCredential(KEY)
    )


async def parse_pdf(file_bytes: bytes, filename: str = "document.pdf") -> dict:
    import asyncio
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _parse_sync, file_bytes, filename)


def _parse_sync(file_bytes: bytes, filename: str) -> dict:
    client = get_client()
    poller = client.begin_analyze_document(
        "prebuilt-layout",
        analyze_request=file_bytes,
        content_type="application/pdf",
    )
    result = poller.result()

    pages = result.pages if result.pages else []
    page_count = len(pages)

    # ── 1) Original text content (kept pristine for enriched .md later) ──
    original_content = result.content if result.content else ""

    # ── 2) Collect DI figure spans (for OCR noise cleaning only) ──
    all_figure_span_data = []
    figure_char_offsets = set()
    if hasattr(result, "figures") and result.figures:
        for i, fig in enumerate(result.figures):
            caption = ""
            if hasattr(fig, "caption") and fig.caption:
                caption = fig.caption.content
            if hasattr(fig, "spans") and fig.spans:
                for span in fig.spans:
                    all_figure_span_data.append({
                        "offset": span.offset,
                        "length": span.length,
                        "di_index": i,
                        "caption": caption,
                    })
                    for off in range(span.offset, span.offset + span.length):
                        figure_char_offsets.add(off)

    # ── 3) Collect ALL table spans (for enriched .md placement) ──
    all_table_span_data = []
    if result.tables:
        for i, tbl in enumerate(result.tables):
            if hasattr(tbl, "spans") and tbl.spans:
                for span in tbl.spans:
                    all_table_span_data.append({
                        "offset": span.offset,
                        "length": span.length,
                        "table_index": i,
                    })

    # ── 4) Build cleaned text: strip figure OCR noise ──
    if figure_char_offsets:
        cleaned_chars = []
        for i, ch in enumerate(original_content):
            cleaned_chars.append(" " if i in figure_char_offsets else ch)
        cleaned_text = "".join(cleaned_chars)
        cleaned_text = re.sub(r"\n\s*\n\s*\n+", "\n\n", cleaned_text)
        cleaned_text = re.sub(r"\n[ \t]+\n", "\n\n", cleaned_text)
    else:
        cleaned_text = original_content

    # ── 5) Extract tables as HTML + markdown ──
    tables_html = []
    tables_md = []
    if result.tables:
        for i, tbl in enumerate(result.tables):
            tables_html.append(_table_to_html(tbl, i + 1))
            tables_md.append(_table_to_markdown(tbl, i + 1))

    # ── 6) Extract section headings for chunking ──
    sections = []
    if hasattr(result, "paragraphs") and result.paragraphs:
        for p in result.paragraphs:
            if getattr(p, "role", None) == "sectionHeading":
                offset = p.spans[0].offset if hasattr(p, "spans") and p.spans else None
                sections.append({"heading": p.content, "offset": offset})

    # ── 7) Extract ALL images directly from PDF via PyMuPDF ──
    figure_images = _extract_images_pymupdf(file_bytes)

    # ── 8) Tag figure spans with kept_index (not used for image matching anymore) ──
    for fsd in all_figure_span_data:
        fsd["kept_index"] = None  # images are extracted independently now

    # ── 9) Build structured text for LLM (cleaned + tables as markdown) ──
    structured_text = cleaned_text
    if tables_md:
        structured_text += "\n\n" + "=" * 60 + "\n"
        structured_text += "EXTRACTED TABLES (Markdown format)\n"
        structured_text += "=" * 60 + "\n\n"
        structured_text += "\n\n".join(tables_md)

    return {
        "pages": page_count,
        "text": structured_text,
        "original_content": original_content,
        "sections": sections,
        "tables_md": tables_md,
        "tables_html": tables_html,
        "table_spans": all_table_span_data,
        "figure_spans": all_figure_span_data,
        "figure_images": figure_images,
    }


def _extract_images_pymupdf(file_bytes: bytes) -> list[dict]:
    """
    Extract ALL meaningful images from PDF using PyMuPDF.
    Completely independent of Document Intelligence.
    Filters out icons, logos, and decorative elements by size.
    Deduplicates by xref (same image referenced on multiple pages).
    """
    import fitz
    figure_images = []
    seen_xrefs = set()

    try:
        pdf_doc = fitz.open(stream=file_bytes, filetype="pdf")
        print(f"🖼️  PyMuPDF: scanning {len(pdf_doc)} pages for images...")

        for page_num in range(len(pdf_doc)):
            page = pdf_doc[page_num]
            image_list = page.get_images(full=True)

            for img_info in image_list:
                xref = img_info[0]

                # Skip duplicates (same image embedded once, referenced many times)
                if xref in seen_xrefs:
                    continue
                seen_xrefs.add(xref)

                try:
                    base_image = pdf_doc.extract_image(xref)
                    if not base_image:
                        continue

                    img_bytes = base_image["image"]
                    width = base_image.get("width", 0)
                    height = base_image.get("height", 0)
                    ext = base_image.get("ext", "png")

                    # Filter: skip tiny images (icons, logos, bullets)
                    if width < MIN_IMAGE_WIDTH or height < MIN_IMAGE_HEIGHT:
                        print(f"  ⏭️  Skip xref={xref} page {page_num+1}: too small ({width}x{height})")
                        continue

                    if len(img_bytes) < MIN_IMAGE_BYTES:
                        print(f"  ⏭️  Skip xref={xref} page {page_num+1}: too few bytes ({len(img_bytes)})")
                        continue

                    # Filter: skip extremely thin bars/lines/banners
                    aspect = max(width, height) / max(min(width, height), 1)
                    if aspect > MAX_ASPECT_RATIO:
                        print(f"  ⏭️  Skip xref={xref} page {page_num+1}: extreme aspect ratio ({width}x{height}, ratio={aspect:.1f})")
                        continue

                    # Convert to PNG if needed for consistent format
                    if ext != "png":
                        try:
                            pix = fitz.Pixmap(img_bytes)
                            if pix.n > 4:  # CMYK → RGB
                                pix = fitz.Pixmap(fitz.csRGB, pix)
                            img_bytes = pix.tobytes("png")
                        except Exception:
                            # If conversion fails, use original bytes
                            pass

                    img_b64 = base64.b64encode(img_bytes).decode("utf-8")
                    idx = len(figure_images) + 1

                    figure_images.append({
                        "index": idx,
                        "page": page_num + 1,
                        "caption": "",  # PyMuPDF doesn't know captions
                        "image_base64": img_b64,
                        "width": width,
                        "height": height,
                    })
                    print(f"  ✅ Image {idx}: page {page_num+1}, {width}x{height}, {len(img_bytes)} bytes")

                except Exception as e:
                    print(f"  ⚠️ Error extracting xref={xref}: {e}")
                    continue

        pdf_doc.close()
        print(f"🖼️  PyMuPDF: extracted {len(figure_images)} images total")

    except Exception as e:
        print(f"⚠️ PyMuPDF image extraction error: {e}")

    return figure_images


def _table_to_html(table, table_num: int) -> str:
    rows, cols = table.row_count, table.column_count
    grid = [["" for _ in range(cols)] for _ in range(rows)]
    for cell in table.cells:
        r, c = cell.row_index, cell.column_index
        if r < rows and c < cols:
            grid[r][c] = cell.content.replace("\n", " ").strip()
    lines = [f"<h4>Table {table_num}</h4>"]
    lines.append('<table border="1" cellpadding="6" cellspacing="0" style="border-collapse:collapse;">')
    for r_idx, row in enumerate(grid):
        lines.append("  <tr>")
        tag = "th" if r_idx == 0 else "td"
        for v in row:
            lines.append(f"    <{tag}>{v or '&nbsp;'}</{tag}>")
        lines.append("  </tr>")
    lines.append("</table>")
    return "\n".join(lines)


def _table_to_markdown(table, table_num: int) -> str:
    rows, cols = table.row_count, table.column_count
    grid = [["" for _ in range(cols)] for _ in range(rows)]
    for cell in table.cells:
        r, c = cell.row_index, cell.column_index
        if r < rows and c < cols:
            grid[r][c] = cell.content.replace("\n", " ").strip()
    lines = [f"### Table {table_num}"]
    for r_idx, row in enumerate(grid):
        line = "| " + " | ".join(cell or " " for cell in row) + " |"
        lines.append(line)
        if r_idx == 0:
            lines.append("| " + " | ".join("---" for _ in row) + " |")
    return "\n".join(lines)
