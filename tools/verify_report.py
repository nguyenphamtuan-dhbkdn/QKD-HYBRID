"""Verify the exported report's page count, section rules and navigation targets.

Run with the bundled document Python after tools/render_report.ps1.
This verifies resolved Word bookmarks and PDF destinations, not field codes alone.
"""

from __future__ import annotations

import json
import re
from typing import Any

from build_report_docx import FOOTER_TEXT, HEADER_TEXT, ROOT, digest, verify
from pypdf import PdfReader

RENDER = ROOT / "results/report_build/expanded_render"
PDF = ROOT / "docs/BaoCao_QKD_Hybrid_MoRong.pdf"


def normalize(text: str) -> str:
    """Ignore PDF whitespace while retaining actual caption/heading characters."""
    return " ".join(text.split())


def main() -> None:
    """Fail if page numbering, list entries or any navigation target is wrong."""
    structural = verify()
    audit = json.loads((RENDER / "word_audit.json").read_text(encoding="utf-8-sig"))
    if audit["docx_sha256"] != structural["docx_sha256"]:
        raise ValueError("Word audit belongs to an older DOCX")
    if audit["pdf_sha256"] != digest(PDF):
        raise ValueError("PDF changed since Word navigation was audited")
    reader = PdfReader(PDF)
    pages = len(reader.pages)
    if not 32 <= pages <= 35 or pages != audit["pages"]:
        raise ValueError(f"Expected 32–35 physical pages, got {pages}")
    sections = audit["sections"]
    if len(sections) != 3 or sections[-1]["logical_start"] != 1:
        raise ValueError("Incorrect section structure or numbering restart")
    body_start = sections[-1]["physical_start"]
    texts = [normalize(page.extract_text()) for page in reader.pages]
    for i, text in enumerate(texts):
        if i < body_start - 1:
            if HEADER_TEXT in text or FOOTER_TEXT in text:
                raise ValueError("Header or footer leaked into cover/contents")
        else:
            logical = i - body_start + 2
            if HEADER_TEXT not in text or f"{FOOTER_TEXT} {logical}" not in text:
                raise ValueError(f"Incorrect running header/footer on page {i + 1}")
    if "DANH SÁCH HÌNH ẢNH" not in texts[body_start - 1]:
        raise ValueError("Numbering must start at the figure list")
    lists = audit["navigation"]
    if len(lists) != 3 or [len(x["links"]) for x in lists[1:]] != [10, 5]:
        raise ValueError("Figure or table list is incomplete")
    target_count = 0
    for listing in lists:
        for link in listing["links"]:
            if not link["target_exists"] or not link["anchor"]:
                raise ValueError("Broken internal Word hyperlink")
            match = re.search(r"\s(\d+)\s*$", link["text"])
            if not match or int(match.group(1)) != link["target_page"]:
                raise ValueError("List page number differs from the bookmark page")
            physical = link["target_page"] + body_start - 1
            if normalize(link["target_text"]) not in texts[physical - 1]:
                raise ValueError(
                    "Bookmark target text absent from the expected PDF page"
                )
            target_count += 1
    references = {p.indirect_reference.idnum: i for i, p in enumerate(reader.pages)}
    pdf_links = 0
    for page in reader.pages:
        for pointer in page.get("/Annots", []):
            annotation = pointer.get_object()
            if annotation.get("/Subtype") != "/Link":
                continue
            action = annotation.get("/A", {})
            if hasattr(action, "get_object"):
                action = action.get_object()
            destination = annotation.get("/Dest", action.get("/D"))
            if destination is None:
                continue
            if isinstance(destination, str):
                if destination not in reader.named_destinations:
                    raise ValueError("Unresolved named PDF navigation destination")
            else:
                if destination[0].idnum not in references:
                    raise ValueError("PDF hyperlink points outside the document")
            pdf_links += 1
    if pdf_links < target_count:
        raise ValueError("Some Word navigation links were lost during PDF export")
    result: dict[str, Any] = {
        **structural,
        "physical_pages": pages,
        "unnumbered_front_pages": body_start - 1,
        "first_numbered_physical_page": body_start,
        "last_logical_page": pages - body_start + 1,
        "word_navigation_targets_checked": target_count,
        "contents_links": len(lists[0]["links"]),
        "figure_links": len(lists[1]["links"]),
        "table_links": len(lists[2]["links"]),
        "pdf_internal_links_checked": pdf_links,
        "pdf_sha256": digest(PDF),
    }
    (RENDER / "verification.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
