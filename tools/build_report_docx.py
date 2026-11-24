"""Build the expanded Vietnamese report from retained experiment evidence.

Use the bundled document Python runtime. The existing cover is retained verbatim.
Run experiments/report_summary.py with uv first; no trials run in this builder.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
from importlib.metadata import version
from pathlib import Path
from typing import Any
from zipfile import ZipFile

from docx import Document
from docx.enum.section import WD_SECTION_START
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_TAB_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor
from report_expansion_vi import chapter_one, chapter_two

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "docs/BaoCao_QKD_Hybrid.docx"
OUTPUT = ROOT / "docs/BaoCao_QKD_Hybrid_MoRong.docx"
MANIFEST = ROOT / "docs/report_build_manifest.json"
DATA = ROOT / "results/report_summary"
BACKUP = ROOT / "results/report_build/before_rewrite/BaoCao_QKD_Hybrid.docx"
HEADER_TEXT = "[Báo cáo đồ án học phần Mã hóa và Mật mã]"
FOOTER_TEXT = "[Nguyễn Phạm Tuân - Trần Duy Hòa - Nhóm 6]"
Row = dict[str, str]


def digest(path: Path) -> str:
    """Return SHA-256 of a document source or retained measurement."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def number(value: object, digits: int = 2) -> str:
    """Format measured values with Vietnamese decimal and thousands separators."""
    return (
        f"{float(str(value)):,.{digits}f}".replace(",", "_")
        .replace(".", ",")
        .replace("_", ".")
    )


def percent(value: object, digits: int = 2) -> str:
    """Convert a stored probability to a percentage without changing its meaning."""
    return number(float(str(value)) * 100, digits) + "%"


class Report:
    """Keep the student's cover and write a readable three chapter report."""

    def __init__(self) -> None:
        if not BACKUP.exists():
            BACKUP.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(TEMPLATE, BACKUP)
        self.doc = Document(TEMPLATE)
        children = list(self.doc.element.body)
        split = next(
            i
            for i, child in enumerate(children)
            if child.find(".//" + qn("w:sectPr")) is not None
        )
        # Preserve all cover content and the final body's page settings.
        for child in children[split + 1 :]:
            if child.tag != qn("w:sectPr"):
                self.doc.element.body.remove(child)
        # Keep one cover section and one contents section, irrespective of how
        # many sections the input document acquired during manual editing.
        final = self.doc.element.body.sectPr
        for child in list(final):
            if child.tag in (
                qn("w:headerReference"),
                qn("w:footerReference"),
                qn("w:titlePg"),
                qn("w:pgNumType"),
                qn("w:pgBorders"),
            ):
                final.remove(child)
        self.evidence = json.loads((DATA / "summary.json").read_text(encoding="utf-8"))
        self.data: dict[str, Any] = self.evidence["evidence"]
        self.figures: list[dict[str, str]] = []
        self.tables: list[dict[str, Any]] = []
        self.equations = 0
        self.headings: list[str] = []
        self.chapter_words: dict[str, int] = {}
        self.current_chapter = "front"
        for name, size in (
            ("Normal", 13),
            ("Title", 16),
            ("Heading 1", 16),
            ("Heading 2", 14),
            ("Caption", 11),
        ):
            style = self.doc.styles[name]
            style.font.name = "Times New Roman"
            style.font.size = Pt(size)
            style.font.color.rgb = RGBColor(0, 0, 0)
            for border in list(style.element.iter(qn("w:pBdr"))):
                border.getparent().remove(border)
            pf = style.paragraph_format
            pf.line_spacing = 1.2
            pf.space_after = Pt(6)
            pf.widow_control = True
            pf.first_line_indent = Cm(0.8 if name == "Normal" else 0)
            if name.startswith("Heading"):
                pf.keep_with_next = True
                pf.space_before = Pt(10)
                style.font.bold = True
        self.doc.styles[
            "Normal"
        ].paragraph_format.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        self.doc.styles["Heading 1"].paragraph_format.page_break_before = True
        self.doc.styles[
            "Heading 1"
        ].paragraph_format.alignment = WD_ALIGN_PARAGRAPH.CENTER
        self.doc.core_properties.title = "Mô phỏng hệ thống phân phối khóa lượng tử"
        self.doc.core_properties.subject = "Báo cáo đồ án BB84 E91 và mã hóa dữ liệu"
        for style_name in ("Header", "Footer", "TOC 1", "TOC 2", "Table of Figures"):
            if style_name in self.doc.styles:
                style = self.doc.styles[style_name]
                style.font.name = "Times New Roman"
                style.font.size = Pt(12)
                style.font.color.rgb = RGBColor(0, 0, 0)
        # The retained Footer style had a centre tab. Remove it so the PAGE
        # field reaches the explicit right tab at the text area's right edge.
        self.doc.styles["Footer"].paragraph_format.tab_stops.clear_all()
        for section in self.doc.sections:
            section.header.is_linked_to_previous = False
            section.footer.is_linked_to_previous = False
            for part in (section.header, section.footer):
                for element in list(part._element):
                    part._element.remove(element)
                part.add_paragraph()
            for name in ("headerReference", "footerReference", "pgNumType", "titlePg"):
                for element in list(section._sectPr.findall(qn("w:" + name))):
                    section._sectPr.remove(element)
        # A date on the cover is body text, never a cover footer.
        from docx.text.paragraph import Paragraph

        cover_end = Paragraph(children[split], self.doc._body)
        cover_end.add_run("Đà Nẵng, 11/2026").italic = True
        cover_end.alignment = WD_ALIGN_PARAGRAPH.CENTER
        cover_end.paragraph_format.first_line_indent = Cm(0)
        cover_end.paragraph_format.space_before = Pt(100)

    def pick(self, exp: str, metric: str, **filters: str) -> Row:
        """Require an unambiguous CSV row for every number quoted in prose."""
        values = [
            r
            for r in self.data[exp]["rows"]
            if r["metric"] == metric and all(r.get(k) == v for k, v in filters.items())
        ]
        if len(values) != 1:
            raise ValueError(f"Expected one measurement: {exp}, {metric}, {filters}")
        return values[0]

    def val(self, exp: str, metric: str, **filters: str) -> str:
        """Format a measured row's value as a Vietnamese number."""
        return number(self.pick(exp, metric, **filters)["value"])

    def p(self, text: str, *, bullet: bool = False) -> None:
        """Add a connected paragraph or a simple list item."""
        p = self.doc.add_paragraph(text, style="List Bullet" if bullet else "Normal")
        if bullet:
            p.paragraph_format.first_line_indent = Cm(0)
            p.paragraph_format.line_spacing = 1.2
        self.chapter_words[self.current_chapter] = self.chapter_words.get(
            self.current_chapter, 0
        ) + len(text.split())

    def h(self, text: str, level: int = 2) -> None:
        """Add section headings with no unnecessary nesting."""
        if level == 1:
            self.current_chapter = text
        self.doc.add_heading(text, level)
        self.headings.append(text)

    def equation(self, text: str, explanation: str = "") -> None:
        """Insert editable OMML and explain the symbols directly underneath."""
        p = self.doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.first_line_indent = Cm(0)
        p.paragraph_format.keep_with_next = bool(explanation)
        equation = OxmlElement("m:oMath")

        def math_run(value: str) -> Any:
            """Use upright text and a consistent size inside native OMML."""
            run = OxmlElement("m:r")
            properties = OxmlElement("m:rPr")
            style = OxmlElement("m:sty")
            style.set(qn("m:val"), "p")
            properties.append(style)
            run.append(properties)
            font_properties = OxmlElement("w:rPr")
            size = OxmlElement("w:sz")
            size.set(qn("w:val"), "23")
            font_properties.append(size)
            run.append(font_properties)
            token = OxmlElement("m:t")
            token.text = value
            run.append(token)
            return run

        def append_math(parent: Any, fragment: str) -> None:
            """Build real subscripts for the named quantities in the report."""
            symbols = {
                "Qub": ("Q", "ub"),
                "QIR": ("Q", "IR"),
                "Pgiữ": ("P", "giữ"),
                "pZ": ("p", "Z"),
                "ηch": ("η", "ch"),
                "ηd": ("η", "d"),
                "Pcoinc": ("P", "coinc"),
                "ηA": ("η", "A"),
                "ηB": ("η", "B"),
                "Smax": ("S", "max"),
                "σS": ("σ", "S"),
                "εPE": ("ε", "PE"),
                "εPA": ("ε", "PA"),
                "Qmax": ("Q", "max"),
                "kmin": ("k", "min"),
                "Pphát hiện": ("P", "phát hiện"),
                "ΔPA": ("Δ", "PA"),
                "leakEC": ("leak", "EC"),
                "leakV": ("leak", "V"),
                "r∞": ("r", "∞"),
                "fEC": ("f", "EC"),
                "Kauth": ("K", "auth"),
                "Kứng dụng": ("K", "ứng dụng"),
                "Kcuối": ("K", "cuối"),
            }
            pattern = "|".join(
                re.escape(key) for key in sorted(symbols, key=len, reverse=True)
            )
            previous = 0
            for item in re.finditer(pattern, fragment):
                parent.append(math_run(fragment[previous : item.start()]))
                subscript = OxmlElement("m:sSub")
                base, sub = OxmlElement("m:e"), OxmlElement("m:sub")
                first, second = symbols[item.group()]
                base.append(math_run(first))
                sub.append(math_run(second))
                subscript.extend([base, sub])
                parent.append(subscript)
                previous = item.end()
            parent.append(math_run(fragment[previous:]))

        position = 0
        for match in re.finditer(r"(10)\^\(([^()]+)\)|(\(3/4\))\^(k)", text):
            append_math(equation, text[position : match.start()])
            power = OxmlElement("m:sSup")
            base, exponent = OxmlElement("m:e"), OxmlElement("m:sup")
            base.append(math_run(match.group(1) or match.group(3)))
            exponent.append(math_run(match.group(2) or match.group(4)))
            power.extend([base, exponent])
            equation.append(power)
            position = match.end()
        append_math(equation, text[position:])
        p._p.append(equation)
        self.equations += 1
        if explanation:
            self.p(explanation)
            self.doc.paragraphs[-1].paragraph_format.keep_together = True

    def field(self, paragraph: Any, code: str, cache: str = "") -> None:
        """Insert a live Word field with a readable pre-update result."""
        field = OxmlElement("w:fldSimple")
        field.set(qn("w:instr"), code)
        if cache:
            run, text = OxmlElement("w:r"), OxmlElement("w:t")
            text.text = cache
            run.append(text)
            field.append(run)
        paragraph._p.append(field)

    def caption(self, label: str, index: int, title: str) -> None:
        """Use SEQ plus explicit bookmarks, enabling native Word TOF/TOT links."""
        p = self.doc.add_paragraph(style="Caption")
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.keep_with_next = True
        bookmark_id = 1000 + index + (100 if label == "Bảng" else 0)
        start = OxmlElement("w:bookmarkStart")
        start.set(qn("w:id"), str(bookmark_id))
        start.set(
            qn("w:name"), f"QKD_{'Table' if label == 'Bảng' else 'Figure'}_{index}"
        )
        p._p.append(start)
        p.add_run(label + " ")
        self.field(p, f"SEQ {label} \\* ARABIC", str(index))
        p.add_run(". " + title)
        end = OxmlElement("w:bookmarkEnd")
        end.set(qn("w:id"), str(bookmark_id))
        p._p.append(end)

    def table(self, name: str, title: str) -> None:
        """Render a small evidence-derived table with repeatable header rows."""
        record = self.evidence["report_tables"][name]
        self.caption("Bảng", len(self.tables) + 1, title)
        table = self.doc.add_table(rows=1, cols=len(record["headers"]))
        table.alignment = WD_TABLE_ALIGNMENT.CENTER
        table.autofit = False
        widths = record.get(
            "widths", [16 / len(record["headers"])] * len(record["headers"])
        )
        for column, width in zip(table.columns, widths, strict=True):
            column.width = Cm(width)
        borders = OxmlElement("w:tblBorders")
        for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
            border = OxmlElement("w:" + edge)
            for key, value in {"val": "single", "sz": "4", "color": "D9D9D9"}.items():
                border.set(qn("w:" + key), value)
            borders.append(border)
        table._tbl.tblPr.append(borders)
        margins = OxmlElement("w:tblCellMar")
        for side in ("top", "bottom", "left", "right"):
            item = OxmlElement("w:" + side)
            item.set(qn("w:w"), "85")
            item.set(qn("w:type"), "dxa")
            margins.append(item)
        table._tbl.tblPr.append(margins)
        values = [record["headers"], *record["rows"]]
        for row_index, row_values in enumerate(values):
            row = table.rows[0] if row_index == 0 else table.add_row()
            row._tr.get_or_add_trPr().append(OxmlElement("w:cantSplit"))
            if row_index == 0:
                row._tr.get_or_add_trPr().append(OxmlElement("w:tblHeader"))
            for cell, value, width in zip(row.cells, row_values, widths, strict=True):
                cell.width = Cm(width)
                cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
                cell.text = str(value)
                p = cell.paragraphs[0]
                p.paragraph_format.first_line_indent = Cm(0)
                p.paragraph_format.line_spacing = 1.1
                p.paragraph_format.space_after = Pt(2)
                p.paragraph_format.space_before = Pt(2)
                p.alignment = WD_ALIGN_PARAGRAPH.LEFT
                for run in p.runs:
                    run.font.size = Pt(11)
                    run.bold = row_index == 0
                if row_index == 0:
                    shade = OxmlElement("w:shd")
                    shade.set(qn("w:fill"), "E9ECEF")
                    cell._tc.get_or_add_tcPr().append(shade)
        self.tables.append({"name": name, "title": title, "rows": len(record["rows"])})
        note = self.doc.add_paragraph("Nguồn: " + record["source"])
        note.paragraph_format.first_line_indent = Cm(0)
        for run in note.runs:
            run.font.size = Pt(9)

    def fig(self, name: str, title: str, source: str) -> None:
        """Embed a code generated chart and keep it with its caption."""
        path = DATA / f"{name}.png"
        p = self.doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.first_line_indent = Cm(0)
        p.paragraph_format.keep_with_next = True
        shape = p.add_run().add_picture(str(path), width=Cm(15.7))
        shape._inline.docPr.set("descr", title)
        self.caption("Hình", len(self.figures) + 1, title)
        note = self.doc.add_paragraph("Nguồn dữ liệu: " + source)
        note.paragraph_format.first_line_indent = Cm(0)
        note.paragraph_format.line_spacing = 1
        for run in note.runs:
            run.font.size = Pt(9)
        self.figures.append(
            {
                "path": path.relative_to(ROOT).as_posix(),
                "title": title,
                "source": source,
            }
        )

    def front(self) -> None:
        """Separate unnumbered cover/contents from numbered figure/table lists."""
        self.doc.add_paragraph("MỤC LỤC", style="Title")
        p = self.doc.add_paragraph()
        self.field(p, 'TOC \\o "1-2" \\h \\z \\u')
        section = self.doc.add_section(WD_SECTION_START.NEW_PAGE)
        section.header.is_linked_to_previous = False
        section.footer.is_linked_to_previous = False
        section.top_margin, section.bottom_margin = Cm(2.5), Cm(2.3)
        section.header_distance, section.footer_distance = Cm(1), Cm(1)
        for item in list(section._sectPr.findall(qn("w:pgNumType"))):
            section._sectPr.remove(item)
        numbering = OxmlElement("w:pgNumType")
        numbering.set(qn("w:start"), "1")
        section._sectPr.append(numbering)
        for part, text, edge in (
            (section.header, HEADER_TEXT, "bottom"),
            (section.footer, FOOTER_TEXT, "top"),
        ):
            p = part.paragraphs[0]
            p.text = text
            p.alignment = WD_ALIGN_PARAGRAPH.LEFT
            p.paragraph_format.first_line_indent = Cm(0)
            p.paragraph_format.left_indent = Cm(0)
            p.paragraph_format.right_indent = Cm(0)
            p.paragraph_format.space_before = Pt(4)
            p.paragraph_format.space_after = Pt(4)
            p.paragraph_format.line_spacing = 1
            border_group = OxmlElement("w:pBdr")
            border = OxmlElement("w:" + edge)
            for key, value in {
                "val": "single",
                "sz": "12",
                "space": "5",
                "color": "000000",
            }.items():
                border.set(qn("w:" + key), value)
            border_group.append(border)
            p._p.get_or_add_pPr().append(border_group)
            for run in p.runs:
                run.font.name = "Times New Roman"
                run.font.size = Pt(11)
            if edge == "top":
                p.paragraph_format.tab_stops.clear_all()
                p.paragraph_format.tab_stops.add_tab_stop(
                    Cm(16), WD_TAB_ALIGNMENT.RIGHT
                )
                p.add_run("\t")
                self.field(p, "PAGE", "1")
        self.doc.add_paragraph("DANH SÁCH HÌNH ẢNH", style="Title")
        self.field(self.doc.add_paragraph(), 'TOC \\h \\z \\c "Hình"')
        self.doc.add_page_break()
        self.doc.add_paragraph("DANH SÁCH BẢNG BIỂU", style="Title")
        self.field(self.doc.add_paragraph(), 'TOC \\h \\z \\c "Bảng"')
        self.doc.add_page_break()
        self.doc.add_paragraph("LỜI MỞ ĐẦU", style="Title")
        self.p(
            "Đồ án tìm hiểu cách hai bên tạo khóa chung bằng phân phối khóa lượng tử "
            "và dùng khóa đó để bảo vệ dữ liệu. Nhóm xây dựng chương trình mô phỏng "
            "BB84 và E91, sau đó thử các tình huống có nhiễu, có người nghe lén và có "
            "sửa đổi dữ liệu khi truyền."
        )
        self.p(
            "Kết quả cho thấy hành vi chặn rồi phát lại của Eve làm tăng tỷ lệ bit "
            "sai và có thể khiến phiên tạo khóa bị dừng. Các thử nghiệm tệp cũng cho "
            "thấy dữ liệu hợp lệ được khôi phục, còn các trường hợp sửa đổi đã thử "
            "đều bị từ chối. Đây là kết quả trong mô hình phần mềm, chưa thể xem là "
            "bằng chứng an toàn cho một hệ thống QKD thật."
        )
        self.p(
            "Chương 1 giải thích cơ sở vật lý, các công thức và điều kiện tạo khóa. "
            "Chương 2 trình bày thiết kế hệ thống, cách chọn tham số và các bước "
            "kiểm tra. Chương 3 phân tích các kịch bản đã chạy, cách đọc biểu đồ "
            "và giới hạn của những kết quả thu được."
        )


def chapter_three(r: Report) -> None:
    """Explain scenarios, measured trends, their causes and practical limits."""
    r.h("CHƯƠNG 3 KẾT QUẢ THỰC NGHIỆM VÀ ĐÁNH GIÁ", 1)
    r.h("3.1 Thiết lập thực nghiệm và cách đọc kết quả")
    meta = r.data["E01"]["metadata"]
    r.p(
        f"Các kết quả dưới đây lấy từ bộ chạy nhanh đã lưu. Seed gốc là "
        f"{meta['seed']}; môi trường lần chạy dùng Python {meta['python']}, "
        f"NumPy {meta['library_versions']['numpy']}, Qiskit "
        f"{meta['library_versions']['qiskit']} và Aer "
        f"{meta['library_versions']['qiskit-aer']}. Bộ chạy nhanh dùng ít lượt "
        "lặp hơn bộ đầy đủ nên phù hợp để quan sát xu hướng, nhưng chưa đủ "
        "để kết luận về những sự cố có xác suất rất nhỏ."
    )
    r.p(
        "Mỗi hình có chú thích nguồn CSV tương ứng. Trục phần trăm cho biết "
        "tỷ lệ lỗi, tỷ lệ chặn hoặc tỷ lệ phiên; trục bit cho biết lượng khóa "
        "còn lại. Các thanh sai số trong hình giao thức là khoảng tin cậy của "
        "số liệu đã lưu. Riêng hình tốc độ mã hóa dùng khoảng tứ phân vị để "
        "mô tả độ dao động của thời gian đo. Thanh sai số rộng nghĩa là cần "
        "thận trọng hơn khi so sánh các điểm gần nhau."
    )
    r.p(
        "E4 sử dụng Cascade thực để theo dõi xử lý khóa. E2, E5, E8, E10 "
        "và E14 dùng sửa sai lý tưởng để giảm thời gian chạy. Vì vậy, các "
        "kết quả đó không phải phép đo chi phí Cascade. Trong các thống kê "
        "tốc độ khóa, phiên bị dừng đóng góp số bit cuối bằng không."
    )

    r.table("results", "Tóm tắt một số kết quả thực nghiệm đã lưu")
    r.p(
        "Bảng tóm tắt chỉ dùng để định hướng. Các mục tiếp theo nêu điều kiện "
        "của từng kết quả, phân tích đường biểu diễn và giải thích phạm vi có "
        "thể kết luận. Những tỷ lệ đạt toàn bộ trong mẫu đã thử không bảo đảm "
        "mọi lần chạy hoặc mọi kiểu tấn công đều cho cùng kết quả."
    )
    r.h("3.2 Eve chặn và phát lại tín hiệu")
    cfg = meta["config"]
    first = r.pick("E01", "qber", backend="fast", noise="0", x="0.5")
    last = r.pick("E01", "qber", backend="fast", noise="0", x="1")
    noisy = r.pick("E01", "qber", backend="fast", noise="0.02", x="0")
    r.p(
        f"Thực nghiệm E1 giữ {number(cfg['pulses'], 0)} xung cho mỗi cấu hình "
        f"backend nhanh và lặp {first['n']} lần. Nhóm tăng dần tỷ lệ xung Eve "
        "chặn từ không chặn đến chặn toàn bộ, rồi đo QBER sau sàng lọc. Hai "
        "trường hợp được xét là kênh không có nhiễu nền và kênh có nhiễu nền "
        f"{percent(cfg['noise'][-1], 0)}. Các điểm Qiskit chỉ chạy ở hai đầu "
        f"của dải chặn, với {number(cfg['aer_pulses'], 0)} xung mỗi lượt."
    )
    r.fig(
        "01_eve",
        "QBER tăng khi Eve chặn nhiều tín hiệu hơn",
        "results/quick/E01_qber_eve.csv",
    )
    r.p(
        "Đường backend nhanh khi không có nhiễu nền đi lên gần tuyến tính. "
        f"Khi Eve chặn một nửa số xung, QBER đo được là {percent(first['value'])}; "
        f"khi chặn toàn bộ, QBER là {percent(last['value'])}. Xu hướng này "
        "phù hợp với công thức cơ bản ở Chương 1. Nguyên nhân là Eve càng "
        "đo nhiều thì càng có nhiều cơ hội chọn sai cơ sở và làm sai bit của Bob."
    )
    r.p(
        f"Đường có nhiễu nền đã bắt đầu ở QBER {percent(noisy['value'])} ngay "
        "khi không có Eve và tiếp tục tăng khi Eve can thiệp. Hai nguồn lỗi "
        "không cộng thẳng trong mọi trường hợp, vì hai lần lật cùng một bit "
        "có thể bù nhau. Đây cũng là lý do cần biết mức nhiễu bình thường "
        "trước khi diễn giải một QBER tăng lên."
    )
    r.p(
        "Kết quả minh họa được dấu vết của kiểu nghe lén đã mô hình hóa. "
        "Tuy nhiên, QBER cao chỉ cho biết kênh không đáp ứng điều kiện tạo "
        "khóa; riêng số đo này chưa xác định được lỗi do Eve hay do thiết bị. "
        "Việc chặn ít tín hiệu cũng có thể khó phân biệt với dao động nền "
        "nếu số mẫu kiểm tra còn nhỏ."
    )

    r.h("3.3 Ảnh hưởng của nhiễu nền đến phiên tạo khóa")
    a = r.pick("E02", "abort", series="BB84 Qmax=0.08", x="0.04")
    b = r.pick("E02", "abort", series="BB84 Qmax=0.11", x="0.08")
    r.p(
        "Trong E2, nhóm tắt Eve và chỉ tăng nhiễu lật bit trên kênh. Hai "
        "cấu hình đặt ngưỡng QBER lần lượt là 0,08 và 0,11. Mỗi điểm dùng "
        f"{number(r.data['E02']['metadata']['config']['pulses'], 0)} xung "
        f"và {a['n']} lượt lặp. Hình bên trái ghi tỷ lệ phiên phải dừng; "
        "hình bên phải ghi số bit khóa cuối trung bình."
    )
    r.fig(
        "02_noise",
        "Nhiễu làm tăng số phiên dừng và giảm lượng khóa",
        "results/quick/E02_noise_abort.csv",
    )
    r.p(
        "Khi nhiễu tăng, đường tỷ lệ dừng đi lên, còn đường số bit khóa "
        "đi xuống. Trên các điểm đã chạy, cấu hình ngưỡng 0,08 dừng toàn bộ "
        f"{a['n']} lượt ngay tại nhiễu nền {percent(a['x'], 0)}; cấu hình "
        f"ngưỡng 0,11 dừng toàn bộ {b['n']} lượt tại {percent(b['x'], 0)}. "
        "Ngưỡng chặt hơn khiến hệ thống từ chối kênh sớm hơn. Các mốc này "
        "chỉ thuộc lưới quét và cỡ mẫu đang xét, không phải giới hạn cố định "
        "của mọi hệ thống BB84."
    )
    r.p(
        "Phiên có thể dừng trước khi QBER trung bình chạm ngưỡng vì chương "
        "trình dùng cả phần dự phòng cho sai số lấy mẫu. Ngoài ra, quá trình "
        "xử lý có thể không còn đủ bit để tạo khóa cuối. Thực nghiệm cho "
        "thấy việc từ chối khóa có thể xảy ra trên một kênh chỉ có nhiễu, "
        "nên không thể coi mọi lần dừng là một lần bắt được Eve."
    )

    r.h("3.4 Số bit kiểm tra và khả năng phát hiện Eve")
    small = r.pick("E03", "detection", x="5")
    mid = r.pick("E03", "detection", x="20")
    large = r.pick("E03", "detection", x="50")
    r.p(
        "E3 xét trường hợp lý tưởng không có nhiễu nền và Eve chặn toàn bộ. "
        "Thay vì chạy đầy đủ quá trình tạo khóa, thí nghiệm lấy số lỗi từ "
        "mô hình xác suất của kiểu tấn công này. Một lượt được xem là phát "
        "hiện nếu mẫu công khai có ít nhất một bit sai. Mỗi cỡ mẫu được "
        f"thử {number(small['n'], 0)} lượt."
    )
    r.fig(
        "03_detection",
        "Mẫu kiểm tra lớn hơn giúp dễ thấy sai lệch",
        "results/quick/E03_sample_detection.csv",
    )
    r.p(
        f"Với {small['x']} bit kiểm tra, tỷ lệ phát hiện là "
        f"{percent(small['value'], 1)}. Khi tăng lên {mid['x']} bit, tỷ lệ "
        f"đạt {percent(mid['value'], 1)}. Ở {large['x']} bit, toàn bộ "
        f"{number(large['n'], 0)} lượt trong mẫu đều thấy lỗi. Đường thực "
        "nghiệm tăng nhanh rồi tiến sát mốc lý thuyết, vì lấy nhiều bit "
        "hơn làm giảm cơ hội bỏ sót tất cả lỗi."
    )
    r.p(
        "Việc không bỏ sót ở một bộ mẫu hữu hạn không có nghĩa xác suất "
        "bỏ sót ngoài thực tế bằng không. Hơn nữa, tiêu chí có một lỗi là "
        "báo động chỉ hợp lý với giả định kênh sạch của E3. Trên kênh có "
        "nhiễu, hệ thống cần so sánh mức lỗi với nền và ngưỡng thống kê. "
        "Công khai quá nhiều bit cũng làm giảm phần dữ liệu còn lại để tạo khóa."
    )

    r.h("3.5 Lượng khóa qua các bước xử lý")
    key = {
        metric: r.pick("E04", metric, noise="0.01", x="100000")
        for metric in ("sifted", "reconciled", "final_bits")
    }
    end = r.pick("E05", "rate", x="1000000")
    r.p(
        "E4 theo dõi số bit sau sàng lọc, sau sửa sai và xác minh, rồi số "
        "bit khóa cuối tính theo lượng thông tin đã công khai. E5 giữ "
        "nhiễu nền cố định và tăng số xung để quan sát ảnh hưởng của việc "
        "chỉ có một lượng dữ liệu hữu hạn. Hình bên trái chọn đường E4 "
        "có nhiễu nền 1%; hình bên phải là E5 với nhiễu nền 3%. Hai hình "
        "dùng điều kiện khác nhau, nên không so trực tiếp độ cao của hai đường."
    )
    r.fig(
        "04_keys",
        "Khóa cuối ngắn hơn dữ liệu đo và phụ thuộc cỡ phiên",
        "results/quick/E04_key_pipeline.csv; E05_finite_key.csv",
    )
    r.p(
        f"Ở {number(key['sifted']['x'], 0)} xung của E4, trung bình còn "
        f"{number(key['sifted']['value'], 0)} bit sau sàng lọc, "
        f"{number(key['reconciled']['value'], 0)} bit sau sửa sai và xác minh, "
        f"rồi {number(key['final_bits']['value'], 0)} bit khóa cuối. Phần "
        "giảm đầu tiên gồm các bit lấy ra để kiểm tra công khai. Phần giảm "
        "tiếp theo phản ánh việc phải trừ thông tin lộ khi sửa sai và phần "
        "dự phòng an toàn. Khóa ngắn đi là bước cần thiết của quy trình."
    )
    r.p(
        "Trong E5, các phiên nhỏ chưa tạo được khóa cuối; khi số xung "
        "tăng, tốc độ khóa tăng và tiến gần đường mốc khi có rất nhiều dữ "
        f"liệu. Tại {number(end['x'], 0)} xung, tốc độ đo là "
        f"{number(end['value'], 4)} bit trên mỗi xung, vẫn dưới mốc "
        f"{number(end['reference'], 4)}. Khi có nhiều mẫu hơn, mức dự phòng "
        "cho sai số ước lượng chiếm tỷ lệ nhỏ hơn. Kết quả giải thích vì "
        "sao có chuỗi bit sau đo chưa đồng nghĩa sẽ tạo được khóa dùng được."
    )

    r.h("3.6 Đối chiếu backend nhanh và Qiskit")
    samples = r.data["backend"]["samples"]
    fastest = next(
        x
        for x in samples
        if x["config"]["bb84"]["backend"] == "fast"
        and x["config"]["bb84"]["n_pulses"] == 2000
    )
    aer = next(
        x
        for x in samples
        if x["config"]["bb84"]["backend"] == "qiskit"
        and x["config"]["bb84"]["n_pulses"] == 2000
    )
    r.p(
        "Các điểm Qiskit trong hình QBER cho xu hướng cùng chiều với "
        "backend nhanh ở những cấu hình được đối chiếu. Điểm Qiskit có "
        "thanh sai số rộng hơn vì số xung ít hơn. Hai backend không cần "
        "cho cùng từng bit; điều cần so là hành vi thống kê của cùng mô "
        "hình. Kết quả hiện có hỗ trợ sự nhất quán ở các điểm đã thử, chưa "
        "xác nhận mọi cấu hình đều tương đương."
    )
    r.p(
        "Phép đo thời gian riêng chỉ đo bước mô phỏng BB84, không đo "
        "toàn bộ quá trình tạo khóa hay mã hóa tệp. Mỗi cỡ phiên được chạy "
        "lại sau một lượt làm nóng, rồi lấy thời gian trung vị. Trục thời "
        "gian dùng thang log để thấy được cả hai đường có độ chênh lớn."
    )
    r.fig(
        "06_backends",
        "Thời gian mô phỏng của hai backend",
        "results/bb84_backend_scaling.json",
    )
    r.p(
        f"Ở {number(fastest['config']['bb84']['n_pulses'], 0)} xung, backend "
        f"nhanh mất khoảng {number(fastest['median_seconds'] * 1000, 3)} ms, "
        f"còn Qiskit mất {number(aer['median_seconds'] * 1000, 3)} ms. "
        "Đường Qiskit tăng mạnh hơn khi số xung tăng vì phải tạo và mô "
        "phỏng mạch đo. NumPy xử lý theo mảng nên phù hợp hơn với các lượt "
        "quét lớn. Đây là thời gian trên máy chạy đã lưu, không phải "
        "tốc độ của một thiết bị QKD hoặc máy tính lượng tử thật."
    )

    r.h("3.7 Kết quả E91 và so sánh với BB84")
    good = r.pick("E07", "chsh", series="E91 fast, Eve=0", x="1")
    bad = r.pick("E07", "chsh", series="E91 fast, Eve=1", x="1")
    r.p(
        "E7 thay đổi mức chất lượng trạng thái rối, ký hiệu V, rồi đo "
        "CHSH khi không có Eve và khi Eve chặn toàn bộ. V càng lớn thì "
        "trạng thái càng gần trường hợp lý tưởng của mô hình. Backend "
        f"nhanh dùng {number(r.data['E07']['metadata']['config']['pairs'], 0)} "
        f"cặp mỗi lượt và lặp {good['n']} lần cho mỗi cấu hình."
    )
    r.fig(
        "07_e91", "Tương quan E91 giảm khi Eve can thiệp", "results/quick/E07_chsh.csv"
    )
    r.p(
        "Khi V tăng, cả hai đường CHSH đều đi lên nhưng đường có Eve "
        "thấp hơn rõ rệt. Ở chất lượng tốt nhất trong phép quét, CHSH "
        f"không có Eve là {number(good['value'], 3)}, vượt giới hạn Bell; "
        f"khi có Eve chỉ còn {number(bad['value'], 3)}, nằm dưới giới hạn. "
        "Eve đo rồi phát lại làm mất một phần tương quan vốn có của cặp "
        "rối. Khi V thấp, ngay cả kênh không có Eve cũng có thể không đủ "
        "điều kiện, nên hệ thống còn phải xét chất lượng nguồn."
    )
    r.p(
        "Trong chương trình, điều kiện tiếp tục dựa trên cả độ không "
        "chắc chắn của ước lượng CHSH, không chỉ nhìn đường trung bình "
        "vượt vạch Bell. Kết quả minh họa khả năng phát hiện kiểu can "
        "thiệp đã thử trong mô hình E91, chưa chứng minh an toàn trước "
        "mọi tấn công hay mọi sai lệch của detector."
    )
    bb = r.pick("E08", "rate", series="BB84 Eve=0", x="0")
    ee = r.pick("E08", "rate", series="E91 Eve=0", x="0")
    r.p(
        "E8 so sánh hai giao thức với cùng số lượt phát và mức nhiễu "
        f"lật bit. Khi không có Eve và không có nhiễu nền, BB84 cho "
        f"{number(bb['value'], 4)} bit khóa trên mỗi lượt phát, còn E91 "
        f"cho {number(ee['value'], 4)}. E91 dành nhiều lựa chọn đo cho "
        "kiểm tra tương quan nên tỷ lệ giữ bit khóa thấp hơn ở thiết "
        "lập này. Khi Eve chặn toàn bộ, cả hai đều không cấp khóa trong "
        "các lượt đã chạy. So sánh này dùng sửa sai lý tưởng và không "
        "đánh giá chi phí nguồn rối hay thiết bị quang ngoài thực tế."
    )

    r.h("3.8 Khoảng cách truyền và lượng khóa thu được")
    r.p(
        "E6 tính các đường tốc độ khóa từ mô hình suy hao và nhiễu của "
        "thiết bị dò. Ba đường lần lượt là BB84 dùng xung yếu, BB84 có "
        "trạng thái mồi để ước lượng phần tín hiệu dùng được, và E91. "
        "Đây là tính toán theo mô hình khi có rất nhiều dữ liệu, không "
        "phải phép đo trên một tuyến cáp thật."
    )
    r.fig(
        "05_distance",
        "Lượng khóa giảm theo chiều dài đường truyền",
        "results/quick/E06_distance.csv",
    )
    r.p(
        "Cả ba đường đều giảm khi chiều dài tăng. Tín hiệu suy hao làm "
        "số lượt dò hữu ích ít đi, còn nhiễu nền của detector trở nên "
        "đáng kể hơn so với tín hiệu. Đường E91 giảm nhanh trong thiết "
        "lập này vì cần ghi nhận được cả hai phía của cặp rối. Trục dọc "
        "dùng thang log, nên một khoảng cách nhỏ giữa hai mức trên hình "
        "có thể tương ứng với chênh lệch nhiều lần về tốc độ."
    )
    r.p(
        "Chiều dài E91 ở đây là chiều dài mỗi nhánh, và tốc độ tính "
        "trên mỗi cặp phát; BB84 tính trên mỗi xung phát. Đường xung yếu "
        "chưa tính đầy đủ tấn công tách photon, còn đường trạng thái "
        "mồi mới là ước lượng theo mô hình. Vì vậy, không dùng thứ tự "
        "các đường để kết luận giao thức nào an toàn hơn hoặc xác định "
        "khoảng cách triển khai tối đa ngoài thực tế."
    )

    r.h("3.9 Demo truyền tin và mã hóa tệp")
    if "normal" in r.data["chat"] and "eve" in r.data["chat"]:
        normal = r.data["chat"]["normal"][-1]
        eve = r.data["chat"]["eve"][-1]
        r.p(
            "Ở demo truyền tin, nhật ký phiên bình thường ghi nhận "
            f"QBER {percent(normal['metrics']['qber'])} và chuyển đến "
            "trạng thái KEY_IN_USE, nghĩa là khóa đã được cho phép dùng "
            "cho tin nhắn đầu tiên. Khi bật Eve, phiên đối chiếu có QBER "
            f"{percent(eve['metrics']['qber'])} và dừng ở trạng thái ABORT "
            "do vượt ngưỡng. Nhật ký này cho thấy sự thay đổi trong "
            "quyết định cấp khóa; nó không phải bản ghi xác nhận mọi "
            "tin nhắn đã được Bob nhận."
        )
    r.p(
        "Dữ liệu ứng dụng và thông điệp xác thực đi qua TCP nội bộ; "
        "phần lượng tử vẫn là mô phỏng trong cùng tiến trình. Demo giúp "
        "quan sát việc chỉ cấp khóa khi phiên đạt điều kiện, nhưng chưa "
        "kiểm tra được độ trễ mạng diện rộng hoặc việc đồng bộ thiết "
        "bị giữa hai điểm ở xa."
    )
    integrities = [x for x in r.data["E10"]["rows"] if x["metric"] == "integrity"]
    r.p(
        "E10 kiểm tra toàn bộ luồng từ BB84 có HMAC đến mã hóa và giải "
        "mã tệp. Nhóm thử văn bản, ảnh PNG và dữ liệu nhị phân ngẫu nhiên "
        "bằng cả hai thuật toán. Sau giải mã, chương trình so mã băm "
        "SHA 256 của tệp gốc và tệp nhận để kiểm tra chúng có giống nhau. "
        f"Có {len(integrities)} tổ hợp loại tệp và thuật toán; mỗi tổ hợp "
        f"đạt {integrities[0]['successes']}/{integrities[0]['n']} lượt "
        "khôi phục đúng. Kết quả xác nhận chức năng hoạt động với các "
        "mẫu đã thử, chưa phải bằng chứng khóa mô phỏng có tính bí mật thật."
    )
    r.p(
        "E9 đo riêng thời gian xử lý tệp sau khi đã có khóa, gồm chia "
        "khối, dẫn xuất khóa và đọc ghi đĩa. Biểu đồ dưới chọn dữ liệu "
        "văn bản để dễ so sánh. Điểm biểu diễn trung vị; thanh sai số "
        "là khoảng tứ phân vị của các lượt đo, không phải khoảng tin cậy."
    )
    r.fig(
        "08_cipher",
        "Tốc độ xử lý tệp văn bản của hai thuật toán",
        "results/quick/E09_cipher_benchmark.csv",
    )
    r.p(
        "Trong dải kích thước đã thử, tốc độ theo MB/s nhìn chung tăng "
        "khi tệp lớn hơn. Với tệp nhỏ, chi phí mở tệp và chuẩn bị xử lý "
        "chiếm tỷ lệ lớn; khi tệp lớn, chi phí này được chia trên nhiều "
        "byte hơn. Hai đường có thể gần nhau hoặc đổi thứ tự ở một vài "
        "điểm. Số đo gồm cả đọc ghi tệp và phụ thuộc máy chạy, nên chưa "
        "đủ để khẳng định một thuật toán luôn nhanh hơn trong mọi ứng dụng."
    )

    r.h("3.10 Sửa bản mã và giả mạo kênh trao đổi")
    tamper = [x for x in r.data["E11"]["rows"] if x["metric"] == "tamper"]
    r.p(
        "E11 chủ động sửa phần đầu tệp, thay đổi nội dung bản mã, sửa "
        "thẻ xác thực, cắt ngắn tệp và đảo thứ tự khối. Mỗi lỗi được thử "
        "riêng trên từng thuật toán để xác định hệ thống có từ chối "
        f"dữ liệu không. Trong {len(tamper)} tổ hợp lỗi và thuật toán, "
        f"mỗi tổ hợp đều từ chối {tamper[0]['successes']}/{tamper[0]['n']} "
        "lượt. Các phép thử này cho thấy việc kiểm tra toàn vẹn đã xử "
        "lý đúng những dạng sửa đổi được đưa vào thí nghiệm."
    )
    r.p(
        "Thí nghiệm còn cố tình lặp nonce trên dữ liệu thử để quan sát "
        "rò rỉ quan hệ giữa hai bản rõ. Kết quả phát hiện rò rỉ ở đây là "
        "dấu hiệu nguy hiểm, không phải một ca bảo vệ thành công. Vì "
        "vậy, ngoài chọn thuật toán, ứng dụng phải bảo đảm không lặp "
        "nonce với cùng khóa. Kết quả từ chối các tệp đã sửa cũng không "
        "thể suy rộng thành khả năng chống mọi cách giả mạo."
    )
    off = r.pick("E12", "mitm", x="no HMAC")
    on = r.pick("E12", "mitm", x="HMAC")
    r.p(
        "E12 xét một kiểu tấn công khác: Eve tạo hai liên kết riêng và "
        "giả vai đối tác với từng phía trên kênh trao đổi thông thường. "
        "Nhóm chạy cùng kịch bản khi bỏ xác thực và khi bật HMAC. Khác "
        "với E1, mục tiêu ở đây là kiểm tra danh tính phía trao đổi, "
        "không chỉ quan sát lỗi do đo tín hiệu lượng tử."
    )
    r.fig(
        "09_authentication",
        "Xác thực kênh trao đổi ngăn kịch bản giả mạo đã thử",
        "results/quick/E12_classical_mitm.csv",
    )
    r.p(
        f"Khi không có HMAC, Eve thành công {off['successes']}/{off['n']} "
        f"lượt. Khi bật HMAC, Eve thành công {on['successes']}/{on['n']} "
        f"lượt và cả hai phía đều từ chối thẻ giả trong {on['both_tags_rejected']} "
        "lượt. Chênh lệch này cho thấy xác thực kênh cổ điển là thành "
        "phần bắt buộc của thiết kế. Việc không quan sát thấy thành "
        "công trên mẫu hữu hạn không có nghĩa xác suất giả mạo bằng "
        "không. Kết quả còn dựa trên việc khóa HMAC được chia sẻ và giữ "
        "bí mật đúng cách."
    )

    r.h("3.11 Đánh giá bộ giám sát")
    ci = r.pick("E13", "design_bits", series="ci · Q₀=0.01", x="0.01")
    sprt = r.pick("E13", "design_bits", series="sprt · Q₀=0.01", x="0.01")
    power_ci = r.pick("E13", "design_power", series="ci · Q₀=0.01", x="0.01")
    power_sp = r.pick("E13", "design_power", series="sprt · Q₀=0.01", x="0.01")
    r.p(
        "E13 so sánh các cách theo dõi lỗi. CI kiểm tra trên một mẫu có "
        "kích thước cố định; SPRT cập nhật quyết định theo từng mẫu đến; "
        "CUSUM theo dõi mức thay đổi tích lũy. Nhóm thử Eve chặn đều và "
        "Eve dồn hành vi chặn về cuối phiên, đồng thời theo dõi cả báo "
        "động đúng lẫn báo động nhầm trên dữ liệu không bị tấn công. "
        "Hình dưới chọn nhiễu nền 1% để thấy rõ khác biệt giữa hai cách "
        "Eve can thiệp."
    )
    r.fig(
        "10_monitor",
        "Khả năng báo động phụ thuộc cách Eve can thiệp",
        "results/quick/E13_detectors.csv",
    )
    r.p(
        "Khi Eve chặn đều, tỷ lệ báo động đúng nhìn chung tăng theo tỷ "
        "lệ chặn. Tuy nhiên, khi Eve bắt đầu muộn, đường SPRT thấp ở "
        "nhiều mức chặn của phép thử. Nguyên nhân là SPRT có thể đã "
        "chấp nhận đoạn đầu là bình thường và kết thúc kiểm tra trước "
        "khi thay đổi xuất hiện. CUSUM vẫn theo dõi thay đổi nên phản "
        "ứng tốt hơn với kịch bản chặn muộn này. Điều đó cho thấy cần "
        "xem cả thời điểm tấn công khi chọn cách giám sát."
    )
    r.p(
        "Trong phép so riêng CI và SPRT với cùng giả thuyết thiết kế "
        "và mức sai số mục tiêu, CI dùng trung bình "
        f"{number(ci['value'], 1)} bit, còn SPRT dùng "
        f"{number(sprt['value'], 1)} bit ở nhiễu nền 1%. Số lượt báo động "
        f"tương ứng là {power_ci['successes']}/{power_ci['n']} và "
        f"{power_sp['successes']}/{power_sp['n']}. SPRT quyết định sớm "
        "hơn ở tình huống này, nhưng kết quả chặn muộn cho thấy lợi "
        "thế đó không áp dụng cho mọi cách tấn công."
    )
    r.p(
        "Hạ ngưỡng thường giúp thấy dấu hiệu sớm hơn nhưng cũng có thể "
        "làm tăng báo động nhầm. Độ trễ được lưu chỉ tính trên các lượt "
        "có báo động và tính từ đầu mẫu, nên phải xem cùng tỷ lệ bỏ sót. "
        "Một bộ phát hiện báo nhanh trên vài lượt thành công chưa chắc "
        "phù hợp nếu bỏ qua nhiều lượt tấn công khác."
    )

    r.h("3.12 Kiểm tra bổ sung và giới hạn của mô hình")
    passes = [x for x in r.data["E14"]["rows"] if x["metric"] == "pass"]
    r.p(
        "E14 kiểm tra một số đặc điểm thống kê của chuỗi bit như mức "
        "cân bằng và các dạng lặp. Tổng cộng có "
        f"{sum(int(x['successes']) for x in passes)}/"
        f"{sum(int(x['n']) for x in passes)} phép thử riêng lẻ đạt ngưỡng "
        "trong bộ mẫu đã lưu. Kết quả này giúp phát hiện một số sai lệch "
        "dễ thấy, nhưng chuỗi qua kiểm định vẫn có thể dự đoán được. "
        "Đặc biệt, đầu ra mạch Hadamard trên Aer vẫn đến từ bộ mô phỏng, "
        "không phải nguồn ngẫu nhiên lượng tử vật lý."
    )
    r.p(
        "E15 là phần tính toán minh họa ảnh hưởng của Grover và Shor "
        "đến các bài toán mật mã, không phải thử phá khóa thật. Phần "
        "này nhắc rằng độ dài khóa, lượng thông tin bí mật và giả định "
        "về năng lực tấn công đều cần được xét cùng nhau. Tăng độ dài "
        "đầu ra bằng HKDF không tạo thêm bí mật nếu nguồn khóa ban đầu "
        "đã dự đoán được."
    )
    for text in (
        "Các trạng thái lượng tử, suy hao và detector đều là mô hình phần mềm. "
        "Mô phỏng chưa phản ánh đầy đủ sai số thiết bị, ánh sáng ngoài ý muốn "
        "hay những đường rò thông tin của phần cứng.",
        "Các tấn công được thử có kịch bản cụ thể. Kết quả phát hiện chặn và "
        "phát lại chưa bao quát tấn công tổng quát, tấn công làm mù detector "
        "hoặc khai thác nguồn phát. Mô hình xung yếu chưa có quy trình trạng "
        "thái mồi đầy đủ để đánh giá mọi tấn công tách photon.",
        "Điều kiện tạo khóa và phần dự phòng thống kê được giản lược phục vụ "
        "đồ án. Chưa có chứng minh rằng toàn bộ hệ thống giữ an toàn khi "
        "kết hợp với mọi ứng dụng hoặc khi Eve dùng mọi chiến lược có thể.",
        "Seed làm cho thí nghiệm lặp lại được nhưng cũng khiến dữ liệu mô "
        "phỏng có thể dự đoán. Khóa bắt nguồn từ mô phỏng có seed không được "
        "dùng để bảo vệ thông tin thật, kể cả khi bước mã hóa sử dụng thư "
        "viện và nonce đúng cách.",
        "Demo mạng chỉ chạy trên cùng máy. Các phép đo thời gian chịu ảnh "
        "hưởng của đọc ghi đĩa, tải hệ thống và cấu hình máy; chúng không "
        "thay thế được thử nghiệm giữa các thiết bị ở xa.",
        "Bộ chạy nhanh có ít lượt lặp ở nhiều thực nghiệm. Những tỷ lệ đạt "
        "toàn bộ hoặc không có lỗi chỉ mô tả mẫu đã thử, không bảo đảm "
        "các lần chạy khác sẽ luôn cho cùng kết quả.",
    ):
        r.p(text, bullet=True)

    r.h("3.13 Nhận xét chung và hướng phát triển")
    r.p(
        "Qua các thực nghiệm, nhóm quan sát được sự tăng QBER khi Eve "
        "chặn nhiều tín hiệu hơn, sự giảm lượng khóa khi nhiễu và khoảng "
        "cách tăng, cùng vai trò của cỡ mẫu trong việc quyết định có "
        "tiếp tục phiên hay không. E91 bổ sung cách quan sát tương quan "
        "cặp rối. Các kết quả ứng dụng cho thấy luồng cấp khóa, mã hóa "
        "và kiểm tra toàn vẹn hoạt động với những trường hợp đã thử."
    )
    r.p(
        "Đồ án giúp làm rõ rằng QKD cần đi cùng xác thực kênh trao đổi, "
        "quản lý khóa và mã hóa dữ liệu đúng cách. Nếu phát triển tiếp, "
        "nhóm sẽ tăng số lượt lặp ở các vùng gần ngưỡng dừng, bổ sung "
        "mô hình nguồn và detector sát thực tế hơn, rồi thử ứng dụng "
        "trên hai máy riêng. Để tiến tới triển khai thật còn cần nguồn "
        "ngẫu nhiên phù hợp, thiết bị vật lý và một đánh giá an toàn "
        "đầy đủ hơn phạm vi mô phỏng môn học."
    )


def references(r: Report) -> None:
    """Keep bibliography identifiers outside prose and select core sources only."""
    r.h("TÀI LIỆU THAM KHẢO", 1)
    bib = (ROOT / "docs/references.bib").read_text(encoding="utf-8-sig")
    selected = (
        "bennett1984bb84",
        "ekert1991e91",
        "brassard1994cascade",
        "tomamichel2012finite",
        "rfc5869",
        "nist80038d",
        "rfc8439",
        "wootters1982cloning",
        "clauser1969chsh",
        "ma2005practical",
    )
    # Use actual retained BibTeX keys and fields rather than inventing entries.
    entries = re.split(r"(?=@\w+\s*\{)", bib)
    chosen = [
        e
        for e in entries
        if any(
            e.startswith("@" + kind + "{" + key + ",")
            for key in selected
            for kind in ("article", "inproceedings", "misc", "techreport")
        )
    ]
    if len(chosen) != len(selected):
        raise ValueError("Missing retained bibliography entry")
    for index, entry in enumerate(chosen, 1):
        fields: dict[str, str] = {}
        for name in ("author", "title", "year", "url", "doi"):
            match = re.search(name + r"\s*=\s*\{([^\n]+)\}", entry)
            if match:
                fields[name] = (
                    match.group(1).rstrip(",").replace("{", "").replace("}", "")
                )
        if fields.get("title"):
            r.p(
                f"[{index}] {fields.get('author', '')}. {fields['title']}. "
                f"{fields.get('year', '')}. {fields.get('url', fields.get('doi', ''))}"
            )


def verify() -> dict[str, Any]:
    """Validate report constraints and every cited evidence digest."""
    doc = Document(OUTPUT)
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    text = "\n".join(p.text for p in doc.paragraphs)
    chapters = [
        p.text
        for p in doc.paragraphs
        if p.style.name == "Heading 1" and p.text.startswith("CHƯƠNG")
    ]
    if len(chapters) != 3:
        raise ValueError("Report must have three chapters")
    if len(doc.tables) != len(manifest["tables"]) + 1:
        raise ValueError("A report table is missing or has no caption")
    original = Document(BACKUP)
    if [c.text for row in doc.tables[0].rows for c in row.cells] != [
        c.text for row in original.tables[0].rows for c in row.cells
    ]:
        raise ValueError("Student information on the cover was changed")
    if "JST-UD" in text:
        raise ValueError("Reference codes must not occur in prose")
    with ZipFile(OUTPUT) as package:
        xml = package.read("word/document.xml").decode()
    equations = len(re.findall(r"<m:oMath[ >]", xml))
    if equations != manifest["equations"] or equations < 20:
        raise ValueError("Core theoretical equations are missing")
    if len(manifest["figures"]) != 10:
        raise ValueError("Missing report figures")
    archive = json.loads((DATA / "summary.json").read_text(encoding="utf-8")).get(
        "source_archive", {}
    )
    for item in manifest["inputs"]:
        path = ROOT / item["path"]
        if path.exists():
            actual = digest(path)
        elif item["path"] in archive:
            actual = hashlib.sha256(archive[item["path"]].encode("utf-8")).hexdigest()
        else:
            raise FileNotFoundError(path)
        if actual != item["sha256"]:
            raise ValueError("Retained evidence changed: " + item["path"])
    if digest(Path(__file__)) != manifest["builder_sha256"]:
        raise ValueError("Report builder changed after the document was built")
    counts = manifest["chapter_words"]
    if len(doc.sections) != 3:
        raise ValueError("Expected separate cover, contents and numbered body sections")
    for section in doc.sections[:2]:
        for part in (section.header, section.footer):
            if any(p.text.strip() for p in part.paragraphs):
                raise ValueError("Cover and contents must have no header/footer text")
            if part._element.xpath('.//w:instrText[contains(text(), "PAGE")]'):
                raise ValueError("Unnumbered front matter contains a PAGE field")
    body = doc.sections[2]
    if body.start_type != WD_SECTION_START.NEW_PAGE:
        raise ValueError("Numbered body must start at a Next Page section break")
    if body.header.is_linked_to_previous or body.footer.is_linked_to_previous:
        raise ValueError("Body header/footer is still linked to front matter")
    if HEADER_TEXT not in body.header.paragraphs[0].text:
        raise ValueError("Incorrect report header")
    if FOOTER_TEXT not in body.footer.paragraphs[0].text:
        raise ValueError("Incorrect report footer")
    if body._sectPr.find(qn("w:pgNumType")).get(qn("w:start")) != "1":
        raise ValueError("Numbered section must restart at one")
    for part, edge in ((body.header, "bottom"), (body.footer, "top")):
        border = part._element.find(".//" + qn("w:" + edge))
        if border is None or border.get(qn("w:color")) != "000000":
            raise ValueError("Missing black header/footer rule")
    codes = " ".join(doc.element.body.xpath(".//w:instrText/text()"))
    codes += " ".join(doc.element.body.xpath(".//w:fldSimple/@w:instr"))
    for expected in ("TOC ", '\\c "Hình"', '\\c "Bảng"'):
        if expected not in codes:
            raise ValueError("Missing native linked contents/list field: " + expected)
    names = set(doc.element.body.xpath(".//w:bookmarkStart/@w:name"))
    for label, count in (
        ("Figure", len(manifest["figures"])),
        ("Table", len(manifest["tables"])),
    ):
        if any(f"QKD_{label}_{i}" not in names for i in range(1, count + 1)):
            raise ValueError("A figure/table caption has no bookmark")
    return {
        "chapters": len(chapters),
        "body_tables": len(manifest["tables"]),
        "equations": equations,
        "figures": len(manifest["figures"]),
        "evidence_hashes_match": True,
        "student_information_preserved": True,
        "sections": len(doc.sections),
        "numbering_starts_at_figure_list": True,
        "chapter_words": counts,
        "docx_sha256": digest(OUTPUT),
    }


def main() -> None:
    """Build from retained evidence, record provenance, then check constraints."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()
    if not args.check_only:
        report = Report()
        report.front()
        chapter_one(report)
        chapter_two(report)
        chapter_three(report)
        references(report)
        report.doc.save(OUTPUT)
        summary = DATA / "summary.json"
        sources = [
            *report.evidence["source_files"],
            {"path": summary.relative_to(ROOT).as_posix(), "sha256": digest(summary)},
        ]
        for figure in report.figures:
            sources.append(
                {"path": figure["path"], "sha256": digest(ROOT / figure["path"])}
            )
        for source in (
            ROOT / "experiments/report_summary.py",
            ROOT / "docs/references.bib",
            ROOT / "tools/report_expansion_vi.py",
        ):
            sources.append(
                {"path": source.relative_to(ROOT).as_posix(), "sha256": digest(source)}
            )
        manifest = {
            "document": OUTPUT.relative_to(ROOT).as_posix(),
            "git_commit": subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
            ).strip(),
            "cover_preserved": True,
            "backup": BACKUP.relative_to(ROOT).as_posix(),
            "inputs": sources,
            "figures": report.figures,
            "tables": report.tables,
            "equations": report.equations,
            "headings": report.headings,
            "chapter_words": report.chapter_words,
            "builder_sha256": digest(Path(__file__)),
            "library_versions": {"python-docx": version("python-docx")},
        }
        MANIFEST.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    result = verify()
    target = ROOT / "results/report_build/docx_check.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
