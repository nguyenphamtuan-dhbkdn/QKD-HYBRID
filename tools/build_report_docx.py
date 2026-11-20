"""Build the Vietnamese QKD report exclusively from retained experiment evidence.

Windows: uv run --with python-docx==1.2.0 python tools/build_report_docx.py
No experiment is launched. Rebuilds use sorted inputs and a fixed package timestamp;
the manifest records SHA-256 input digests and the actual authoring environment.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import platform
import re
import subprocess
import textwrap
import tomllib
import xml.etree.ElementTree as ET
from collections.abc import Iterable, Sequence
from dataclasses import fields, is_dataclass
from datetime import datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from docx import Document
from docx.enum.section import WD_SECTION_START
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor
from matplotlib import font_manager
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

from qkdsim.config import SessionConfig

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs/BaoCao_QKD_Hybrid.docx"
DIAGRAMS = ROOT / "docs/report_diagrams"
MANIFEST = ROOT / "docs/report_build_manifest.json"
VALIDATION = ROOT / "results/report_build"
Row = dict[str, str]


def read_json(path: Path) -> Any:
    """Read retained UTF-8 evidence without modifying the source."""
    return json.loads(path.read_text(encoding="utf-8-sig"))


def read_csv(path: Path) -> list[Row]:
    """Read every record; empty optional numeric cells remain missing."""
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def rel(path: Path) -> str:
    """Return a stable repository-relative path for provenance."""
    return path.relative_to(ROOT).as_posix()


def digest(path: Path) -> str:
    """Compute SHA-256(file bytes), never a key fingerprint."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fmt(value: object) -> str:
    """Preserve missingness and display measured numbers to six digits."""
    if value is None or value == "":
        return "—"
    if isinstance(value, bool):
        return "Có" if value else "Không"
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("Nonfinite evidence value")
        return f"{value:.6g}"
    if isinstance(value, str):
        if re.fullmatch(r"[-+]?\d+", value):
            return value
        try:
            return fmt(float(value)) if re.fullmatch(r"[-+\d.eE]+", value) else value
        except ValueError:
            return value
    return str(value)


def installed() -> dict[str, str]:
    """Read actual package metadata, separating it from historical run versions."""
    names = (
        "numpy",
        "scipy",
        "qiskit",
        "qiskit-aer",
        "cryptography",
        "matplotlib",
        "PyYAML",
        "typer",
        "rich",
        "pytest",
        "pytest-cov",
        "hypothesis",
        "ruff",
        "mypy",
        "python-docx",
    )
    result = {}
    for name in names:
        try:
            result[name] = version(name)
        except PackageNotFoundError:
            result[name] = "Không cài trong môi trường dựng"
    return result


def git_info() -> dict[str, object]:
    """Record source revision plus dirty status without changing Git state."""
    return {
        "commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "dirty": bool(
            subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT)
        ),
    }


def inventory() -> list[dict[str, object]]:
    """Parse all CSV/JSON/JSONL evidence and hash all retained plot inputs."""
    result = []
    for path in sorted((ROOT / "results").rglob("*")):
        if not path.is_file() or VALIDATION in path.parents:
            continue
        if path.suffix not in (".csv", ".json", ".jsonl", ".png"):
            continue
        item: dict[str, object] = {"path": rel(path), "sha256": digest(path)}
        if path.suffix == ".csv":
            item["records"] = len(read_csv(path))
        elif path.suffix == ".json":
            read_json(path)
        elif path.suffix == ".jsonl":
            item["records"] = len(
                [
                    json.loads(line)
                    for line in path.read_text(encoding="utf-8").splitlines()
                    if line.strip()
                ]
            )
        result.append(item)
    return result


def bibliography() -> list[dict[str, str]]:
    """Parse braced BibTeX fields, retaining nested title and author braces."""
    text = (ROOT / "docs/references.bib").read_text(encoding="utf-8-sig")
    entries = []
    for start in re.finditer(r"@\w+\s*\{([^,]+),", text):
        pos, depth = start.end(), 1
        end = pos
        while depth and end < len(text):
            depth += (text[end] == "{") - (text[end] == "}")
            end += 1
        body = text[pos : end - 1]
        entry = {"key": start.group(1).strip()}
        cursor = 0
        while match := re.search(r"(\w+)\s*=\s*\{", body[cursor:]):
            name = match.group(1)
            begin = cursor + match.end()
            stop, level = begin, 1
            while level and stop < len(body):
                level += (body[stop] == "{") - (body[stop] == "}")
                stop += 1
            entry[name] = body[begin : stop - 1].replace("{", "").replace("}", "")
            cursor = stop
        entries.append(entry)
    if len({entry["key"] for entry in entries}) != len(entries):
        raise ValueError("Duplicate bibliography key")
    return entries


def xml(tag: str, **attributes: object) -> Any:
    """Construct a namespace-qualified WordprocessingML property."""
    element = OxmlElement(tag)
    for key, value in attributes.items():
        element.set(qn(f"w:{key}"), str(value))
    return element


def field(paragraph: Any, instruction: str, cache: str = "") -> None:
    """Insert a live Word field with a deterministic readable cached value."""
    run = paragraph.add_run()
    run._r.append(xml("w:fldChar", fldCharType="begin"))
    code = xml("w:instrText")
    code.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    code.text = f" {instruction} "
    run._r.append(code)
    run._r.append(xml("w:fldChar", fldCharType="separate"))
    if cache:
        paragraph.add_run(cache)
    paragraph.add_run()._r.append(xml("w:fldChar", fldCharType="end"))


def diagram(name: str, labels: list[str], *, branch: str | None = None) -> Path:
    """Draw a directed processing graph at 300 DPI using Vietnamese fonts."""
    DIAGRAMS.mkdir(parents=True, exist_ok=True)
    candidates = [
        Path("C:/Windows/Fonts/arial.ttf"),
        Path("C:/Windows/Fonts/segoeui.ttf"),
    ]
    font = next((path for path in candidates if path.exists()), None)
    if font:
        font_manager.fontManager.addfont(str(font))
    plt.rcParams["font.family"] = (
        font_manager.FontProperties(fname=str(font)).get_name()
        if font
        else "DejaVu Sans"
    )
    count = len(labels)
    fig, ax = plt.subplots(figsize=(8.8, count * 0.66 + 0.35))
    ax.set_xlim(0, 10)
    ax.set_ylim(-0.3, count)
    ax.axis("off")
    center, width = (3.9, 6.4) if branch else (5, 8)
    for index, label in enumerate(labels):
        y = count - index - 0.65
        box = FancyBboxPatch(
            (center - width / 2, y - 0.27),
            width,
            0.54,
            boxstyle="round,pad=0.015,rounding_size=0.055",
            facecolor="#EEF2F6",
            edgecolor="#5A6B7C",
            linewidth=0.8,
        )
        ax.add_patch(box)
        ax.text(center, y, label, ha="center", va="center", fontsize=10.7)
        if index:
            ax.add_patch(
                FancyArrowPatch(
                    (center, y + 0.71),
                    (center, y + 0.29),
                    arrowstyle="-|>",
                    mutation_scale=10,
                    linewidth=0.8,
                    color="#5A6B7C",
                )
            )
    if branch:
        y = count / 2 - 0.45
        box = FancyBboxPatch(
            (7.65, y - 0.65),
            2.15,
            1.3,
            boxstyle="round,pad=0.025,rounding_size=0.05",
            facecolor="#EEF2F6",
            edgecolor="#5A6B7C",
            linewidth=0.8,
        )
        ax.add_patch(box)
        ax.text(
            8.72, y, textwrap.fill(branch, 20), ha="center", va="center", fontsize=10
        )
        ax.add_patch(
            FancyArrowPatch(
                (7.13, y),
                (7.62, y),
                arrowstyle="-|>",
                mutation_scale=10,
                linewidth=0.8,
                color="#5A6B7C",
            )
        )
    path = DIAGRAMS / f"{name}.png"
    fig.savefig(path, dpi=300, bbox_inches="tight", pad_inches=0.10, facecolor="white")
    plt.close(fig)
    return path


class Report:
    """Compose a three-chapter report with matching caption registries."""

    def __init__(self) -> None:
        self.doc = Document()
        self.tables: list[str] = []
        self.figures: list[str] = []
        self.headings: list[tuple[int, str]] = []
        self.figure_sources: list[str] = []
        self.table_sources: list[str] = []
        self.list_tables: Any = None
        self.list_figures: Any = None
        self.refs = bibliography()
        self.ref_ids = {
            entry["key"]: index + 1 for index, entry in enumerate(self.refs)
        }
        self.setup()

    def cite(self, *keys: str) -> str:
        """Resolve stable numeric citations from the actual BibTeX order."""
        return ", ".join(f"[{self.ref_ids[key]}]" for key in keys)

    def setup(self) -> None:
        """Apply A4, 3/2/2/2 cm margins and the faculty typography."""
        section = self.doc.sections[0]
        section.page_width, section.page_height = Cm(21), Cm(29.7)
        section.left_margin, section.right_margin = Cm(3), Cm(2)
        section.top_margin, section.bottom_margin = Cm(2), Cm(2)
        section.footer_distance = Cm(0.9)
        for name, size in (
            ("Normal", 13),
            ("Heading 1", 16),
            ("Heading 2", 14),
            ("Heading 3", 13),
            ("Caption", 12),
            ("Title", 17),
        ):
            style = self.doc.styles[name]
            style.font.name = "Times New Roman"
            style.font.size = Pt(size)
            style.font.color.rgb = RGBColor(0, 0, 0)
            for border in list(style.element.iter(qn("w:pBdr"))):
                border.getparent().remove(border)
            style.element.get_or_add_rPr().append(
                xml(
                    "w:rFonts",
                    ascii="Times New Roman",
                    hAnsi="Times New Roman",
                    eastAsia="Times New Roman",
                    cs="Times New Roman",
                )
            )
            pf = style.paragraph_format
            pf.line_spacing = 1.3
            pf.space_after = Pt(6)
            pf.widow_control = True
            if name == "Normal":
                pf.first_line_indent = Cm(1.1)
                pf.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
            else:
                pf.first_line_indent = Cm(0)
            if name.startswith("Heading"):
                style.font.bold = True
                pf.keep_with_next = True
                pf.space_before = Pt(12)
        self.doc.styles[
            "Heading 1"
        ].paragraph_format.alignment = WD_ALIGN_PARAGRAPH.CENTER
        self.doc.styles["Heading 1"].paragraph_format.page_break_before = True
        self.doc.styles["Caption"].font.italic = False
        self.doc.styles["Caption"].font.bold = False
        self.doc.styles["Title"].font.bold = True
        self.doc.styles[
            "Caption"
        ].paragraph_format.alignment = WD_ALIGN_PARAGRAPH.CENTER
        self.doc.core_properties.title = "Mô phỏng phân phối khóa lượng tử kết hợp AEAD"
        self.doc.core_properties.author = "Nguyễn Phạm Tuân; Trần Duy Hòa"
        self.doc.core_properties.created = datetime(2026, 11, 20)
        self.doc.core_properties.modified = datetime(2026, 11, 20)
        self.doc.settings.element.append(xml("w:updateFields", val="true"))
        compat = self.doc.settings.element.find(qn("w:compat"))
        if compat is not None:
            compat.append(
                xml(
                    "w:compatSetting",
                    name="compatibilityMode",
                    uri="http://schemas.microsoft.com/office/word",
                    val="15",
                )
            )

    def p(self, text: str, *, bold: bool = False) -> Any:
        """Add an academic paragraph with body first-line indentation."""
        paragraph = self.doc.add_paragraph()
        paragraph.add_run(text).bold = bold
        return paragraph

    def sub(self, label: str, text: str) -> None:
        """Use the requested black diamond for a functional contract label."""
        paragraph = self.doc.add_paragraph()
        paragraph.paragraph_format.first_line_indent = Cm(0)
        paragraph.add_run(f"❖ {label}: ").bold = True
        paragraph.add_run(text)

    def h(self, text: str, level: int = 2) -> None:
        """Register numbered headings for a cached, live TOC."""
        self.doc.add_heading(text, level)
        self.headings.append((level, text))

    def eq(self, text: str) -> None:
        """Store a Unicode mathematical expression as an editable Office equation."""
        p = self.doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.first_line_indent = Cm(0)
        equation = OxmlElement("m:oMath")
        run, value = OxmlElement("m:r"), OxmlElement("m:t")
        value.text = text
        run.append(value)
        equation.append(run)
        p._p.append(equation)

    def code(self, text: str) -> None:
        """Shade code paragraphs without introducing layout tables."""
        p = self.doc.add_paragraph()
        p.paragraph_format.first_line_indent = Cm(0)
        p.paragraph_format.line_spacing = 1.05
        p.paragraph_format.keep_together = True
        p.alignment = WD_ALIGN_PARAGRAPH.LEFT
        p._p.get_or_add_pPr().append(xml("w:shd", fill="F2F2F2"))
        r = p.add_run(text)
        r.font.name, r.font.size = "Consolas", Pt(10)

    def table(
        self,
        title: str,
        headers: Sequence[str],
        rows: Iterable[Sequence[object]],
        *,
        source: str = "",
        widths: Sequence[float] | None = None,
    ) -> None:
        """Place an italic-prefix caption above a padded, repeating-header table."""
        caption = f"Bảng {len(self.tables) + 1}. {title}"
        self.tables.append(caption)
        self.table_sources.append(source)
        p = self.doc.add_paragraph(style="Caption")
        p.paragraph_format.keep_with_next = True
        p.add_run(caption.split(". ", 1)[0] + ". ").italic = True
        p.add_run(title)
        table = self.doc.add_table(rows=1, cols=len(headers))
        table.alignment = WD_TABLE_ALIGNMENT.CENTER
        table.autofit = False
        if widths is None:
            widths = [16 / len(headers)] * len(headers)
        for column, width in zip(table.columns, widths, strict=True):
            column.width = Cm(width)
        properties = table._tbl.tblPr
        borders = xml("w:tblBorders")
        for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
            borders.append(xml(f"w:{edge}", val="single", sz="4", color="CCCCCC"))
        properties.append(borders)
        margins = xml("w:tblCellMar")
        for side in ("top", "bottom", "left", "right"):
            margins.append(xml(f"w:{side}", w="85", type="dxa"))
        properties.append(margins)
        table.rows[0]._tr.get_or_add_trPr().append(xml("w:tblHeader"))
        for values, row in [
            (headers, table.rows[0]),
            *((values, table.add_row()) for values in rows),
        ]:
            row._tr.get_or_add_trPr().append(xml("w:cantSplit"))
            is_header = row._tr is table.rows[0]._tr
            for index, (cell, value) in enumerate(zip(row.cells, values, strict=True)):
                cell.width = Cm(widths[index])
                cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
                cell.text = fmt(value)
                if is_header:
                    cell._tc.get_or_add_tcPr().append(xml("w:shd", fill="E9ECEF"))
                for paragraph in cell.paragraphs:
                    paragraph.paragraph_format.first_line_indent = Cm(0)
                    paragraph.paragraph_format.line_spacing = 1.12
                    paragraph.paragraph_format.space_after = Pt(2)
                    paragraph.paragraph_format.space_before = Pt(2)
                    paragraph.alignment = WD_ALIGN_PARAGRAPH.LEFT
                    for run in paragraph.runs:
                        run.font.size = Pt(10.5)
                        run.bold = is_header
        if source:
            self.source(source)

    def source(self, text: str) -> None:
        """Keep source notes concise and distinguish them from measured values."""
        p = self.doc.add_paragraph()
        p.paragraph_format.first_line_indent = Cm(0)
        p.paragraph_format.line_spacing = 1.08
        p.alignment = WD_ALIGN_PARAGRAPH.LEFT
        r = p.add_run(f"Nguồn: {text}")
        r.font.size = Pt(10)

    def fig(self, title: str, path: Path, source: str) -> None:
        """Embed a real PNG with aspect ratio preserved and a following caption."""
        if not path.is_file():
            raise FileNotFoundError(path)
        p = self.doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.first_line_indent = Cm(0)
        p.paragraph_format.keep_with_next = True
        shape = p.add_run().add_picture(str(path), width=Cm(15.8))
        if shape.height > Cm(14.7):
            ratio = Cm(14.7) / shape.height
            shape.width = int(shape.width * ratio)
            shape.height = Cm(14.7)
        shape._inline.docPr.set("descr", title)
        caption = f"Hình {len(self.figures) + 1}. {title}"
        self.figures.append(caption)
        self.figure_sources.append(rel(path))
        p = self.doc.add_paragraph(style="Caption")
        p.add_run(caption.split(". ", 1)[0] + ". ").italic = True
        p.add_run(title)
        self.source(source)

    def flow(
        self,
        name: str,
        title: str,
        labels: list[str],
        source: str,
        branch: str | None = None,
    ) -> None:
        """Add a code-derived process graph, never an experimental measurement."""
        self.fig(
            title,
            diagram(name, labels, branch=branch),
            f"sơ đồ tự dựng từ {source}; đây là mô tả thiết kế.",
        )

    def cover(self) -> None:
        """Build an isolated, unnumbered double-border faculty cover."""
        section = self.doc.sections[0]
        borders = xml("w:pgBorders", offsetFrom="page", display="allPages")
        for side in ("top", "left", "bottom", "right"):
            borders.append(
                xml(
                    f"w:{side}",
                    val="thickThinSmallGap",
                    sz="12",
                    space="27",
                    color="000000",
                )
            )
        section._sectPr.append(borders)

        def center(
            text: str,
            size: int,
            *,
            bold: bool = False,
            before: int = 0,
            after: int = 0,
            italic: bool = False,
        ) -> None:
            p = self.doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            pf = p.paragraph_format
            pf.first_line_indent, pf.line_spacing = Cm(0), 1.1
            pf.space_before, pf.space_after = Pt(before), Pt(after)
            r = p.add_run(text)
            r.font.size, r.bold, r.italic = Pt(size), bold, italic

        center("ĐẠI HỌC ĐÀ NẴNG", 13, bold=True)
        center("TRƯỜNG ĐẠI HỌC BÁCH KHOA", 13, bold=True)
        center("KHOA CÔNG NGHỆ THÔNG TIN", 14, bold=True, before=8, after=16)
        logo = ROOT / "docs/assets/logo_it.png"
        if logo.is_file():
            p = self.doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p.paragraph_format.first_line_indent = Cm(0)
            p.add_run().add_picture(str(logo), width=Cm(3))
        else:
            p = self.doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p.paragraph_format.first_line_indent = Cm(0)
            p.paragraph_format.space_after = Pt(18)
            r = p.add_run("[Chèn logo Khoa CNTT]")
            r.font.size = Pt(11)
            r._r.get_or_add_rPr().append(xml("w:bdr", val="single", sz="4", space="6"))
        center("BÁO CÁO MÔN HỌC", 18, bold=True, before=20, after=8)
        center("[ĐIỀN TÊN MÔN HỌC, VD: MÃ HÓA VÀ MẬT MÃ HỌC]", 12, bold=True)
        center("ĐỀ TÀI", 14, bold=True, before=28, after=10)
        center(
            "MÔ PHỎNG HỆ THỐNG PHÂN PHỐI KHÓA LƯỢNG TỬ (BB84, E91) "
            "KẾT HỢP GIÁM SÁT LƯỢNG TỬ VÀ MÃ HÓA XÁC THỰC AEAD "
            "(AES-256-GCM, CHACHA20-POLY1305)",
            15,
            bold=True,
            after=28,
        )
        table = self.doc.add_table(rows=3, cols=3)
        table.alignment = WD_TABLE_ALIGNMENT.CENTER
        table.autofit = False
        data = [
            ("Họ tên sinh viên", "Mã sinh viên", "Nhóm HP"),
            ("Nguyễn Phạm Tuân", "102230329", "[23Nh12]"),
            ("[Trần Duy Hòa]", "[102230187]", "[23Nh12]"),
        ]
        borders = xml("w:tblBorders")
        for side in ("top", "left", "bottom", "right", "insideH", "insideV"):
            borders.append(xml(f"w:{side}", val="single", sz="5", color="000000"))
        table._tbl.tblPr.append(borders)
        for index, values in enumerate(data):
            for cell, value, width in zip(
                table.rows[index].cells, values, (6.1, 4.1, 3.0), strict=True
            ):
                cell.width = Cm(width)
                cell.text = value
                p = cell.paragraphs[0]
                p.paragraph_format.first_line_indent = Cm(0)
                p.paragraph_format.space_after = Pt(3)
                p.paragraph_format.line_spacing = 1.1
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                for r in p.runs:
                    r.font.size, r.bold = Pt(12), index == 0
        center("CBHD : [PGS.TS. Nguyễn Tấn Khôi]", 13, bold=True, before=28)
        section.footer_distance = Cm(2)
        cover_footer = section.footer.paragraphs[0]
        cover_footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
        cover_footer.paragraph_format.first_line_indent = Cm(0)
        cover_footer.add_run("Đà Nẵng, 11/2026").italic = True
        section = self.doc.add_section(WD_SECTION_START.NEW_PAGE)
        section.footer_distance = Cm(0.9)
        # add_section clones sectPr; the body must explicitly remove cover borders.
        for border in list(section._sectPr.findall(qn("w:pgBorders"))):
            section._sectPr.remove(border)
        section.footer.is_linked_to_previous = False
        footer = section.footer.paragraphs[0]
        footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
        footer.paragraph_format.first_line_indent = Cm(0)
        field(footer, "PAGE", "1")
        section._sectPr.append(xml("w:pgNumType", start="1"))

    def front(self) -> None:
        """Reserve live contents and complete, statically registered caption lists."""
        p = self.doc.add_paragraph("MỤC LỤC", style="Title")
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        field(
            self.doc.add_paragraph(),
            'TOC \\o "1-3" \\h \\z \\u',
            "Cập nhật mục lục trong Word bằng Ctrl+A → F9.",
        )
        self.doc.add_paragraph().add_run()._r.append(xml("w:br", type="page"))
        p = self.doc.add_paragraph("DANH MỤC BẢNG", style="Title")
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        self.list_tables = p
        self.doc.add_paragraph().add_run()._r.append(xml("w:br", type="page"))
        p = self.doc.add_paragraph("DANH MỤC HÌNH", style="Title")
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        self.list_figures = p
        self.doc.add_paragraph().add_run()._r.append(xml("w:br", type="page"))
        p = self.doc.add_paragraph("LỜI MỞ ĐẦU", style="Title")
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        self.p(
            "Báo cáo trình bày thiết kế và đánh giá qkdsim, một hệ thống mô phỏng "
            "phân phối khóa lượng tử BB84 và E91 kết hợp giám sát công khai, hậu xử lý "
            "cổ điển và mã hóa xác thực. Toàn bộ kênh lượng tử là mô hình phần mềm "
            "trong phòng thí nghiệm; kết quả không chứng nhận an toàn cho một hệ thống "
            "quang học hoặc dịch vụ truyền thông ngoài thực tế."
        )
        self.p(
            "Động lực nghiên cứu xuất phát từ hai tác động khác nhau của tính toán "
            "lượng tử. Shor đe dọa giả định phân tích thừa số và logarit rời rạc của "
            "RSA/ECC khi có máy lượng tử đủ năng lực. Grover làm giảm số mũ truy vấn "
            "tìm khóa đối xứng trong mô hình lý tưởng. Do đó, phân phối khóa và bảo vệ "
            "nội dung là hai bài toán liên quan nhưng cần các cơ chế đánh giá riêng. "
            + self.cite("shor1994algorithms", "grover1996search")
        )
        self.p(
            "Sản phẩm cung cấp backend NumPy cho quét tham số lớn, backend Qiskit Aer "
            "để đối chiếu mô hình đo, các bộ phát hiện QBER và tỷ lệ dò, cơ chế xác "
            "thực HMAC và container tệp QKDH. Hai demo cho phép quan sát gửi tin qua "
            "TCP loopback và khôi phục tệp sau kiểm tra thẻ AEAD. Khóa từ mô phỏng "
            "có seed dự đoán được không an toàn để dùng ngoài thực tế, ngay cả khi "
            "HKDF và thư viện AEAD hoạt động đúng."
        )
        self.p(
            "Báo cáo gồm ba chương. Chương 1 xây dựng nền tảng vật lý, thống kê và "
            "mật mã. Chương 2 ánh xạ yêu cầu vào cấu trúc chương trình, hợp đồng dữ "
            "liệu và các điều kiện dừng. Chương 3 sử dụng bộ kết quả đã lưu để đối "
            "chiếu mô hình, đánh giá ứng dụng và xác định giới hạn cần nghiên cứu tiếp."
        )

    def finish_lists(self) -> None:
        """Insert each caption exactly once in its corresponding front list."""
        for anchor, captions in (
            (self.list_tables, self.tables),
            (self.list_figures, self.figures),
        ):
            previous = anchor._p
            for caption in captions:
                p = self.doc.add_paragraph(caption)
                p.paragraph_format.first_line_indent = Cm(0)
                p.paragraph_format.line_spacing = 1.15
                previous.addnext(p._p)
                previous = p._p


def chapter_one(r: Report) -> None:
    """Explain the project's models, formulas, references and security boundaries."""
    r.h("CHƯƠNG 1. CƠ SỞ LÝ THUYẾT", 1)
    r.h("1.1 Tổng quan về mật mã lượng tử và bài toán phân phối khóa")
    r.p(
        "Phân phối khóa nhằm tạo vật liệu khóa chung giữa các bên qua một môi trường "
        "có thể bị quan sát hoặc can thiệp. QKD sử dụng thống kê phép đo để phát hiện "
        "những tác động không tương thích với mô hình kênh đã giả định, sau đó giảm "
        "thông tin của đối phương bằng hậu xử lý. Việc chấp nhận phiên luôn phụ thuộc "
        "xác thực kênh cổ điển, mô hình nguồn và detector, cỡ mẫu và ngân sách sai số."
    )
    r.p(
        "JST-UD 7832 cung cấp bối cảnh thực thi các thuật toán lượng tử cơ bản, trong "
        "đó có Grover; JST-UD 8256 bàn về thuật toán lượng tử phá mã RSA. "
        "Trong đề tài, hai tài liệu được dùng để đặt vấn đề, còn E15 là bảng "
        "mô hình chi phí tìm khóa "
        "và không chạy Shor hay Grover trên khóa thực. AES-256 và ChaCha20 với khóa "
        "256 bit có số mũ truy vấn tìm khóa tổng quát bằng 128 dưới giả định entropy "
        "khóa đầy đủ. Chi phí oracle, sửa lỗi và độ sâu mạch chưa được đo. "
        + r.cite("dung2022quantum", "dung2023rsa", "grassl2016aes")
    )
    r.table(
        "Phân biệt đối tượng kỹ thuật và ánh xạ chương trình",
        ["Đối tượng", "Câu hỏi kỹ thuật", "Điểm hiện thực"],
        [
            ("QKD", "Hai đầu tạo khóa chung hay dừng?", "simulation.py; protocols/"),
            (
                "Mô hình vật lý",
                "Xung nào đến và được đo thế nào?",
                "physics/; attacks/",
            ),
            ("Hậu xử lý", "Loại mẫu, sửa lỗi, giảm lượng rò ra sao?", "postprocess/"),
            ("Giám sát", "Quan sát có bất thường so với nền?", "monitor/"),
            (
                "Xác thực",
                "Ai phát khung và có đúng thứ tự?",
                "auth/channel.py; pool.py",
            ),
            (
                "Bảo vệ nội dung",
                "Bản mã có giữ bí mật và toàn vẹn?",
                "crypto/aead.py; container.py",
            ),
            (
                "Phân phối khóa ứng dụng",
                "Khóa nào còn được phép cấp?",
                "crypto/keystore.py",
            ),
        ],
        source="src/qkdsim/; đường dẫn trong bảng tương đối với gói này.",
        widths=[3, 6, 7],
    )
    r.h("1.2 Tổng quan tài liệu và các nghiên cứu tham khảo")
    r.p(
        "Các tài liệu nền tảng xác định mô hình giao thức và nguyên lý an toàn; các "
        "nghiên cứu ứng dụng hỗ trợ đối chiếu kiến trúc. Báo cáo không chuyển số liệu "
        "của công trình khác thành kết quả của qkdsim. Việc đối chiếu năm công trình "
        "dưới đây tập trung vào phạm vi được nêu trong dàn ý và thông tin thư mục, "
        "không giả định đã tái lập đầy đủ mọi thí nghiệm của từng tác giả."
    )
    r.table(
        "Đối chiếu các công trình tham khảo với đề tài",
        ["Tài liệu", "Nội dung đối chiếu", "Phạm vi qkdsim"],
        [
            (
                r.cite("bennett1984bb84", "ekert1991e91"),
                "BB84 chuẩn bị–đo; E91 kiểm tra Bell",
                "Hai backend; E1, E7, E8",
            ),
            (
                r.cite("brassard1994cascade", "tomamichel2012finite"),
                "Hiệu chỉnh và ngân sách khóa hữu hạn",
                "Cascade-back; cận giản lược",
            ),
            (
                r.cite("mozo2025hybrid"),
                "BB84 mô phỏng kết hợp AES-256",
                "HKDF → AEAD → container; E10–E11",
            ),
            (
                r.cite("rao2017aes"),
                "AES-256 trước tấn công lượng tử",
                "E15 tách truy vấn Grover khỏi chi phí cổng",
            ),
            (
                r.cite("ravipati2025e91"),
                "E91 và bảo vệ liên lạc",
                "Φ+; góc Bloch; cận CHSH và QBER",
            ),
            (
                r.cite("sykot2025multilayered"),
                "Bảo mật nhiều lớp có QKD",
                "QKD, HMAC, AEAD; không có giấu tin",
            ),
            (
                r.cite("thakur2025hybrid"),
                "Tổng quan BB84/E91 và hướng lai",
                "E8 so sánh độc lập; chưa ghép hai khóa",
            ),
        ],
        source="docs/references.bib; docs/report_outline_vi.md.",
        widths=[2.4, 6.3, 7.3],
    )
    r.table(
        "Ranh giới giữa tham khảo lý thuyết và hiện thực",
        ["Khía cạnh", "Đã lập trình", "Chưa thuộc sản phẩm"],
        [
            (
                "Nguồn quang",
                "Đơn photon; số photon Poisson",
                "Thiết bị thật; PNS; mồi đầy đủ",
            ),
            (
                "An toàn QKD",
                "Ước lượng QBER, CHSH, rò EC/verify",
                "Chứng minh khả hợp cho mọi tấn công",
            ),
            ("Xác thực", "HMAC-SHA256; làm mới pool", "Wegman–Carter"),
            (
                "Mật mã ứng dụng",
                "AES-GCM; ChaCha20-Poly1305; HKDF",
                "Chữ ký hậu lượng tử; ML-KEM",
            ),
            (
                "Lai giao thức",
                "BB84 hoặc E91 đưa khóa cho AEAD",
                "HKDF(K_BB84 || K_E91)",
            ),
            (
                "Kiểm thử ngẫu nhiên",
                "Năm chẩn đoán SP 800-22",
                "Chứng nhận entropy nguồn vật lý",
            ),
        ],
        source="src/qkdsim/; SPEC.md mục 20; docs/decisions.md.",
        widths=[3, 6.5, 6.5],
    )
    r.h("1.3 Cơ sở lý thuyết giao thức QKD, hậu xử lý và mã hóa xác thực")
    r.h("1.3.1 Qubit, phép đo và giao thức BB84", 3)
    r.p(
        "Qubit thuần có biểu diễn |ψ⟩ = α|0⟩ + β|1⟩ với tổng bình phương môđun "
        "của hai biên độ bằng một. Quy tắc Born cho xác suất kết quả 1 khi đo Z bằng "
        "|β|². Cơ sở X gồm |+⟩ và |−⟩, là tổ hợp tổng và hiệu của hai trạng thái Z "
        "chia √2. Vì độ chồng lấp giữa một trạng thái Z và một trạng thái X có bình "
        "phương bằng 1/2, phép đo sai cơ sở không giữ thông tin bit chuẩn bị."
    )
    r.p(
        "Định lý không nhân bản có thể giải thích bằng bảo toàn tích vô hướng. Nếu "
        "cùng một biến đổi unita sao chép được |a⟩ và |b⟩, tích vô hướng phải thỏa "
        "⟨a|b⟩ = ⟨a|b⟩²; điều kiện không đúng với hai trạng thái phân biệt và không "
        "trực giao. Eve trong mô hình phải đo rồi chuẩn bị lại, qua đó gây nhiễu khi "
        "chọn sai cơ sở. " + r.cite("wootters1982cloning", "bennett1984bb84")
    )
    r.p(
        "Alice chọn bit và cơ sở Z/X; Bob chọn cơ sở độc lập, đo các xung được dò "
        "và công bố cơ sở qua kênh cổ điển đã xác thực. Hai bên giữ các vị trí phát "
        "hiện cùng cơ sở. Với pZ = 1/2, tỷ lệ giữ kỳ vọng trên lượt dò là 1/2. Khi "
        "Eve chặn tỷ lệ p và dùng cơ sở ngẫu nhiên trên kênh lý tưởng, ba yếu tố "
        "p, xác suất sai cơ sở 1/2 và xác suất sai bit 1/2 cho QBER = p/4."
    )
    r.eq("QIR = p/4;  Q = ech + QIR − 2echQIR;  Pphát hiện(k) = 1 − (3/4)ᵏ")
    r.p(
        "Công thức phát hiện cuối chỉ mô tả có ít nhất một sai khác khi Eve chặn "
        "toàn phần trên kênh lý tưởng. Trong kênh nhiễu, sai khác còn có thể đến từ "
        "thiết bị. Kênh sợi dùng ηch = 10^(−αL/10); depolarizing mức d đóng góp d/2 "
        "và lệch góc θ đóng góp sin²θ. Detector áp dụng hiệu suất, đếm tối và chọn "
        "bit ngẫu nhiên khi nhấp kép. Nhiễu độc lập ghép bằng XOR thay vì cộng thô."
    )
    r.h("1.3.2 E91, rối lượng tử và kiểm tra Bell CHSH", 3)
    r.p(
        "Mã nguồn dùng |Φ+⟩ = (|00⟩ + |11⟩)/√2; đây là quy ước khác trạng thái "
        "singlet trong bài gốc của Ekert. Alice đo ở các góc Bloch 0, π/4, π/2; "
        "Bob đo ở π/4, π/2, 3π/4. Trong chín cặp thiết lập đồng xác suất, hai cặp "
        "cùng góc tạo khóa, bốn cặp dùng CHSH, ba cặp còn lại không dùng cho hai "
        "mục đích này. " + r.cite("ekert1991e91", "clauser1969chsh")
    )
    r.eq("E(a,b) = V cos(a−b);  S = E₀₀ − E₀₂ + E₂₀ + E₂₂ = 2√2 V")
    r.p(
        "V là độ hiển thị Werner khi tắt các nguồn nhiễu bổ sung. Cận cổ điển là "
        "|S| ≤ 2. Trên mẫu, tương quan ước lượng bằng 1 − 2x/n; phương sai của S "
        "cộng các phương sai (1 − Ê²)/(n − 1) ở bốn nhóm rời nhau. Chương trình "
        "chỉ cho qua cổng Bell khi S − zσS > 2 và mỗi nhóm đủ mẫu để tính sai số. "
        "Đây là kiểm tra trong mô hình dò đã giả định, chưa phải an toàn độc lập "
        "thiết bị. Tỷ lệ trùng phùng chịu tích suy hao hai nhánh."
    )
    r.p(
        "Khi Eve đo Z/X đồng xác suất rồi phát lại trên nhánh Bob, tương quan "
        "trên cặp bị chặn giảm một nửa. Tại V = 1 và chặn toàn phần, mô hình dự "
        "báo S = √2 và QBER cặp khóa bằng 1/4. Với Eve cố định Z hoặc X, QBER "
        "cặp khóa lần lượt là 3/8 hoặc 1/8; vì vậy không chuyển trực tiếp mọi "
        "công thức BB84 sang các thiết lập khóa E91."
    )
    r.h("1.3.3 Hậu xử lý cổ điển và độ dài khóa hữu hạn", 3)
    r.p(
        "Sàng lọc không phải khóa cuối. Hai bên lấy mẫu đều không hoàn lại, công "
        "bố bit để ước lượng QBER và loại các bit này khỏi vật liệu khóa. Với x "
        "lỗi trong k bit, Q̂ = x/k. Chương trình dùng cận Hoeffding để quyết định "
        "dừng và lưu thêm khoảng Clopper–Pearson, Wilson để mô tả độ không chắc chắn."
    )
    r.eq("Qub = min{1, Q̂ + √[ln(1/εPE)/(2k)]}")
    r.p(
        "Cascade hoán vị khóa qua nhiều lượt, chia khối và công bố chẵn lẻ. Khối "
        "bất đồng chẵn lẻ được tìm kiếm nhị phân để sửa một bit. Cascade-back cập "
        "nhật những khối đã mở ở các lượt trước chứa bit vừa sửa và tái xử lý khi "
        "chẵn lẻ đổi. Kích thước ban đầu là max(2, ceil(0,73/Q̂)); khi mẫu không "
        "có lỗi, mã dùng mức nội bộ 0,01. Mỗi chẵn lẻ mới được tính vào leakEC. "
        "Số lượt hữu hạn vẫn có thể để sót các cặp lỗi chẵn. "
        + r.cite("brassard1994cascade")
    )
    r.p(
        "Xác minh dùng băm đa thức tại điểm ngẫu nhiên hệ điều hành trong trường "
        "GF(2⁶¹−1), không dùng so sánh trực tiếp khóa qua mạng. Chặn xác suất trùng "
        "thẻ dựa vào bậc đa thức chia kích thước trường và được kiểm tra với εcor. "
        "Thẻ công khai chiếm 64 bit trong phép tính lượng rò. Khi xác minh thành "
        "công, phép băm Toeplitz K = Tx mod 2 rút khóa xuống ℓ bit; seed công khai "
        "độc lập dài n + ℓ − 1 bit lấy từ hệ điều hành."
    )
    r.eq("ℓ = ⌊n[1−h₂(min(Qub, 1/2))] − leakEC − leakverify − 2 log₂(1/εPA)⌋")
    r.p(
        "Ở đây h₂(q) = −q log₂q − (1−q)log₂(1−q), εPA = εsec; εcor được "
        "xử lý riêng tại xác minh. Tích ma trận Toeplitz được tính bằng tích chập "
        "FFT, làm tròn rồi lấy modulo 2, tránh dựng ma trận đặc. Khi ℓ ≤ 0 hoặc "
        "đầu ra hai bên không khớp, phiên dừng. Cận này là giản lược cho nguồn "
        "đơn photon lý tưởng, chưa thay thế chứng minh khả hợp với lấy mẫu hữu "
        "hạn và tấn công tổng quát. " + r.cite("shor2000bb84", "tomamichel2012finite")
    )
    r.h("1.3.4 Xác thực HMAC, HKDF và mã hóa AEAD", 3)
    r.p(
        "Kênh cổ điển là công khai nhưng cần xác thực nguồn gốc và thứ tự. Khung "
        "HMAC-SHA256 ràng buộc mã phiên, chiều gửi, bộ đếm, loại, độ dài và nội dung. "
        "Bên nhận kiểm tra thẻ trước khi chấp nhận số thứ tự kế tiếp. Cơ chế này "
        "cần khóa chia sẻ ban đầu và dựa trên giả định an toàn tính toán. QKD "
        "đóng vai trò mở rộng khóa; tự nó không giải quyết nhận dạng ban đầu."
    )
    r.p(
        "HKDF-SHA256 thực hiện Extract rồi Expand với salt và nhãn mục đích "
        "riêng, tạo khóa cho AES-GCM, ChaCha20-Poly1305 hoặc xác thực. Đầu vào "
        "phải có ít nhất 32 byte trong API hiện tại. Dẫn xuất khóa không bổ sung "
        "entropy bí mật nếu vật liệu QKD được tạo từ seed mô phỏng đã biết. "
        + r.cite("rfc5869")
    )
    r.eq("(C,T) = SealK(N,A,M);  M = OpenK(N,A,C,T)")
    r.p(
        "AEAD bảo vệ bản rõ M và xác thực dữ liệu liên kết A mà không mã hóa A. "
        "AES-256-GCM và ChaCha20-Poly1305 dùng nonce 96 bit và thẻ 128 bit tại "
        "lớp bao của dự án. Nonce ghép tiền tố ngẫu nhiên 32 bit với bộ đếm 64 "
        "bit; giới hạn sử dụng khóa được kiểm tra độc lập với độ dài bộ đếm. "
        "Lặp cùng khóa–nonce có thể làm lộ XOR hai bản rõ. E11 chỉ cố ý vi phạm "
        "trên khóa dùng riêng để minh họa hậu quả. " + r.cite("nist80038d", "rfc8439")
    )
    r.flow(
        "01_overall",
        "Luồng nghiệp vụ tổng thể của QKD-HYBRID",
        [
            "Cấu hình YAML → nguồn và kênh lượng tử mô phỏng",
            "BB84 hoặc E91 → phát hiện và công bố cơ sở",
            "Sàng lọc → công khai mẫu → QBER / CHSH",
            "Giám sát và xác thực → quyết định tiếp tục",
            "Cascade → xác minh → Toeplitz-FFT",
            "Khóa cuối → HKDF → AES-GCM / ChaCha20-Poly1305",
            "Chat TCP loopback hoặc tệp QKDH → kiểm tra toàn vẹn",
        ],
        "src/qkdsim/simulation.py; auth/; crypto/",
        "Không đạt → ABORT, lưu bằng chứng",
    )


RQ = [
    (
        "RQ1",
        "QBER thay đổi thế nào theo Eve và nhiễu?",
        "E1–E3",
        "p/4; ghép XOR; xác suất phát hiện",
    ),
    (
        "RQ2",
        "Giám sát phát hiện tin cậy và nhanh đến đâu?",
        "E3, E13; D1",
        "TPR, FPR, độ trễ, khoảng tin cậy",
    ),
    (
        "RQ3",
        "Cỡ mẫu, QBER và lượng rò quyết định khóa cuối ra sao?",
        "E4–E6",
        "ℓ, fEC, bit/xung và khoảng cách",
    ),
    (
        "RQ4",
        "BB84 và E91 khác nhau về hiệu suất, nhiễu và chi phí?",
        "E7–E8",
        "S, sàng lọc, dừng, thời gian phiên",
    ),
    (
        "RQ5",
        "Hai AEAD khác nhau về hiệu năng và toàn vẹn?",
        "E9–E12; D2",
        "MB/s, ms, khứ hồi, sửa tệp, nonce",
    ),
    (
        "RQ6",
        "Grover/Shor thay đổi bài toán bảo vệ khóa thế nào?",
        "E15",
        "Số mũ truy vấn; mô hình đa thức",
    ),
]

FUNCTIONS = [
    (
        "2.3.1 Đối tượng sử dụng và hợp đồng tương tác",
        "Người dùng CLI truyền cấu hình hoặc tham số; D1 nhận tin nhắn và lệnh bật "
        "Eve; D2 nhận tệp vào/ra; bộ thực nghiệm nhận YAML E1–E15; backend nhận mảng "
        "chuẩn bị và bộ sinh mô phỏng.",
        "CLI xuất JSON công khai; demo trả bản rõ đã xác thực hoặc trạng thái dừng; "
        "thực nghiệm lưu CSV, JSON và PNG/PDF. Backend trả quan sát; bộ điều phối "
        "giữ GroundTruth riêng cho đánh giá.",
        "Typer kiểm tra tham số rồi gọi hàm miền nghiệp vụ. D1 vận chuyển khung "
        "HMAC và AEAD qua TCP loopback; các lượt quang học vẫn chạy trong tiến trình. "
        "D2 tạo khóa qua một liên kết BB84 trước khi xử lý tệp theo khối.",
        "Cấu hình sai bị từ chối sớm; không có khóa dùng được thì demo không gửi. "
        "Hai đường dẫn tệp hoặc tệp khóa trùng nhau bị từ chối. Bộ thực nghiệm "
        "không được suy diễn khóa thành công từ riêng trạng thái accepted "
        "của lệnh bb84.",
        "src/qkdsim/cli.py; file_demo.py; demos/secure_chat.py; experiments/run_all.py",
        "02_interactions",
        "Hợp đồng tương tác giữa người dùng và các lớp hệ thống",
        [
            "CLI / D1 Chat / D2 File / Bộ chạy E1–E15",
            "Kiểm tra YAML và tham số đầu vào",
            "Bộ điều phối simulation.py → backend fast / Aer",
            "Hậu xử lý + giám sát + kênh xác thực",
            "JSON công khai / khóa nội bộ / tệp / CSV và hình",
        ],
    ),
    (
        "2.3.2 Chức năng 1 Mô phỏng vật lý và giao thức BB84 E91",
        "SessionConfig chứa số xung/cặp, nguồn, kênh, detector, Eve và backend; "
        "numpy.random.Generator của phiên cung cấp mọi lựa chọn vật lý.",
        "BB84Transmission hoặc E91Transmission chứa bit, nhãn cơ sở và mặt nạ dò. "
        "simulate_bb84/simulate_e91 trả GroundTruth ở đối tượng riêng.",
        "NumPy thao tác vector trên mảng, suy hao nhị thức từng photon và lấy mẫu "
        "kết quả đo. Aer BB84 dựng một mạch Clifford và mô phỏng stabilizer; E91 "
        "gom thiết lập đo thành mạch hai qubit, dùng ma trận mật độ cho góc ngoài "
        "Clifford. Seed Aer được dẫn xuất từ bộ sinh phiên. Eve IR đo rồi phát lại; "
        "MITM cổ điển chạy hai liên kết riêng, không phải mô hình mất photon.",
        "attack.kind=pns được nhận diện trong schema nhưng các hàm mô phỏng hiện "
        "từ chối vì chưa triển khai. Không coi bit đệm ở vị trí không dò là dữ "
        "liệu khóa. Backend Aer nhỏ được dùng đối chiếu phân phối, không yêu cầu "
        "hai backend có chuỗi bit giống nhau trên cùng seed.",
        "src/qkdsim/simulation.py; protocols/; physics/; attacks/intercept_resend.py; "
        "attacks/mitm_classical.py",
        "03_physics",
        "Chuỗi mô phỏng nguồn kênh Eve và detector",
        [
            "Nguồn đơn photon / Poisson → bit và cơ sở",
            "Suy hao kênh → phần photon đến vị trí Eve",
            "Eve đo–phát lại hoặc truyền nguyên trạng",
            "Nhiễu quang học → đo bằng NumPy / Qiskit Aer",
            "Detector: hiệu suất, đếm tối, nhấp kép",
            "Quan sát Alice–Bob → sàng lọc / thống kê",
        ],
    ),
    (
        "2.3.3 Chức năng 2 Hậu xử lý và độ dài khóa hữu hạn",
        "Quan sát hai phía; các tham số k_min, test_fraction, q_max, eps_pe, "
        "eps_sec, eps_cor; số lượt Cascade và chế độ EC.",
        "LinkKeys gồm đầu ra cục bộ hai bên hoặc AbortEvidence. FinalKey lưu số "
        "bit thật, lượng rò và metadata; các byte đệm ở cuối không làm tăng "
        "độ dài khóa.",
        "Sift giữ vị trí đủ điều kiện; PE lấy mẫu và loại mẫu; Cascade công bố "
        "chẵn lẻ và quay lại khối trước; xác minh băm đa thức; tính ℓ trước PA; "
        "Toeplitz dùng một seed công khai OS cho cả hai phía. Khi có pool HMAC, "
        "dành 256 bit để làm mới xác thực rồi báo riêng độ dài hữu dụng "
        "và tốc độ ròng.",
        "Dừng khi thiếu mẫu, Qub vượt ngưỡng, cận trùng thẻ quá lớn, thẻ khác nhau, "
        "ℓ không dương, hai đầu ra PA khác nhau hoặc không đủ bit làm mới HMAC. "
        "Chế độ ideal EC trực tiếp đồng bộ khóa và ước lượng lượng rò, chỉ phục vụ "
        "tách ảnh hưởng mô hình trong một số thí nghiệm.",
        "src/qkdsim/postprocess/; simulation.py:_finish_key",
        "04_postprocess",
        "Cascade với quay lại khối và khuếch đại riêng tư Toeplitz",
        [
            "Sàng lọc → chọn mẫu công khai không hoàn lại",
            "Tính Q̂, cận Qub → loại bit mẫu",
            "Cascade: hoán vị → chẵn lẻ → chia đôi",
            "Cascade-back: cập nhật và mở lại khối trước",
            "Băm xác minh → tính ℓ từ lượng rò",
            "Toeplitz-FFT → đối chiếu cục bộ → dành bit HMAC",
        ],
    ),
    (
        "2.3.4 Chức năng 3 Lớp giám sát lượng tử",
        "Chỉ các bit mẫu đã công khai, số xung gửi/dò, nhãn cơ sở, cửa sổ QBER "
        "và đường nền hiệu chuẩn. CHSH được tính từ các nhóm kiểm tra E91 riêng.",
        "Metrics, WindowQBER và DetectorDecision; mức OK/WARN/ABORT/LOCKDOWN; "
        "sự kiện JSONL, evidence.json và hình qber.png khi BB84 dừng.",
        "Threshold so Qub với q_max; CI dùng đuôi nhị thức một phía; SPRT cộng "
        "log-tỷ số hợp lý theo bit và dừng ở biên Wald; CUSUM cộng theo cửa sổ "
        "với ngân sách alpha/W; Joint kết hợp QBER với hai đuôi tỷ lệ dò bằng "
        "Bonferroni. Calibration tắt Eve và đo thêm cổng trống. Máy trạng thái "
        "phiên tương ứng yêu cầu SessionStateMachine mang tên MonitoredSession "
        "trong mã hiện tại, kết hợp enum State và Policy.",
        "WARN yêu cầu đổi khóa trước thông điệp tiếp theo; ABORT không cấp khóa; "
        "lỗi liên tiếp tăng thời gian chờ và có thể LOCKDOWN đến khi người vận "
        "hành reset. QBER_Z/X là đại lượng chẩn đoán, không phải một kiểm định "
        "độc lập bổ sung trong Joint. Cổng Hoeffding vẫn áp dụng dù bộ phát hiện "
        "khác báo clear. E91 dùng cổng Bell riêng; không suy diễn rằng có đầy đủ "
        "nhật ký máy trạng thái BB84 cho mọi đường chạy E91.",
        "src/qkdsim/monitor/metrics.py; detectors.py; calibration.py; session.py; "
        "policy.py; events.py; simulation.py:run_e91_link",
        "05_monitor",
        "Luồng giám sát công khai và quyết định phản ứng",
        [
            "Calibration → QBER nền, tỷ lệ dò và đếm tối",
            "Quan sát công khai → QBER, QBER_Z/X, tỷ lệ dò",
            "Threshold / CI / SPRT / CUSUM / Joint",
            "Policy: OK → WARN → ABORT → LOCKDOWN",
            "Cho dùng khóa / yêu cầu rekey / chờ / reset",
            "JSONL và evidence.json → hình QBER khi dừng",
        ],
    ),
    (
        "2.3.5 Chức năng 4 Xác thực cổ điển AEAD và quản lý khóa",
        "Khóa HMAC chia sẻ trước; mã phiên; thông điệp công khai; FinalKey; "
        "bản rõ, salt, nonce, AAD và đường dẫn tệp.",
        "Khung xác thực theo thứ tự, khóa dẫn xuất theo mục đích, bản mã có thẻ "
        "AEAD và báo cáo xử lý tệp. KeyStore cấp khóa theo mã và trạng thái sử dụng.",
        "AuthenticationPool cấp khóa cho liên kết và chỉ làm mới sau thành công. "
        "HKDF dùng nhãn riêng; NonceSequence cấp nonce trong khóa; container xác "
        "thực header cùng chỉ số khối và cờ cuối. Ghi vào tệp tạm bên cạnh đích và "
        "chỉ đổi tên sau khi hoàn tất. KeyStore giữ khóa trong bộ nhớ với trạng "
        "thái available/reserved/used/revoked và TTL; API theo phong cách ETSI-014 "
        "cục bộ, chưa phải dịch vụ REST tương thích tiêu chuẩn.",
        "Sai HMAC, replay, sai AEAD tag/AAD, header lạ, tệp cắt ngắn, đảo khối, "
        "vượt ngân sách nonce/byte hoặc khóa quá hạn đều bị từ chối. D2 lưu khóa "
        "Bob ở sidecar chỉ dành cho demo; quyền cục bộ Windows cần được quản lý, "
        "không được xem tệp này là kho khóa sản xuất.",
        "src/qkdsim/auth/; crypto/kdf.py; aead.py; container.py; "
        "keystore.py; file_demo.py",
        "06_container",
        "Luồng mã hóa tệp QKDH và ràng buộc xác thực",
        [
            "FinalKey + salt hệ điều hành → HKDF theo thuật toán",
            "Header: QKDH | phiên bản | thuật toán | UUID | salt | prefix | cỡ tệp",
            "Chia bản rõ theo khối mặc định 64 KiB",
            "Nonce = prefix 32 bit || counter 64 bit",
            "AAD = header || counter || index || cờ cuối",
            "AEAD → counter || bản mã || tag → tệp tạm → công bố",
        ],
    ),
]


def chapter_two(r: Report) -> None:
    """Connect requirements to actual modules, contracts and failure behavior."""
    r.h("CHƯƠNG 2. PHÂN TÍCH THIẾT KẾ HỆ THỐNG", 1)
    r.h("2.1 Phát biểu bài toán")
    r.p(
        "Hệ thống nhận cấu hình phiên và các tác động mô phỏng, tạo chuỗi quan sát "
        "Alice–Bob, quyết định chấp nhận hoặc dừng rồi cấp vật liệu khóa cho ứng "
        "dụng. Bài toán thiết kế là giữ nhất quán giữa mô hình vật lý, lượng thông "
        "tin đã công khai, điều kiện thống kê và kỷ luật mật mã. Một đường chạy "
        "không đủ bằng chứng không được trả khóa chỉ vì chưa quan sát thấy Eve."
    )
    r.table(
        "Các câu hỏi nghiên cứu và tiêu chí quan sát",
        ["Mã", "Câu hỏi", "Bằng chứng", "Chỉ tiêu"],
        RQ,
        source="SPEC.md mục 1.2; experiments/.",
        widths=[1.1, 6.6, 2.4, 5.9],
    )
    r.table(
        "Yêu cầu chức năng và điểm hiện thực",
        ["Yêu cầu", "Hiện thực", "Điều kiện nghiệm thu"],
        [
            (
                "BB84 và E91",
                "protocols/; physics/; simulation.py",
                "Oracle lý tưởng; dung sai thống kê ≥ 4σ",
            ),
            (
                "Khóa cuối nhất quán",
                "postprocess/",
                "Xác minh, PA và khóa hai phía khớp",
            ),
            (
                "Phát hiện bất thường",
                "monitor/",
                "FPR/TPR, độ trễ và bằng chứng công khai",
            ),
            ("Chống giả mạo cổ điển", "auth/", "Sai thẻ, replay, sai phiên bị từ chối"),
            (
                "Tệp toàn vẹn",
                "crypto/container.py",
                "Hai AEAD round trip; lỗi không công bố bản rõ",
            ),
            (
                "Tái lập thí nghiệm",
                "experiments/_suite.py; run_all.py",
                "CSV + seed, config, commit, versions, hash",
            ),
        ],
        source="src/qkdsim/; tests/; SPEC.md mục 16–17.",
        widths=[3, 6.3, 6.7],
    )
    r.table(
        "Ma trận hợp đồng chức năng cấp hệ thống",
        ["Chức năng", "Đầu vào", "Đầu ra", "Không thành công"],
        [
            (
                "load_config",
                "YAML ghi đè",
                "SessionConfig",
                "Tên/kiểu/miền không hợp lệ",
            ),
            (
                "simulate_*",
                "Config + Generator",
                "Quan sát; GroundTruth riêng",
                "Backend/attack chưa hỗ trợ",
            ),
            (
                "estimate_parameters",
                "SiftedKey + BB84Config",
                "Ước lượng và bit chưa công khai",
                "Thiếu mẫu; Qub cao",
            ),
            (
                "run_*_session",
                "Config, pool tùy chọn",
                "FinalKey hoặc AbortEvidence",
                "HMAC, CHSH, EC, verify, ℓ",
            ),
            (
                "authorize_message",
                "Số byte dự kiến",
                "Cấp quyền và tính ngân sách",
                "WARN; tuổi/byte/số tin vượt hạn",
            ),
            (
                "encrypt/decrypt_file",
                "Tệp, khóa/provider, metadata",
                "Container hoặc bản rõ đã kiểm tra",
                "Sai định dạng, thẻ, bộ đếm, EOF",
            ),
        ],
        source="src/qkdsim/config.py; simulation.py; postprocess/estimation.py; "
        "monitor/session.py; crypto/container.py.",
        widths=[3.2, 3.7, 4.7, 4.4],
    )
    r.h("2.2 Phân tích hiện trạng và ranh giới mô phỏng")
    r.p(
        "Backend nhanh cần phục vụ quét nhiều cấu hình mà không dựng từng mạch "
        "qubit trong vòng lặp Python. Backend Aer cần bám thao tác lượng tử để "
        "kiểm tra ngữ nghĩa phép đo. Vì hai đường có cách lấy mẫu khác nhau, phép "
        "so sánh đúng là phân phối và oracle giải tích với cỡ mẫu thực, không phải "
        "so từng bit cùng seed. Chi phí stabilizer nhiều qubit cũng giới hạn quy "
        "mô của Aer trong các phép đo hiệu năng đã lưu."
    )
    r.table(
        "Vấn đề thiết kế cơ chế đã có và giới hạn",
        ["Vấn đề", "Cơ chế", "Giới hạn cần hiểu"],
        [
            (
                "Quy mô mô phỏng",
                "NumPy vector; Aer đối chiếu điểm nhỏ",
                "Thời gian phụ thuộc máy, nhiễu, quy mô",
            ),
            (
                "RNG",
                "Generator có seed; secrets cho mật mã",
                "Khóa dựa seed vẫn không bí mật thực",
            ),
            (
                "MITM",
                "HMAC gắn ngữ cảnh và thứ tự",
                "Cần khóa ban đầu; an toàn tính toán",
            ),
            (
                "Mẫu hữu hạn",
                "Hoeffding, CP, xác minh và ℓ",
                "Chưa có chứng minh khả hợp đầy đủ",
            ),
            (
                "Tệp lớn",
                "Streaming; đầu ra tạm và đổi tên",
                "I/O và hệ tệp ảnh hưởng benchmark",
            ),
            (
                "Giám sát",
                "5 bộ phát hiện, calibration, policy",
                "Nền đã biết; chưa gộp sai số hiệu chuẩn",
            ),
            (
                "Ranh giới dữ liệu",
                "GroundTruth chỉ cho điều phối/thực nghiệm",
                "FinalKey còn cờ Eve phục vụ mô phỏng",
            ),
        ],
        source="docs/decisions.md; src/qkdsim/.",
        widths=[3, 6.3, 6.7],
    )
    r.p(
        "GroundTruth chứa cơ sở, bit và mặt nạ chặn của Eve, được giữ ngoài gói "
        "giao thức và giám sát. FinalKey hiện vẫn có cờ ground_truth_eve_present "
        "ẩn khỏi repr để thí nghiệm ghi nhận sự hiện diện Eve sau xử lý; cờ này "
        "không được dùng làm điều kiện phát hiện. Đây là metadata riêng của bộ "
        "mô phỏng, cần bỏ khỏi hợp đồng cấp khóa khi xây dựng dịch vụ thực."
    )
    r.h("2.3 Phân tích chức năng")
    for (
        heading,
        inputs,
        outputs,
        algorithm,
        errors,
        source,
        name,
        title,
        labels,
    ) in FUNCTIONS:
        r.h(heading, 3)
        r.sub("Đầu vào", inputs)
        r.sub("Đầu ra", outputs)
        r.sub("Thuật toán", algorithm)
        r.sub("Điều kiện và xử lý ngoại lệ", errors)
        r.sub("Căn cứ mã nguồn", source)
        r.flow(name, title, labels, source)
    r.code(
        "SIFT → PE → nếu Qub > q_max: ABORT\n"
        "CASCADE → VERIFY → nếu thẻ/cận không đạt: ABORT\n"
        "ℓ ← secret_key_length(n, Qub, leakEC, leakverify, εsec, εcor)\n"
        "nếu ℓ ≤ bit cần làm mới HMAC: ABORT\n"
        "PA_A, PA_B ← Toeplitz-FFT(cùng seed công khai từ OS)\n"
        "nếu PA_A ≠ PA_B: ABORT; ngược lại cấp khóa hữu dụng"
    )
    r.flow(
        "07_session",
        "Máy trạng thái phiên BB84 và nhánh dừng",
        [
            "INIT → QUANTUM_TX",
            "BASIS_RECONCILIATION → PARAMETER_ESTIMATION",
            "ERROR_CORRECTION → VERIFICATION",
            "PRIVACY_AMPLIFICATION → KEY_READY",
            "KEY_IN_USE → kiểm tra hạn mức và yêu cầu rekey",
            "Thử phiên mới qua back-off; LOCKDOWN cần reset",
        ],
        "src/qkdsim/monitor/session.py; policy.py",
        "Lỗi tại bước hợp lệ → ABORT → evidence.json",
    )
    r.h("2.3.6 Công nghệ sử dụng", 3)
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    deps = project["project"]["dependencies"]
    dev = project["project"]["optional-dependencies"]["dev"]
    roles = {
        "numpy": "Mảng và mô phỏng vector",
        "scipy": "Phân phối, thống kê, FFT",
        "qiskit": "Dựng mạch lượng tử",
        "qiskit-aer": "Mô phỏng mạch và nhiễu",
        "cryptography": "AEAD, HKDF",
        "matplotlib": "Biểu đồ và sơ đồ",
        "pyyaml": "Đọc cấu hình",
        "typer": "CLI",
        "rich": "Hiển thị terminal",
        "click": "Nền CLI",
        "pytest": "Kiểm thử",
        "pytest-cov": "Độ bao phủ",
        "hypothesis": "Kiểm tra theo thuộc tính",
        "ruff": "Lint",
        "mypy": "Kiểu tĩnh",
        "pre-commit": "Hook kiểm tra",
        "types-pyyaml": "Kiểu cho YAML",
        "jsonschema": "Kiểm tra schema sự kiện",
    }
    r.table(
        "Công nghệ và phiên bản được ghim trong dự án",
        ["Phụ thuộc", "Vai trò", "Nhóm"],
        [
            (
                dependency,
                roles.get(dependency.split("==")[0].lower(), "Hỗ trợ dự án"),
                group,
            )
            for group, dependencies in (("Chạy", deps), ("Phát triển", dev))
            for dependency in dependencies
        ]
        + [
            (
                "python-docx==1.2.0",
                "Dựng DOCX theo yêu cầu báo cáo",
                "Bổ sung qua uv --with",
            )
        ],
        source="pyproject.toml; lệnh dựng báo cáo.",
        widths=[5.8, 6.5, 3.7],
    )
    r.p(
        "Python yêu cầu từ 3.11 theo pyproject.toml. Pandas, Streamlit và thư viện "
        "PQC chỉ xuất hiện ở định hướng đặc tả, không phải phụ thuộc thực tế hiện "
        "tại. Trình dựng dùng csv của thư viện chuẩn, giữ nguyên các tệp kết quả."
    )
    r.h("2.4 Thiết kế cấu trúc dữ liệu giao thức và định dạng lưu trữ")
    r.h("2.4.1 Luồng dữ liệu và cấu trúc đối tượng chính", 3)
    r.table(
        "Đối tượng dữ liệu và phạm vi truy cập",
        ["Đối tượng", "Thành phần chính", "Vai trò và ranh giới"],
        [
            (
                "SessionConfig",
                "seed; bb84/e91; channel; source; attack; monitor; crypto",
                "Bất biến; kiểm tra tại khởi tạo",
            ),
            (
                "BB84/E91Transmission",
                "Bit, thiết lập đo, mặt nạ dò",
                "Quan sát dùng sàng lọc và nhóm kiểm tra",
            ),
            (
                "GroundTruth",
                "eve_intercepted_mask; eve_basis; eve_bit",
                "Riêng bộ mô phỏng; không cho detector",
            ),
            (
                "ParameterEstimate",
                "stats; alice_remaining; bob_remaining",
                "Bit mẫu đã bị loại",
            ),
            (
                "FinalKey",
                "key_bytes ẩn repr; UUID; length_bits; QBER; leak; eps",
                "Giữ số bit thật; chỉ xuất metadata công khai",
            ),
            (
                "AbortEvidence",
                "session_id; reason; planned_sample_size; stats",
                "Không có khóa có thể cấp",
            ),
            (
                "Event",
                "schema_version; timestamp; state; alert; metrics; detector",
                "Audit công khai theo lần chuyển trạng thái",
            ),
        ],
        source="src/qkdsim/config.py; protocols/; attacks/intercept_resend.py; "
        "postprocess/result.py; monitor/events.py.",
        widths=[3.4, 6.6, 6],
    )
    r.p(
        "Luồng dữ liệu được phân tách ngay ở đầu ra bộ điều phối: quan sát đến "
        "sàng lọc và lấy mẫu, GroundTruth chỉ đến kiểm thử/thực nghiệm. Khóa cuối "
        "đi vào HKDF hoặc KeyStore; log chỉ nhận bộ đếm và tham số công khai. Không "
        "in key_bytes, chuỗi bit khóa hay toàn bộ băm khóa. Nếu cần nhận diện khóa, "
        "chỉ dùng UUID, số bit và tối đa bốn ký tự hex đầu của fingerprint SHA-256."
    )
    r.h("2.4.2 Cấu hình YAML và các dataclass", 3)
    r.p(
        "YAML chỉ ghi đè các trường được khai báo. Trình đọc từ chối section lạ, "
        "sai kiểu, xác suất ngoài miền hoặc các kết hợp không hỗ trợ. Bảng dưới "
        "liệt kê cả trường không xuất hiện trong default.yaml nhưng có mặc định "
        "trong dataclass; dấu gạch dài nghĩa là giá trị tùy chọn chưa được đặt."
    )
    defaults = SessionConfig()
    descriptions = {
        "seed": "Seed duy nhất của phiên mô phỏng",
        "n_pulses": "Số xung BB84",
        "p_z": "Xác suất chọn cơ sở Z",
        "test_fraction": "Tỷ lệ bit công khai",
        "k_min": "Cỡ mẫu PE tối thiểu",
        "q_max": "Ngưỡng QBER cận trên",
        "eps_pe": "Ngân sách cận ước lượng",
        "eps_sec": "εPA trong công thức ℓ",
        "eps_cor": "Cận trùng thẻ xác minh",
        "ec_mode": "Cascade hoặc EC lý tưởng",
        "f_ec_ideal": "Hệ số rò EC lý tưởng",
        "backend": "NumPy hoặc Aer",
        "cascade_passes": "Số lượt Cascade",
        "basis_source": "Cơ sở từ NumPy hoặc Aer Hadamard",
        "length_km": "Chiều dài sợi mỗi nhánh",
        "alpha_db_per_km": "Suy hao dB/km",
        "e_misalign": "Xác suất lỗi lệch trục",
        "depol": "Xác suất khử cực",
        "bitflip": "Xác suất lật bit",
        "misalignment_theta": "Góc radian thay e_misalign",
        "eta_det": "Hiệu suất detector",
        "p_dark": "Xác suất đếm tối mỗi cổng",
        "kind": "Loại nguồn hoặc tấn công",
        "mu": "Photon trung bình của xung yếu",
        "p": "Tỷ lệ chặn",
        "basis_mode": "Cơ sở đo Eve",
        "n_pairs": "Số cặp E91",
        "visibility": "Độ hiển thị Werner",
        "chsh_z": "Hệ số sai số chuẩn CHSH",
        "detector": "Bộ phát hiện giám sát",
        "alpha": "Ngân sách báo động nhầm",
        "beta": "Ngân sách bỏ sót thiết kế SPRT",
        "e0": "QBER nền",
        "e1": "QBER giả thuyết thay thế",
        "window_size": "Số bit công khai mỗi cửa sổ",
        "max_seconds": "Tuổi khóa tối đa giây",
        "max_msgs": "Giới hạn thông điệp",
        "lockdown_after": "Số lần dừng liên tiếp để khóa",
        "backoff_seconds": "Hệ số chờ thử lại",
        "cipher": "Thuật toán cấu hình",
        "chunk_size": "Byte bản rõ mỗi khối",
        "max_bytes_per_key": "Ngân sách byte theo khóa",
    }
    for section in fields(defaults):
        value = getattr(defaults, section.name)
        if is_dataclass(value):
            rows = [
                (
                    f"{section.name}.{f.name}",
                    str(f.type)
                    .replace("None", "tùy chọn")
                    .replace("<class '", "")
                    .replace("'>", "")
                    .replace("typing.", ""),
                    fmt(getattr(value, f.name)),
                    descriptions[f.name],
                )
                for f in fields(value)
            ]
        else:
            rows = [
                (section.name, str(section.type), value, descriptions[section.name])
            ]
        r.table(
            f"Trường cấu hình nhóm {section.name}",
            ["Trường", "Kiểu", "Mặc định", "Ý nghĩa"],
            rows,
            source="src/qkdsim/config.py; configs/default.yaml.",
            widths=[4.5, 3.8, 2.7, 5],
        )
    r.p(
        "Một số giá trị được schema chấp nhận là điểm mở rộng. crypto.cipher có "
        "nhãn otp nhưng container chỉ ánh xạ AES-GCM và ChaCha20-Poly1305; pns "
        "chưa có đường mô phỏng hoạt động. Chọn chế độ mã hóa qua CLI cần dùng "
        "tham số cipher được công bố, không mặc định rằng mọi nhãn schema đã có "
        "triển khai tương ứng."
    )
    r.h("2.4.3 Định dạng nhị phân QKDH", 3)
    r.p(
        "QKDH phiên bản 1 dùng số nguyên big-endian. Header có cấu trúc "
        ">4sBB16s16s16s4sIQ, lưu mã thuật toán và metadata công khai. Hai UUID "
        "lần lượt nhận diện phiên và khóa; salt phục vụ HKDF, prefix phục vụ nonce. "
        "Mã thuật toán là 1 cho AES-256-GCM và 2 cho ChaCha20-Poly1305."
    )
    from qkdsim.crypto import container

    schema = [
        ("magic", 4, "QKDH"),
        ("version", 1, "Phiên bản định dạng"),
        ("cipher_id", 1, "Mã AEAD"),
        ("session_id", 16, "UUID phiên"),
        ("key_id", 16, "UUID tra khóa"),
        ("salt", 16, "Ngẫu nhiên OS cho HKDF"),
        ("nonce_prefix", 4, "Tiền tố nonce"),
        ("chunk_size", 4, "Kích thước khối"),
        ("orig_size", 8, "Số byte bản rõ"),
    ]
    offset = 0
    header_rows = []
    for name, size, meaning in schema:
        header_rows.append((name, offset, size, meaning))
        offset += size
    if offset != container._HEADER.size:
        raise ValueError("Report header schema no longer matches implementation")
    r.table(
        "Các trường header QKDH v1",
        ["Trường", "Offset byte", "Số byte", "Ý nghĩa"],
        header_rows,
        source="src/qkdsim/crypto/container.py:_HEADER.",
        widths=[3.8, 2.5, 2, 7.7],
    )
    r.eq("nkhối = max(1, ceil(B/chunk_size));  Btệp = Bheader + B + nkhối × (8 + 16)")
    r.p(
        "Mỗi bản ghi chứa counter 8 byte, bản mã và thẻ 16 byte. AAD ghép nguyên "
        "văn header, counter, chỉ số khối 64 bit và cờ cuối. Tệp rỗng vẫn có một "
        "bản ghi xác thực rỗng. Mặc định chia 65.536 byte; cỡ khối đọc từ ngoài "
        "bị chặn ở 16 MiB. Mỗi khóa bị giới hạn số thông điệp và tổng byte, trong "
        "đó giới hạn mặc định của NonceSequence là 2²⁰ thông điệp và trần cứng "
        "2³², dù trường counter có 64 bit."
    )
    r.p(
        "Bên giải mã tra khóa bằng key_id trước khi có thể kiểm tra thẻ header; "
        "provider chỉ nên tra cứu khóa đã được cấp, không thực hiện hành động "
        "tin cậy dựa trên metadata chưa xác thực. Chỉ sau kiểm tra kích thước, "
        "thứ tự từng counter, mọi tag và EOF, tệp tạm mới thay thế đích. Cơ chế "
        "này ngăn công bố tệp giải mã dở khi một khối cuối bị hỏng."
    )
    r.h("2.4.4 Nhật ký JSONL bằng chứng và metadata thực nghiệm", 3)
    r.p(
        "Mỗi dòng JSONL là một Event hoàn chỉnh với schema_version, timestamp, "
        "session_id, previous_state, state, alert, reason, counters, metrics và "
        "detector. counters chứa sent/detected/sifted/double_clicks/compared/errors; "
        "metrics giữ các tỷ lệ quan sát. JSON nghiêm ngặt không cho số không hữu "
        "hạn. evidence.json bổ sung windows, baseline và đường dẫn plot, chỉ chứa "
        "quan sát công khai, không chứa mảng khóa hoặc dữ liệu Eve riêng."
    )
    r.p(
        "CSV dùng schema metric/series/x/value/low/high/n/reference và các cột "
        "đặc thù. JSON bên cạnh ghi cấu hình, seed, SeedSequence spawn_key, commit, "
        "git_dirty, phiên bản, CSV SHA-256 và danh sách hình. Kết quả từ nhiều "
        "commit được xem là các lượt chạy lịch sử; môi trường dựng báo cáo được "
        "ghi riêng. Khi dùng entropy OS cho PA, nonce, salt hay đo thời gian, "
        "cùng seed không đảm bảo đầu ra byte hoặc benchmark giống hệt."
    )
    r.h("2.5 Xây dựng chương trình")
    r.h("2.5.1 Kiến trúc tổng thể", 3)
    r.p(
        "Kiến trúc tách lớp giao diện, điều phối, quan sát vật lý, hậu xử lý và "
        "mật mã ứng dụng. Các hàm miền nghiệp vụ không phụ thuộc trình dựng báo "
        "cáo. experiments/ gọi API để lưu bằng chứng; tools/build_report_docx.py "
        "chỉ đọc bằng chứng đó và kết hợp phần mô tả mã nguồn. Cấu trúc này cho "
        "phép kiểm tra tính đúng của mô hình riêng với kiểm tra toàn vẹn tệp."
    )
    r.flow(
        "08_architecture",
        "Kiến trúc chương trình và đường đi của dữ liệu",
        [
            "Giao diện: Typer CLI | D1 Chat | D2 File | Experiments",
            "Cấu hình và RNG → simulation.py điều phối",
            "Vật lý + BB84/E91 (NumPy / Aer) → quan sát",
            "Auth + Monitor + Postprocess → khóa hoặc bằng chứng dừng",
            "KeyStore → HKDF → AEAD → QKDH / TCP loopback",
            "Analysis + CSV/JSON/PNG → trình dựng báo cáo DOCX",
        ],
        "src/qkdsim/; demos/; experiments/; tools/build_report_docx.py",
    )
    r.h("2.5.2 Tổ chức thư mục", 3)
    tree = []
    purposes = {
        "configs": "cấu hình phiên và thực nghiệm",
        "src": "gói qkdsim",
        "experiments": "bộ chạy và phân tích E1–E15",
        "demos": "ứng dụng D1/D2",
        "tests": "unit, integration, statistical",
        "results": "bằng chứng đã lưu",
        "docs": "lý thuyết, tài liệu, báo cáo",
        "tools": "dựng và kiểm tra báo cáo",
    }
    for name, meaning in purposes.items():
        base = ROOT / name
        if base.exists():
            tree.append(f"{name}/  # {meaning}")
            for child in sorted(base.iterdir()):
                if child.is_dir() and not child.name.startswith((".", "__")):
                    tree.append(f"  {child.name}/")
    r.code("\n".join(tree))
    r.source("cây thư mục được quét trực tiếp khi dựng báo cáo.")
    r.h("2.5.3 Các module chính và lệnh CLI", 3)
    module_rows = [
        (
            "config.py; rng.py",
            "YAML, seed",
            "Config, Generator, byte OS",
            "Miền giá trị; tách RNG",
        ),
        (
            "physics/; protocols/",
            "Config và Generator",
            "Quan sát đo",
            "Suy hao; backend; oracle",
        ),
        (
            "simulation.py",
            "Quan sát và chính sách",
            "Khóa hoặc bằng chứng",
            "Các cổng dừng; ranh giới Eve",
        ),
        (
            "postprocess/",
            "Bit đã giữ và mẫu công khai",
            "Khóa rút gọn",
            "Rò parity; verify; ℓ; FFT",
        ),
        (
            "monitor/",
            "Mẫu công khai, nền",
            "Quyết định, log",
            "Ngân sách α/β; rekey/lockdown",
        ),
        (
            "auth/",
            "Khóa chia sẻ, khung",
            "Thông điệp đã xác thực",
            "Thẻ, phiên, chiều, thứ tự",
        ),
        (
            "crypto/",
            "Khóa, tệp, AAD",
            "Bản mã/bản rõ",
            "Nonce, hạn mức, xuất tệp nguyên vẹn",
        ),
        (
            "analysis/; qrng.py",
            "Mẫu và tham số",
            "Oracle, CI, p-value",
            "Giả thiết, cỡ mẫu, QRNG mô phỏng",
        ),
        (
            "cli.py; file_demo.py",
            "Tham số người dùng",
            "JSON công khai, tệp",
            "Không lộ khóa; sidecar demo",
        ),
    ]
    r.table(
        "Đầu vào đầu ra và điểm kiểm tra của các module chính",
        ["Module", "Đầu vào", "Đầu ra và vai trò", "Điểm kiểm tra"],
        module_rows,
        source="src/qkdsim/; mô tả chi tiết vai trò ở mục 2.3.",
        widths=[3.8, 3.4, 4.3, 4.5],
    )
    r.table(
        "Các lệnh CLI và ý nghĩa kết quả",
        ["Lệnh qua uv run", "Vai trò", "Điểm cần chú ý"],
        [
            (
                "qkdsim bb84 --config configs/default.yaml",
                "BB84 đến PE",
                "accepted chưa có nghĩa là khóa cuối",
            ),
            (
                "qkdsim e91 --config configs/e91_default.yaml",
                "CHSH và hậu xử lý có HMAC",
                "Đọc cả chsh_lower và status",
            ),
            (
                "qkdsim monitor --detector sprt",
                "BB84 đầy đủ, log và policy",
                "Bằng chứng trong thư mục UUID",
            ),
            (
                "qkdsim calibrate --output calibration.json",
                "Đo nền không Eve",
                "Nền chỉ hợp mô hình hiệu chuẩn",
            ),
            (
                "qkdsim encrypt --in input.bin --out output.qkdh",
                "Demo tệp",
                "Khóa demo sidecar chỉ dùng cục bộ",
            ),
            (
                "qkdsim decrypt --in output.qkdh --out restored.bin",
                "Kiểm tra và khôi phục",
                "Cần cùng tệp khóa demo",
            ),
            (
                "qkdsim experiment E3 --quick",
                "Chạy riêng E3",
                "Chỉ dùng khi chủ động tạo bộ mới",
            ),
            (
                "qkdsim experiments --all --quick",
                "Chạy E1–E15",
                "Không chạy trong quá trình dựng báo cáo",
            ),
        ],
        source="src/qkdsim/cli.py; file_demo.py.",
        widths=[7.6, 3.7, 4.7],
    )


EXPERIMENT_TEXT = [
    (
        "QBER theo tỷ lệ chặn và nhiễu",
        "Đo QBER khi thay đổi p và nhiễu nền; đối chiếu fast với các điểm Aer nhỏ.",
        "Q = e + p/4 − 2e(p/4). Cỡ mẫu Aer khác fast; "
        "khoảng tin cậy trong CSV mô tả trung bình qua các lần lặp.",
    ),
    (
        "Nhiễu và xác suất dừng phiên",
        "Đo xác suất dừng và số bit cuối theo nhiễu và q_max, dùng EC lý tưởng.",
        "Qub = Q̂ + √[ln(1/εPE)/(2k)]. Dừng có thể do "
        "cận QBER hoặc độ dài không dương; tỷ lệ dừng không chỉ đo "
        "một ngưỡng tiệm cận.",
    ),
    (
        "Cỡ mẫu và xác suất phát hiện Eve",
        "Lấy mẫu nhị thức sai khác trên k bit với Eve chặn toàn phần và kênh lý tưởng.",
        "P = 1 − (3/4)ᵏ. Phát hiện một "
        "lỗi không phải tiêu chuẩn phù hợp khi kênh trung thực đã có nhiễu.",
    ),
    (
        "Số bit qua chuỗi hậu xử lý",
        "Theo dõi sàng lọc, hiệu chỉnh, khóa cuối và fEC với Cascade thực và xác minh.",
        "ℓ trừ lượng rò quan sát, thẻ xác minh "
        "và chi phí PA. Phiên dừng đóng góp số bit cuối bằng không; fEC không xác "
        "định khi entropy mẫu bằng không.",
    ),
    (
        "Hiệu ứng khóa hữu hạn",
        "Giữ QBER nền cố định, thay đổi số xung và đối "
        "chiếu tốc độ ℓ/N với mốc tiệm cận.",
        "Mốc có cùng tỷ lệ sàng lọc và tỷ lệ "
        "bit mẫu. EC lý tưởng giúp tách chi phí cận thống kê; không đại diện "
        "benchmark Cascade.",
    ),
    (
        "Tốc độ khóa theo khoảng cách",
        "Đánh giá đường tiệm cận BB84 WCP, mồi "
        "chân không–yếu và E91 theo suy hao và đếm tối.",
        "η = ηd10^(−αL/10). L là "
        "chiều dài mỗi nhánh E91, tốc độ tính theo cặp phát. WCP bỏ qua PNS là "
        "mốc lạc quan; cận mồi là mô hình giải tích, chưa có giao thức decoy đầy đủ.",
    ),
    (
        "CHSH theo Werner và Eve",
        "Đo S, QBER cặp khóa, tỷ lệ dừng cổng Bell và "
        "tỷ lệ quan sát vi phạm Bell trên fast và Aer.",
        "S = 2√2V khi không có "
        "nhiễu khác; IR toàn phần Z/X làm giảm S còn một nửa. Cổng dùng S − zσS, "
        "khác với chỉ kiểm tra S > 2.",
    ),
    (
        "So sánh BB84 và E91",
        "Dùng cùng số lượt phát và xác suất lật bit, đo "
        "sàng lọc, dừng, bit/lượt và thời gian phiên NumPy.",
        "Mốc sàng lọc là "
        "1/2 cho BB84 trên lượt dò và 2/9 cho E91 trên cặp trùng phùng. Thời gian "
        "gồm đường xử lý thực và kết thúc sớm, dùng EC lý tưởng; chưa chuẩn hóa "
        "thành chi phí hạ tầng quang học.",
    ),
    (
        "Hiệu năng hai AEAD",
        "Đo container trên văn bản, PNG hợp lệ có phần "
        "đệm và dữ liệu ngẫu nhiên; có làm nóng trước đo.",
        "MB/s = byte/(giây × "
        "10⁶). low/high là IQR, không phải khoảng tin cậy. Số đo bao gồm I/O, "
        "HKDF và chunking; không chỉ đo lõi AES hoặc ChaCha.",
    ),
    (
        "Toàn vẹn dữ liệu đầu cuối",
        "Mỗi lần lặp chạy BB84 có HMAC, mã hóa, giải mã và đối chiếu SHA-256 tệp.",
        "Khứ hồi bằng nhau là điều kiện "
        "đúng chức năng; không phải chứng minh bí mật khóa mô phỏng. Thời gian "
        "mã hóa/giải mã chỉ tổng hợp các phiên có khóa.",
    ),
    (
        "Sửa tệp và tái sử dụng nonce",
        "Thử sửa header, bản mã, tag, cắt tệp, "
        "đảo khối; thử lặp nonce trên khóa riêng.",
        "Khi lặp (K,N), phần bản mã "
        "có C₁ XOR C₂ = M₁ XOR M₂. nonce_leak đo quan sát rò, còn tamper đo số "
        "lượt từ chối; hai giá trị bằng một mang ý nghĩa khác nhau.",
    ),
    (
        "MITM kênh cổ điển",
        "Eve đóng hai vai trên hai liên kết độc lập, so "
        "khóa hai đầu ra PA và số lần cả hai phía từ chối HMAC.",
        "QKD cần xác "
        "thực kênh cổ điển. Tỷ lệ thành công hữu hạn đi kèm Clopper–Pearson, "
        "không suy diễn xác suất tấn công tổng quát bằng đúng không.",
    ),
    (
        "So sánh bộ phát hiện và ROC",
        "Quét Threshold, CI, SPRT, CUSUM, Joint "
        "trên nền trung thực, IR đều và IR dồn cuối.",
        "SPRT dùng biên Wald; "
        "CUSUM có thể theo dõi thay đổi muộn sau khi SPRT đã chấp nhận H₀. Độ "
        "trễ tính từ đầu mẫu và chỉ tổng hợp lần có báo động; FPR bằng không "
        "trên mẫu hữu hạn vẫn có cận trên dương.",
    ),
    (
        "Chẩn đoán ngẫu nhiên và QRNG",
        "So khóa thô, khóa cuối, NumPy, Aer "
        "Hadamard và secrets bằng năm phép thử SP 800-22.",
        "p-value đánh giá "
        "mức phù hợp mẫu với giả thuyết kiểm định. Min-entropy ở đây là "
        "−log₂(max(p̂₀,p̂₁)); chuỗi có phụ thuộc có thể vẫn cân bằng. Aer là bộ "
        "mô phỏng giả ngẫu nhiên, không phải nguồn entropy vật lý.",
    ),
    (
        "Mức an toàn lượng tử theo mô hình",
        "Đọc bảng chi phí cổ điển và mô "
        "hình Grover/Shor từ CSV được tạo bởi mã phân tích.",
        "Grover có số mũ "
        "truy vấn k/2 khi khóa có entropy k bit; RSA/ECC có mô hình Shor đa thức "
        "nên không gán số mũ truy vấn tương tự. Không đo máy lượng tử thực.",
    ),
]


def selected_rows(rows: list[Row], number: int) -> list[Row]:
    """Select endpoints per metric/series, then round-robin across those groups.

    All rows are parsed and included in the manifest digest. E13 displays its
    design and false-alarm summaries, E14 all per-test pass rates. Other long
    tables show at most 24 representative records, never invented aggregates.
    """
    if number == 9:
        sizes = [float(row["x"]) for row in rows]
        return [
            row
            for row in rows
            if row["metric"] in ("encrypt_mbps", "decrypt_mbps")
            and float(row["x"]) in (min(sizes), max(sizes))
        ]
    if number == 7:
        rows = [row for row in rows if row["metric"] in ("chsh", "qber")]
    if len(rows) <= 24:
        return rows
    if number == 13:
        return [
            row
            for row in rows
            if row["metric"] in ("design_power", "design_bits", "fpr", "threshold_fpr")
        ][:48]
    if number == 14:
        return [row for row in rows if row["metric"] == "pass"]
    groups: dict[tuple[str, str], list[Row]] = {}
    for row in rows:
        groups.setdefault((row["metric"], row["series"]), []).append(row)
    chosen = []
    for side in (0, -1):
        for values in groups.values():
            row = values[side]
            if row not in chosen:
                chosen.append(row)
    return chosen[: 32 if number in (4, 8) else 24]


def experiment(r: Report, number: int, base: Path) -> None:
    """Read stored measurements, check metadata binding and embed the real PNG."""
    matches = sorted(base.glob(f"E{number:02}_*.csv"))
    if len(matches) != 1:
        raise ValueError(f"Need one CSV for E{number:02} in {base}")
    path = matches[0]
    rows = read_csv(path)
    metadata = read_json(path.with_suffix(".json"))
    if metadata.get("csv_sha256") != digest(path):
        raise ValueError(f"CSV provenance mismatch: {path}")
    title, objective, interpretation = EXPERIMENT_TEXT[number - 1]
    r.sub(f"E{number} {title}", f"Mục tiêu: {objective}")
    options = metadata["config"]
    r.p(
        "Thiết lập/đầu vào: "
        + "; ".join(
            f"{key}={json.dumps(value, ensure_ascii=False)}"
            for key, value in options.items()
        )
        + f". Hồ sơ quick={fmt(metadata.get('quick'))}; seed={metadata.get('seed')}; "
        f"cấu hình chạy lưu tại {rel(path.with_suffix('.json'))}."
    )
    display = selected_rows(rows, number)
    headers = ["Đại lượng / chuỗi", "x", "Giá trị", "low / high", "n / mốc"]
    r.table(
        f"E{number} số liệu đọc từ bộ {base.relative_to(ROOT / 'results').as_posix()}",
        headers,
        [
            (
                f"{row['metric']}\n{row['series']}",
                row["x"],
                row["value"],
                f"{fmt(row.get('low'))} / {fmt(row.get('high'))}",
                f"{fmt(row.get('n'))} / {fmt(row.get('reference'))}",
            )
            for row in display
        ],
        source=f"{rel(path)}; {rel(path.with_suffix('.json'))}.",
        widths=[5.4, 2.1, 2.4, 3.4, 2.7],
    )
    if len(display) < len(rows):
        methods = {
            4: "đầu/cuối mỗi nhóm metric/series, tối đa 32 hàng",
            7: "đầu/cuối mỗi nhóm CHSH và QBER",
            8: "đầu/cuối mỗi nhóm metric/series, tối đa 32 hàng",
            9: "thông lượng mã hóa/giải mã ở cỡ tệp nhỏ nhất và lớn nhất",
            13: "các hàng điểm thiết kế và tỷ lệ báo động nhầm, tối đa 48 hàng",
            14: "toàn bộ hàng tỷ lệ đạt của từng phép thử",
        }
        method = methods.get(number, "đầu/cuối mỗi nhóm metric/series, tối đa 24 hàng")
        r.p(
            f"Bảng trình bày {len(display)}/{len(rows)} bản ghi bằng quy tắc chọn "
            f"{method}. Toàn bộ bản ghi gốc được đọc, kiểm tra hash và được thể hiện "
            "trong biểu đồ cùng tên; dữ liệu chi tiết giữ tại CSV nguồn."
        )
    r.fig(
        f"E{number} {title}",
        path.with_suffix(".png"),
        f"{rel(path.with_suffix('.png'))}; biểu đồ đã lưu từ CSV cùng tên.",
    )
    r.p("Đối chiếu lý thuyết và nhận xét: " + interpretation)
    if number == 5:
        last = max(rows, key=lambda row: float(row["x"]))
        r.p(
            f"Ở số xung lớn nhất N={last['x']}, tốc độ hữu hạn quan sát "
            f"là {fmt(last['value'])} bit/xung, so với mốc {fmt(last['reference'])}. "
            "Độ chênh phản ánh chi phí mẫu hữu hạn trong cấu hình này, không "
            "phải một hằng số hiệu suất cho mọi kênh."
        )
    if number == 6:
        r.p(
            "Điểm triệt tiêu được tìm thêm ngoài lưới hình: "
            + "; ".join(
                f"{row['series']} tại {fmt(row['value'])} km "
                f"(giới hạn tìm {row.get('search_limit', '—')} km)"
                for row in rows
                if row["metric"] == "cutoff_km"
            )
            + ". "
            "Các giá trị này thuộc mô hình tiệm cận, không phải cự ly "
            "truyền đã đo trên thiết bị."
        )
    if number == 13:
        r.p(
            "Tại điểm thiết kế, số bit quyết định trung bình: "
            + "; ".join(
                f"{row['series']}: {fmt(row['value'])} bit"
                for row in rows
                if row["metric"] == "design_bits"
            )
            + ". "
            "Cần đối chiếu đồng thời design_power và FPR trước khi chọn "
            "bộ phát hiện có số bit thấp hơn."
        )
    if number == 14:
        passes = [row for row in rows if row["metric"] == "pass"]
        passed = sum(int(float(row["successes"])) for row in passes)
        total = sum(int(float(row["n"])) for row in passes)
        r.p(
            f"Toàn bộ bảng tỷ lệ đạt ghi {passed}/{total} phép thử riêng lẻ "
            "đạt ngưỡng. Tính nhiều phép thử làm xuất hiện một số kết quả "
            "không đạt ngay cả dưới nguồn phù hợp giả thuyết; kết luận cần "
            "xét cỡ mẫu và tính độc lập giữa các phép thử."
        )
    comparisons = [
        row
        for row in rows
        if all(
            row.get(key) not in (None, "")
            for key in ("low", "high", "reference", "value")
        )
    ]
    if comparisons and number not in (5, 9, 14):
        outside = sum(
            not float(row["low"]) <= float(row["reference"]) <= float(row["high"])
            for row in comparisons
        )
        r.p(
            f"Kiểm tra trực tiếp CSV cho {outside}/{len(comparisons)} mốc tham chiếu "
            "nằm ngoài khoảng low/high tương ứng. Đây là các khoảng riêng lẻ, chưa "
            "hiệu chỉnh nhiều phép so sánh; kết quả này không phải kiểm định chung "
            "về tương đương hai backend."
        )
    if number in (10, 11, 12):
        counts = [
            f"{row['series']} / {row['x']}: {row['successes']}/{row['n']}"
            for row in rows
            if row.get("successes")
        ]
        r.p("Số lượt quan sát theo điều kiện: " + "; ".join(counts) + ".")


def acceptance(r: Report, name: str) -> None:
    """Present retained acceptance JSON using its own historical setup."""
    path = ROOT / "results" / f"{name}.json"
    data = read_json(path)
    r.p(
        f"Bổ sung nghiệm thu từ {rel(path)}; Python {data.get('python', 'không ghi')}; "
        f"commit {data.get('git_commit', 'không ghi')}; "
        f"working tree có thay đổi: {fmt(data.get('git_dirty'))}. "
        "Đây là lượt chạy lịch sử, được giữ tách với bộ quick."
    )
    if name == "bb84_backend_scaling":
        r.table(
            "Thời gian mô phỏng BB84 theo backend và quy mô",
            ["Backend", "Xung", "depol", "Trung vị giây", "Lượt đo"],
            [
                (
                    s["config"]["bb84"]["backend"],
                    s["config"]["bb84"]["n_pulses"],
                    s["config"]["channel"]["depol"],
                    s["median_seconds"],
                    len(s["seconds"]),
                )
                for s in data["samples"]
            ],
            source=rel(path),
            widths=[2.3, 2.5, 2.5, 4.4, 4.3],
        )
        r.p(
            "Phép đo có làm nóng từng backend. NumPy xử lý mảng tuyến tính theo "
            "số xung; stabilizer nhiều qubit có chi phí bộ nhớ tăng nhanh hơn. "
            "Bảng thời gian này đánh giá quy mô, còn tính tương đương phân phối "
            "được kiểm tra bởi E1 và kiểm thử thống kê, không suy ra từ tốc độ."
        )
    elif name == "bb84_postprocessing":
        cascade = data["cascade"]
        r.p(
            "Cấu hình Cascade nghiệm thu: "
            + json.dumps(cascade["config"], ensure_ascii=False)
            + "."
        )
        r.table(
            "Nghiệm thu đồng bộ Cascade và hiệu suất rò",
            ["QBER", "Thành công", "Tỷ lệ", "fEC lớn nhất"],
            [
                (row["qber"], row["successes"], row["success_rate"], row["max_f_ec"])
                for row in cascade["samples"]
            ],
            source=rel(path),
        )
        pa = data["privacy_amplification"]
        r.table(
            "Thời gian Toeplitz FFT ở cấu hình nghiệm thu",
            ["n đầu vào", "ℓ đầu ra", "Lượt", "Giây"],
            [
                (pa["config"]["n"], pa["config"]["length"], i + 1, seconds)
                for i, seconds in enumerate(pa["seconds"])
            ],
            source=rel(path),
        )
        r.p(
            f"Trung vị PA là {fmt(pa['median_seconds'])} giây tại cấu hình trên. "
            "Đo PA độc lập với đầu ra bằng đầu vào nhằm đánh giá hiệu năng phép "
            "băm; không hàm ý phiên QKD được phép giữ toàn bộ số bit mà không "
            "trừ lượng rò. Tỷ lệ Cascade chỉ áp dụng cho cấu hình và số lượt đã lưu."
        )
    elif name == "e91_acceptance":
        r.table(
            "Nghiệm thu E91 và đối chiếu dung sai giải tích",
            ["Backend / Eve", "V", "S / lý thuyết", "QBER khóa", "Qua CHSH / 4σ"],
            [
                (
                    f"{p['config']['e91']['backend']} / "
                    f"{p['config']['attack']['kind']}:{p['config']['attack']['basis_mode']}",
                    p["config"]["e91"]["visibility"],
                    f"{fmt(p['chsh']['s'])} / {fmt(p['expected_s'])}",
                    p["key_pair_qber"],
                    f"{fmt(p['passes_chsh_gate'])} / "
                    f"{fmt(p['s_within_4_sigma'] and p['qber_within_4_sigma'])}",
                )
                for p in data["points"]
            ],
            source=rel(path),
            widths=[4.8, 1, 4.1, 2.8, 3.3],
        )
        r.p(
            "Cột 4σ yêu cầu đồng thời S và QBER nằm trong dung sai của oracle. "
            "Vượt kiểm tra mô hình không đồng nghĩa vượt cổng cấp khóa: điểm có "
            "Eve có thể khớp rất tốt mô hình tấn công và vẫn phải dừng."
        )
    elif name == "e12_mitm":
        r.table(
            "MITM trên hai liên kết khi bật và tắt HMAC",
            [
                "Chế độ",
                "Lượt / Eve thành công",
                "Tỷ lệ",
                "CP thấp / cao",
                "Hai thẻ bị từ chối",
            ],
            [
                (
                    mode,
                    f"{point['trials']} / {point['eve_successes']}",
                    point["eve_success_rate"],
                    " / ".join(fmt(v) for v in point["eve_success_clopper_pearson"]),
                    point["both_links_rejected_bad_tags"],
                )
                for mode, point in data["modes"].items()
            ],
            source=rel(path),
            widths=[3.1, 3.2, 1.8, 4.2, 3.7],
        )
    elif name == "randomness_acceptance":
        r.table(
            "Nghiệm thu các phép thử ngẫu nhiên trên cùng độ dài mẫu",
            ["Nguồn", "Số bit", "Min-entropy biên", "p-value nhỏ nhất", "Dưới α"],
            [
                (
                    label,
                    point["bit_count"],
                    point["min_entropy"],
                    min(v for v in point["p_values"].values() if v is not None),
                    ", ".join(point["below_alpha"]) or "Không có",
                )
                for label, point in data["samples"].items()
            ],
            source=rel(path),
            widths=[4.8, 2, 3.2, 3, 3],
        )
        r.p(
            "Ngưỡng từng phép thử và cấu hình được đọc từ hồ sơ nghiệm thu: "
            + json.dumps(data["config"].get("alpha_per_test"))
            + ". Năm phép thử "
            "không đại diện toàn bộ bộ kiểm tra SP 800-22 và không chứng minh "
            "không thể dự đoán khóa mô phỏng."
        )


def validation_results(r: Report) -> None:
    """Read real test artifacts; never convert an unexecuted check into a pass."""
    rows: list[tuple[object, ...]] = []
    junit = VALIDATION / "pytest.xml"
    if junit.exists():
        tree = ET.parse(junit)
        suites = list(tree.getroot().iter("testsuite"))
        totals = {
            key: sum(int(s.get(key, "0")) for s in suites)
            for key in ("tests", "failures", "errors", "skipped")
        }
        rows.append(("pytest", json.dumps(totals, ensure_ascii=False), rel(junit)))
    else:
        rows.append(
            (
                "pytest",
                "Chưa có biên bản chạy trong lần dựng này",
                "tests/ chỉ là mã kiểm thử",
            )
        )
    coverage = VALIDATION / "coverage.json"
    if coverage.exists():
        cov = read_json(coverage)["totals"]
        rows.append(
            (
                "coverage src/qkdsim",
                f"{cov['percent_covered']:.2f}% "
                f"({cov['covered_lines']}/{cov['num_statements']} dòng)",
                rel(coverage),
            )
        )
    for name in ("ruff", "mypy"):
        path = VALIDATION / f"{name}.log"
        if path.exists():
            content = path.read_text(encoding="utf-8-sig", errors="replace")
            # PowerShell redirection under Windows PowerShell 5 may use UTF-16.
            if "\x00" in content or content.startswith("��"):
                content = path.read_text(encoding="utf-16")
            success = (
                "All checks passed!" in content
                if name == "ruff"
                else "Success:" in content
            )
            rows.append(
                (
                    name,
                    content.strip() if success else "Có lỗi; xem biên bản nguồn",
                    rel(path),
                )
            )
        else:
            rows.append((name, "Chưa có biên bản chạy", "Không suy diễn từ cấu hình"))
    r.table(
        "Kết quả kiểm thử và kiểm tra tĩnh đã thực thi",
        ["Công cụ", "Kết quả đọc từ biên bản", "Nguồn"],
        rows,
        widths=[3, 7.5, 5.5],
    )
    r.p(
        "Các kiểm thử bao gồm oracle giải tích, thuộc tính Hypothesis, tương "
        "đương backend, kiểm tra thống kê seed cố định, băm/hộp mật mã theo vector "
        "chuẩn và ca lỗi container/HMAC. Một kiểm thử thuộc tính hiện chấp nhận "
        "Cascade có thể còn lỗi chẵn để xác minh phát hiện, phù hợp với số lượt "
        "hữu hạn; không tuyên bố Cascade luôn hội tụ trên mọi chuỗi lỗi. "
        "Biên bản kiểm thử được tạo riêng, không chạy lại toàn bộ thực nghiệm."
    )


def chapter_three(r: Report, inputs: list[dict[str, object]]) -> None:
    """Evaluate existing result groups and preserve their scientific limitations."""
    r.h("CHƯƠNG 3. TRIỂN KHAI VÀ ĐÁNH GIÁ KẾT QUẢ", 1)
    r.h("3.1 Mô hình triển khai")
    r.h("3.1.1 Môi trường triển khai và nguồn dữ liệu", 3)
    r.p(
        f"Môi trường dựng báo cáo thực tế: {platform.platform()}; "
        f"kiến trúc {platform.machine()}; Python {platform.python_version()}. "
        "Đây là môi trường đọc kết quả và dựng tài liệu, cần phân biệt với "
        "phiên bản, commit và nền tảng đã lưu trong từng lượt đo lịch sử."
    )
    r.table(
        "Phiên bản thư viện trong môi trường dựng báo cáo",
        ["Thư viện", "Phiên bản thực tế"],
        installed().items(),
        source="importlib.metadata.version tại lúc chạy trình dựng.",
        widths=[7, 9],
    )
    primary = ROOT / "results/quick"
    candidates = [primary, *(ROOT / "results/selected").glob("**/*")]
    candidates = [p for p in candidates if p.is_dir() and list(p.glob("E??_*.csv"))]
    # Prefer completeness; tie-break to quick so historical sources remain stable.
    base = max(candidates, key=lambda p: (len(list(p.glob("E??_*.csv"))), p == primary))
    r.p(
        f"Bộ dữ liệu chính là {rel(base)}, được chọn vì có bộ E1–E15 đầy đủ nhất. "
        "results/selected/quick/ chỉ có E3 trong ảnh chụp kho hiện tại và được "
        "đối chiếu riêng, không trộn lần chạy mà bỏ nhãn nguồn. results/demo_chat/ "
        "cung cấp nhật ký và bằng chứng dừng D1; các tệp JSON/CSV gốc results/ "
        "cung cấp số liệu nghiệm thu từng hạng mục. Không chạy lại "
        "experiments/run_all.py "
        "để dựng báo cáo. Mô phỏng phần mềm và TCP loopback không đại diện thiết "
        "bị quang học hoặc kênh mạng diện rộng."
    )
    r.table(
        "Hồ sơ nguồn gốc các lượt thực nghiệm chính",
        ["Tệp metadata", "Seed", "Python / commit", "Thay đổi Git"],
        [
            (
                rel(path),
                fmt(data.get("seed", data.get("config", {}).get("seed"))),
                f"{data.get('python', 'không ghi')}\n"
                f"{data.get('git_commit', 'không ghi')}",
                fmt(data.get("git_dirty")),
            )
            for path in sorted((ROOT / "results").glob("*.json"))
            for data in [read_json(path)]
        ]
        + [
            (
                "results/quick/run_all.json",
                fmt(read_json(primary / "run_all.json").get("seed")),
                str(read_json(primary / "run_all.json").get("git_commit")),
                fmt(read_json(primary / "run_all.json").get("git_dirty")),
            )
        ],
        source="JSON gốc; danh sách đầy đủ và SHA-256 trong "
        "docs/report_build_manifest.json.",
        widths=[5.6, 2, 6.2, 2.2],
    )
    r.p(
        "Các lượt lịch sử đều giữ commit nền và cờ git_dirty khi có thay đổi chưa "
        "commit. Vì vậy commit riêng lẻ chưa đủ để tái tạo chính xác một working "
        "tree cũ. Manifest báo cáo ràng buộc nội dung hiện có bằng SHA-256, đồng "
        "thời giữ config và versions gốc thay vì ghi đè chúng bằng môi trường mới."
    )
    r.h("3.1.2 Công cụ sử dụng và kiểm chứng", 3)
    r.p(
        "Pytest thực thi các tầng unit/integration/statistical, Hypothesis sinh "
        "đầu vào cho thuộc tính bit, nonce, KDF và container; pytest-cov đo bao "
        "phủ src/qkdsim. Ruff kiểm tra mã và mypy --strict kiểm tra kiểu nguồn. "
        "experiments/run_all.py là bộ tạo kết quả có provenance; trình dựng "
        "không gọi bộ này. Bảng kiểm chứng tại mục 3.2.6 đọc biên bản thật của "
        "lần kiểm tra hiện hành, không lấy một con số mục tiêu làm kết quả."
    )
    r.h("3.1.3 Cấu hình hệ thống và lệnh Windows PowerShell", 3)
    r.code(
        "$env:UV_CACHE_DIR = Join-Path (Get-Location) '.uv-cache'\n"
        "$env:PYTHONIOENCODING = 'utf-8'\n"
        "uv sync --extra dev\n"
        "uv run qkdsim bb84 --config configs/default.yaml\n"
        "uv run qkdsim monitor --config configs/default.yaml\n"
        "uv run pytest --cov=src/qkdsim\n"
        "uv run ruff check .\n"
        "uv run mypy --strict src\n"
        "uv run --with python-docx==1.2.0 python tools/build_report_docx.py\n"
        "uv run --with python-docx==1.2.0 python "
        "tools/build_report_docx.py --check-only"
    )
    r.p(
        "configs/default.yaml dùng nguồn đơn photon, backend fast, hậu xử lý "
        "Cascade và detector SPRT. Các mặc định chi tiết đã được liệt kê ở "
        "mục 2.4.2. Để đối chiếu công thức lý tưởng cần tắt lệch trục, đếm tối "
        "và các nguồn nhiễu không nằm trong công thức; không sử dụng nền lệch "
        "trục mặc định cho một phép so sánh Werner thuần."
    )
    r.h("3.2 Kết quả thực nghiệm")
    r.p(
        "Trong bảng E1–E15, ký hiệu x, value, low, high, n và reference giữ "
        "ngữ nghĩa CSV gốc. Đại lượng tỷ lệ được ghi theo [0,1]; số bit, giây, "
        "ms, MB/s và km phụ thuộc metric. Dấu gạch dài chỉ ô không áp dụng hoặc "
        "không đủ thống kê; không thay bằng không. Trung bình dùng khoảng "
        "Student 95%, tỷ lệ dùng Clopper–Pearson 95%; riêng E9 dùng trung vị "
        "và IQR. Các giá trị hiển thị được làm tròn sáu chữ số có nghĩa, CSV "
        "nguồn giữ độ chính xác ban đầu."
    )
    groups = [
        (
            "3.2.1 Nhóm 1 Mô hình vật lý QBER nhiễu và xác suất phát hiện",
            [1, 2, 3],
            "bb84_backend_scaling",
        ),
        (
            "3.2.2 Nhóm 2 Hậu xử lý khóa hữu hạn và khoảng cách",
            [4, 5, 6],
            "bb84_postprocessing",
        ),
        ("3.2.3 Nhóm 3 Giao thức E91 và so sánh BB84 E91", [7, 8], "e91_acceptance"),
        ("3.2.4 Nhóm 4 AEAD toàn vẹn nonce và MITM", [9, 10, 11, 12], "e12_mitm"),
        (
            "3.2.5 Nhóm 5 Giám sát ngẫu nhiên và mức an toàn lượng tử",
            [13, 14, 15],
            "randomness_acceptance",
        ),
    ]
    for title, numbers, extra in groups:
        r.h(title, 3)
        for number in numbers:
            experiment(r, number, base)
        acceptance(r, extra)
        if numbers == [1, 2, 3]:
            for selected in sorted((ROOT / "results/selected").rglob("E03_*.csv")):
                equal = read_csv(selected) == read_csv(next(base.glob("E03_*.csv")))
                r.p(
                    f"Đối chiếu E3 tại {rel(selected)} với bộ chính: "
                    f"{'bản ghi bằng nhau' if equal else 'bản ghi khác nhau'}. "
                    "Hai bộ giữ provenance riêng dù giá trị có thể trùng nhau."
                )
                r.fig(
                    "E3 từ bộ selected để đối chiếu nguồn",
                    selected.with_suffix(".png"),
                    rel(selected.with_suffix(".png")),
                )
        if numbers == [13, 14, 15]:
            path = ROOT / "results/e15_quantum_security.csv"
            r.table(
                "Mức an toàn lượng tử từ bảng E15 nghiệm thu",
                ["Thuật toán", "Cỡ khóa", "Cổ điển", "Tấn công", "Số mũ truy vấn"],
                [
                    (
                        row["primitive"],
                        row["key_bits"],
                        row["classical_bits"],
                        row["quantum_attack"],
                        row["quantum_query_bits"],
                    )
                    for row in read_csv(path)
                ],
                source="results/e15_quantum_security.csv; "
                "results/e15_quantum_security.json.",
                widths=[4, 2.5, 2.5, 3, 4],
            )
            r.p(
                "Ô số mũ trống ở RSA/ECC biểu thị mô hình Shor đa thức. Các mức "
                "cổ điển của hai hệ này lấy từ bảng tương đương NIST ghi trong "
                "metadata E15. AES/ChaCha vẫn cần khóa đầu vào có entropy thực "
                "và kỷ luật nonce; không gán mức 128 bit thực tế cho khóa sinh "
                "từ mô phỏng chỉ vì tên thuật toán là AES-256."
            )
    r.h("3.2.6 Demo ứng dụng và kiểm thử tự động", 3)
    r.sub(
        "D1 Chat",
        "Mục tiêu là quan sát cấp khóa, gửi, rekey, bật Eve, chặn gửi "
        "và khôi phục trên TCP loopback. Không coi các log đã lưu là phép đo mạng WAN.",
    )
    logs = sorted((ROOT / "results/demo_chat").rglob("events.jsonl"))
    demo_rows = []
    for path in logs:
        events = [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        if events:
            last = events[-1]
            demo_rows.append(
                (
                    path.parent.name,
                    len(events),
                    last["state"],
                    last["alert"],
                    last.get("metrics", {}).get("qber"),
                )
            )
    r.table(
        "Các phiên demo chat đã lưu",
        ["Mã phiên", "Sự kiện", "Trạng thái cuối", "Mức", "QBER"],
        demo_rows,
        source="results/demo_chat/*/events.jsonl; không chứa nội dung khóa.",
        widths=[6.6, 1.6, 3, 2, 2.8],
    )
    evidence = sorted((ROOT / "results/demo_chat").rglob("evidence.json"))
    for path in evidence:
        data = read_json(path)
        r.p(
            f"Phiên {path.parent.name}: lý do dừng {data['reason']}; "
            f"đã so sánh {data['counters']['compared']} bit; "
            f"QBER={fmt(data['metrics'].get('qber'))}; "
            f"quyết định {data.get('detector', {}).get('outcome', 'không có')}. "
            f"Căn cứ: {rel(path)}."
        )
        r.fig(
            f"Bằng chứng QBER của phiên chat {path.parent.name}",
            path.parent / data["plot"],
            rel(path),
        )
    r.p(
        "Các nhật ký cung cấp bằng chứng chuyển trạng thái và dừng do quan sát "
        "công khai. Chúng không lưu toàn bộ bản rõ chat, nên không suy ra số "
        "tin giao thành công chỉ từ số phiên KEY_IN_USE. Hàm self_test trong "
        "demos/secure_chat.py kiểm tra gửi, rekey và khôi phục bằng assert; "
        "khi không có biên bản chạy riêng, báo cáo chỉ mô tả hợp đồng này."
    )
    r.sub(
        "D2 File",
        "demos/file_encrypt_demo.py cung cấp lệnh self-test cho khứ hồi "
        "hai AEAD. E10 và kiểm thử integration cung cấp số liệu đã lưu về "
        "SHA-256 và xử lý lỗi. Không tạo một bộ số đo D2 độc lập khi kho chưa có "
        "biên bản tương ứng.",
    )
    r.code(
        "uv run python demos/secure_chat.py --self-test\n"
        "uv run python demos/file_encrypt_demo.py self-test"
    )
    validation_results(r)
    r.h("3.3 Nhận xét đánh giá kết quả và hạn chế")
    findings = [
        "E1–E3 đối chiếu QBER và phát hiện với oracle; "
        "chỉ đúng mô hình IR và nhiễu đã đặt",
        "E13 cho FPR/TPR, ROC và độ trễ có điều kiện; nền mô phỏng và số lượt hữu hạn",
        "E4–E6 tách rò EC, chi phí PE/PA và suy hao; "
        "công thức khóa giản lược, E6 tiệm cận",
        "E7–E8 tách cổng Bell, sàng lọc và thời gian; "
        "chưa đo hạ tầng quang hay an toàn DI",
        "E9–E12 kiểm tra I/O, toàn vẹn, nonce và HMAC; khóa từ seed không an toàn thực",
        "E15 phân biệt Grover với Shor; số mũ truy vấn "
        "không phải số cổng hoặc thời gian thực",
    ]
    r.table(
        "Đối chiếu kết quả với sáu câu hỏi nghiên cứu",
        ["RQ", "Căn cứ", "Kết luận trong phạm vi và giới hạn"],
        [(rq[0], rq[2], finding) for rq, finding in zip(RQ, findings, strict=True)],
        source="CSV/JSON/PNG được dẫn ở mục 3.2.",
        widths=[1.3, 3.1, 11.6],
    )
    r.sub(
        "Các chỉ tiêu chưa được đánh giá trong phạm vi thực nghiệm",
        "Không đo thiết bị quang học thật, đồng bộ nguồn–detector, truyền mạng "
        "diện rộng, nguồn rối vật lý hoặc hiệu chuẩn ngoài phòng thí nghiệm. "
        "Detector blinding, Trojan-horse, rò thời gian/điện năng và các kênh kề "
        "vật lý chưa được mô hình hóa. Không có cơ sở gán độ an toàn triển khai "
        "hoặc tốc độ khóa của thiết bị thương mại từ các bảng mô phỏng.",
    )
    r.table(
        "Các hạn chế hiện có và hướng cải tiến",
        ["Hạn chế", "Hệ quả", "Hướng cải tiến"],
        [
            (
                "Nguồn đơn photon lý tưởng; WCP Poisson",
                "PNS chưa được mô phỏng; đường WCP E6 lạc quan",
                "Mô hình PNS; chọn cường độ và sàng lọc decoy đầy đủ",
            ),
            (
                "Cận khóa hữu hạn giản lược",
                "Chưa chứng minh khả hợp cho tấn công coherent tổng quát",
                "Cận lấy mẫu chặt; ngân sách ε toàn hệ thống",
            ),
            (
                "Khóa chia sẻ ban đầu; HMAC",
                "Xác thực dựa giả định tính toán và cấp khóa ban đầu",
                "Wegman–Carter; hạch toán tiêu thụ khóa",
            ),
            (
                "RNG mô phỏng có seed",
                "Có thể dự đoán vật liệu khóa; QRNG Aer không là entropy vật lý",
                "Nguồn entropy vật lý được kiểm định riêng",
            ),
            (
                "Side-channel phần cứng",
                "Không phát hiện detector blinding/Trojan-horse bằng mô hình này",
                "Đặc tả thiết bị; mô hình tấn công và đo quang thực",
            ),
            (
                "Nonce và tuổi khóa AEAD",
                "QKD không sửa được rò do lặp nonce",
                "Quản lý nonce bền vững; giới hạn dùng; xử lý crash",
            ),
            (
                "Không có mạng/hardware thật",
                "Benchmark chỉ phản ánh máy và hệ tệp của lượt chạy",
                "Đo mạng, mất gói, đồng bộ và thiết bị thực",
            ),
            (
                "Giám sát dùng nền hiệu chuẩn",
                "Chưa gộp sai số nền; SPRT có thể dừng trước tấn công muộn",
                "Cận có sai số calibration; kiểm định tuần tự liên tục",
            ),
            (
                "BB84/E91 được so độc lập",
                "Chưa đánh giá phép ghép hai khóa và ngân sách phụ thuộc",
                "HKDF kết hợp có phân tích an toàn và kiểm thử",
            ),
            (
                "Chưa có PQC ML-KEM",
                "Không có đường kết hợp khóa hậu lượng tử",
                "Thiết kế combiner QKD + ML-KEM, kiểm tra thất bại từng nhánh",
            ),
            (
                "Sidecar khóa D2 và KeyStore bộ nhớ",
                "Chỉ dùng demo; không là kho khóa sản xuất",
                "Kho khóa bảo vệ OS; ACL Windows; vòng đời bền vững",
            ),
        ],
        source="SPEC.md mục 20; docs/decisions.md; mã nguồn hiện tại.",
        widths=[4.2, 6, 5.8],
    )
    r.p(
        "Những ca toàn vẹn hoặc xác thực đạt trên mẫu đã chạy chỉ chứng minh hành "
        "vi được kiểm tra trong cấu hình tương ứng. Các khoảng tin cậy và số lần "
        "lặp cần đi cùng tỷ lệ; không biến một mẫu không thấy lỗi thành xác suất "
        "lỗi bằng không. Tương tự, kiểm tra ngẫu nhiên đạt không chứng minh tính "
        "bí mật, và quan sát vi phạm Bell không tự thiết lập an toàn độc lập thiết bị."
    )
    r.h("3.4 Kết luận")
    r.p(
        "Đồ án hiện thực một chuỗi mô phỏng có thể theo dõi từ nguồn và phép đo "
        "đến quyết định dừng, hậu xử lý, dẫn xuất khóa và bảo vệ dữ liệu. Việc tách "
        "NumPy/Aer, quan sát công khai/GroundTruth và RNG mô phỏng/entropy OS làm "
        "rõ vai trò từng thành phần. Các kết quả E1–E15 cùng hồ sơ nghiệm thu "
        "cho phép đối chiếu các oracle vật lý, ảnh hưởng khóa hữu hạn, khác biệt "
        "giao thức, đánh đổi giám sát và kỷ luật toàn vẹn dữ liệu."
    )
    r.p(
        "Giá trị của sản phẩm nằm ở khả năng thực nghiệm có kiểm soát và kiểm tra "
        "được bằng chứng, không phải cung cấp một đường truyền QKD an toàn ngoài "
        "thực tế. Các bước phát triển tiếp theo cần ưu tiên phân tích khóa hữu "
        "hạn chặt hơn, xác thực và quản lý khóa bền vững, mô hình thiết bị, trạng "
        "thái mồi, ghép BB84/E91 và combiner với ML-KEM. Mỗi mở rộng cần có mô "
        "hình đe dọa, tiêu chí đo và dữ liệu tái lập riêng trước khi kết luận."
    )
    r.p(
        f"Hồ sơ dựng đã đọc {len(inputs)} tệp bằng chứng CSV/JSON/JSONL/PNG trong "
        "results/ ngoài biên bản kiểm tra hiện hành. Danh sách đường dẫn, hash "
        "và số bản ghi được lưu trong docs/report_build_manifest.json; báo cáo "
        "không làm thay đổi các tệp dữ liệu thực nghiệm đầu vào."
    )
    r.h("TÀI LIỆU THAM KHẢO", 2)
    for index, entry in enumerate(r.refs, 1):
        venue = entry.get(
            "journal", entry.get("booktitle", entry.get("institution", ""))
        )
        parts = [f"[{index}] {entry.get('author', '')}", f"“{entry['title']}”", venue]
        if entry.get("volume"):
            parts.append(f"tập {entry['volume']}")
        if entry.get("number"):
            parts.append(f"số {entry['number']}")
        if entry.get("pages"):
            parts.append(f"tr. {entry['pages'].replace('--', '–')}")
        parts.append(entry.get("year", ""))
        if entry.get("doi"):
            parts.append(f"DOI: {entry['doi']}")
        if entry.get("url"):
            parts.append(entry["url"])
        paragraph = r.p(". ".join(part for part in parts if part) + ".")
        paragraph.paragraph_format.first_line_indent = Cm(0)
        paragraph.paragraph_format.keep_together = True


def stable_package(path: Path) -> None:
    """Normalize ZIP timestamps; byte-identical inputs produce identical packages."""
    with ZipFile(path) as archive:
        members = [(name, archive.read(name)) for name in archive.namelist()]
    with ZipFile(path, "w", ZIP_DEFLATED) as archive:
        for name, content in members:
            info = ZipInfo(name, (2026, 11, 20, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            archive.writestr(info, content)


def verify(path: Path, manifest_path: Path = MANIFEST) -> dict[str, object]:
    """Verify exact chapter/caption inventories and structural DOCX invariants."""
    document = Document(str(path))
    manifest = read_json(manifest_path)
    paragraphs = [paragraph.text.strip() for paragraph in document.paragraphs]
    text = "\n".join(
        paragraphs
        + [
            cell.text
            for table in document.tables
            for row in table.rows
            for cell in row.cells
        ]
    )
    if re.search(r"\b(?:TODO|TBD|NaN|None)\b", text):
        raise ValueError("Unexpected placeholder or nonfinite marker in report")
    chapters = [
        p.text
        for p in document.paragraphs
        if p.style is not None
        and p.style.name == "Heading 1"
        and p.text.startswith("CHƯƠNG ")
    ]
    if len(chapters) != 3:
        raise ValueError(f"Need three chapters, got {len(chapters)}")
    table_list_start, figure_list_start, intro = (
        paragraphs.index(title)
        for title in ("DANH MỤC BẢNG", "DANH MỤC HÌNH", "LỜI MỞ ĐẦU")
    )
    for label, captions, start, stop in (
        ("Bảng", manifest["tables"], table_list_start, figure_list_start),
        ("Hình", manifest["figures"], figure_list_start, intro),
    ):
        listed = [
            text for text in paragraphs[start:stop] if text.startswith(f"{label} ")
        ]
        actual = [
            p.text
            for p in document.paragraphs
            if p.style is not None
            and p.style.name == "Caption"
            and p.text.startswith(f"{label} ")
        ]
        if actual != captions or listed != captions:
            raise ValueError(f"{label} captions/list mismatch")
        if len(actual) != len(set(actual)):
            raise ValueError(f"Duplicate {label} caption")
    if len(document.tables) != len(manifest["tables"]) + 1:
        raise ValueError("Uncaptioned body table")
    logo = int((ROOT / "docs/assets/logo_it.png").exists())
    if len(document.inline_shapes) != len(manifest["figures"]) + logo:
        raise ValueError("Uncaptioned body picture")
    if len(document.sections) != 2:
        raise ValueError("Cover/body must use separate sections")
    for section in document.sections:
        if section.page_width is None or abs(section.page_width - Cm(21)) > 635:
            raise ValueError("Page width must be A4")
        if section.left_margin is None or abs(section.left_margin - Cm(3)) > 635:
            raise ValueError("Left margin must be 3 cm")
    if document.styles["Caption"].font.bold:
        raise ValueError("Caption names must not be bold")
    if list(document.styles["Title"].element.iter(qn("w:pBdr"))):
        raise ValueError("Unexpected rule below front-matter title")
    if "PAGE" in document.sections[0].footer._element.xml:
        raise ValueError("Cover must not have a page number")
    if "PAGE" not in document.sections[1].footer._element.xml:
        raise ValueError("Body footer must have a PAGE field")
    for table in document.tables[1:]:
        if (
            table.rows[0]._tr.find("w:trPr/w:tblHeader", namespaces=table._tbl.nsmap)
            is None
        ):
            raise ValueError("Missing repeated header")
        for row in table.rows:
            if row._tr.find("w:trPr/w:cantSplit", namespaces=table._tbl.nsmap) is None:
                raise ValueError("Row can split across pages")
    with ZipFile(path) as archive:
        source = archive.read("word/document.xml").decode()
        settings = archive.read("word/settings.xml").decode()
        if "TOC " not in source or "updateFields" not in settings:
            raise ValueError("Missing live Word TOC")
        if 'w:val="thickThinSmallGap"' not in source:
            raise ValueError("Missing cover double border")
        if 'w:start="1"' not in source:
            raise ValueError("Body page numbering not restarted")
    for item in manifest["inputs"]:
        source_path = ROOT / item["path"]
        if digest(source_path) != item["sha256"]:
            raise ValueError(f"Evidence changed since build: {source_path}")
    for source_name, source_digest in manifest.get("report_sources", {}).items():
        if digest(ROOT / source_name) != source_digest:
            raise ValueError(f"Report source changed since build: {source_name}")
    result: dict[str, object] = {
        "opens_with_python_docx": True,
        "chapters": len(chapters),
        "tables": len(manifest["tables"]),
        "figures": len(manifest["figures"]),
        "caption_lists_match": True,
        "input_hashes_match": True,
        "docx_sha256": digest(path),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result


def main() -> None:
    """Build and validate the report without starting simulations or experiments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()
    if args.check_only:
        verify(OUTPUT)
        return
    inputs = inventory()
    report = Report()
    report.cover()
    report.front()
    chapter_one(report)
    chapter_two(report)
    chapter_three(report, inputs)
    report.finish_lists()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    report.doc.save(str(OUTPUT))
    stable_package(OUTPUT)
    manifest = {
        "document": rel(OUTPUT),
        "git": git_info(),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "library_versions": installed(),
        "inputs": inputs,
        "source_files": {
            rel(path): digest(path)
            for base in ("src", "experiments", "demos", "tests", "configs")
            for path in sorted((ROOT / base).rglob("*"))
            if path.is_file() and path.suffix in (".py", ".yaml")
        },
        "tables": report.tables,
        "figures": report.figures,
        "figure_sources": report.figure_sources,
        "table_sources": report.table_sources,
        "headings": report.headings,
        "diagrams": {
            rel(path): digest(path) for path in sorted(DIAGRAMS.glob("*.png"))
        },
        "validation_artifacts": {
            rel(path): digest(path)
            for path in sorted(VALIDATION.glob("*"))
            if path.suffix in (".json", ".xml", ".log")
            and path.name != "docx_check.json"
        },
        "report_sources": {
            rel(path): digest(path)
            for path in [
                ROOT / "SPEC.md",
                ROOT / "AGENTS.md",
                ROOT / "pyproject.toml",
                Path(__file__),
                *sorted((ROOT / "docs").glob("*.md")),
                ROOT / "docs/references.bib",
            ]
        },
    }
    MANIFEST.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    result = verify(OUTPUT)
    VALIDATION.mkdir(parents=True, exist_ok=True)
    (VALIDATION / "docx_check.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Đã tạo {OUTPUT}")


if __name__ == "__main__":
    main()
