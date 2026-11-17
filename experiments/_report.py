"""Summarize measured output and assumptions for the Vietnamese report."""

from _suite import Experiment, Row

NOTES = (
    "Ghép lỗi chặn–phát lại và lật bit qua XOR. Các điểm Aer dùng cỡ mẫu nhỏ hơn.",
    "Cận Hoeffding làm phiên dừng sớm hơn ngưỡng QBER tiệm cận. "
    "Tỷ lệ dừng còn tính trường hợp độ dài khóa hữu hạn không dương.",
    "Báo phát hiện khi mẫu lý tưởng có ít nhất một bit sai. "
    "Phép thử này dùng mô hình nhị thức với Eve chặn toàn phần.",
    "Sàng lọc giữ số bit đo được. Các bước sau ghi không bit khi phiên dừng. "
    "Hệ số Cascade chỉ tính trên các phiên hiệu chỉnh có entropy mẫu dương. "
    "Độ dài cuối được tính từ lượng rò quan sát và chi phí xác minh.",
    "Mốc tiệm cận có cùng tỷ lệ sàng lọc và tỷ lệ bit công khai. "
    "Cận QBER, thẻ xác minh và ngân sách bí mật làm giảm tốc độ khóa hữu hạn.",
    "Đường tiệm cận dùng mô hình suy hao và đếm tối, khoảng cách tính theo mỗi nhánh. "
    "Đường BB84 xung yếu là ước lượng lạc quan bỏ qua PNS. Đường mồi dùng cận "
    "chân không + mồi yếu. E91 tính theo cặp phát.",
    "Cổng Bell dùng cận dưới CHSH và ngưỡng 2. QBER lấy từ toàn bộ cặp giữ khóa. "
    "Chặn–phát lại Z/X toàn phần làm giảm tương quan còn một nửa.",
    "Tỷ lệ sàng lọc tính trên lượt dò hoặc cặp trùng phùng. "
    "Tỷ lệ dừng bao gồm toàn bộ quy trình. Cột bell_rejections đếm các lượt E91 "
    "dừng tại cổng Bell. Tốc độ tính cả các phiên không tạo khóa. "
    "Thời gian đo trên backend NumPy với EC lý tưởng. BB84 dùng nguồn đơn photon "
    "và đồng bộ cơ sở phát–đo. E91 cần nguồn cặp rối, hai nhánh quang và đo "
    "trùng phùng để ước lượng CHSH. E6 so sánh mô hình tốc độ theo khoảng cách.",
    "Trung vị và IQR tính sau một lượt làm nóng cho từng cấu hình. "
    "Phép đo gồm I/O tệp, HKDF và chia khối. "
    "Hỗ trợ AES-NI và tải máy ảnh hưởng kết quả.",
    "Mỗi lượt dùng một phiên BB84 có HMAC. Đối chiếu SHA-256 trên tệp đã giải mã. "
    "Thời gian mã hóa và giải mã chỉ tổng hợp các phiên đã tạo khóa.",
    "Mỗi lỗi sửa tệp được thử độc lập. Thí nghiệm cố ý lặp nonce trên dữ liệu giả "
    "để kiểm tra XOR bản rõ. Không lặp nonce trong sử dụng thực tế.",
    "Eve chạy hai liên kết với hai đầu cuối. Cột both_tags_rejected đếm số "
    "lượt cả hai bên từ chối thẻ HMAC do Eve tạo.",
    "ROC quét ngân sách α hoặc ngưỡng Qmax. CI dùng cỡ mẫu cố định "
    "cho cùng giả thuyết thiết kế "
    "và mục tiêu α/β. Độ trễ chỉ tính ở lượt báo động kể từ bit đầu. "
    "Eve thích nghi dời toàn bộ lượt chặn về cuối, giữ tỷ lệ chặn trung bình.",
    "SP 800-22 đo sai lệch trong mẫu. Aer lấy mẫu giả ngẫu nhiên qua mạch Hadamard. "
    "Một số phép thử có thể trượt ở mức α ngay trên nguồn không lệch.",
    "Các hàng Grover ghi số mũ truy vấn tìm khóa. Các hàng Shor ghi mô hình "
    "đa thức và để trống số mũ. Chi phí cổng, độ sâu và sửa lỗi cần mô hình riêng.",
)


def _number(row: Row, key: str) -> float:
    """Read a numeric value from an experiment result."""
    value = row[key]
    assert isinstance(value, int | float)
    return float(value)


def interpretation(exp: Experiment) -> str:
    """Combine the experiment assumptions and a reproducible result summary."""
    note = NOTES[exp.number - 1]
    compare = [
        r
        for r in exp.rows
        if all(r[k] is not None for k in ("reference", "low", "high"))
    ]
    if compare and exp.number != 5:
        misses = sum(
            not _number(r, "low") <= _number(r, "reference") <= _number(r, "high")
            for r in compare
        )
        note += (
            f" Có {misses}/{len(compare)} điểm có mốc nằm ngoài khoảng "
            "tin cậy riêng lẻ. Các khoảng chưa hiệu chỉnh cho nhiều phép so sánh."
        )
    if exp.number == 2:
        for series in dict.fromkeys(row["series"] for row in exp.rows):
            full_abort = [
                row
                for row in exp.rows
                if row["series"] == series
                and row["metric"] == "abort"
                and row["value"] == 1
            ]
            if full_abort:
                first = min(_number(row, "x") for row in full_abort)
                note += f" {series} dừng mọi lượt lần đầu tại Q={first:g}."
    if exp.number == 4:
        for series in dict.fromkeys(row["series"] for row in exp.rows):
            rows = [
                row
                for row in exp.rows
                if row["series"] == series and row["metric"] == "final_bits"
            ]
            values = [_number(row, "value") for row in rows]
            down = sum(a > b for a, b in zip(values, values[1:], strict=False))
            note += f" {series} có {down} bước giảm độ dài trung bình trên lưới."
    if exp.number == 5:
        last = max(exp.rows, key=lambda row: _number(row, "x"))
        measured, limit = (_number(last, k) for k in ("value", "reference"))
        note += (
            f" Tại N={last['x']}, tốc độ đo là {measured:.4g}, "
            f"mốc tiệm cận là {limit:.4g} bit/xung."
        )
    if exp.number == 6:
        for row in exp.rows:
            if row["metric"] == "cutoff_km":
                tail = (
                    f"chưa thấy điểm triệt tiêu đến {row['search_limit']} km"
                    if row["value"] is None
                    else f"điểm triệt tiêu khoảng {_number(row, 'value'):.2f} km"
                )
                note += f" Mô hình {row['series']} cho {tail}."
    if exp.number == 7:
        attacked = [
            row
            for row in exp.rows
            if row["metric"] == "bell_violation"
            and str(row["series"]).endswith("Eve=1")
        ]
        violations = sum(_number(row, "successes") for row in attacked)
        trials = sum(_number(row, "n") for row in attacked)
        note += f" Có {violations:g}/{trials:g} lượt Eve cho |S| > 2."
        for row in exp.rows:
            if row["metric"] == "chsh" and row["x"] == 1:
                note += f" Với V=1, {row['series']} cho S={_number(row, 'value'):.4f}."
    if exp.number in (10, 11, 12):
        relevant = [row for row in exp.rows if "successes" in row]
        counts = [
            f"{row['series']} / {row['x']} {row['successes']}/{row['n']}"
            for row in relevant
        ]
        note += " Số lượt ghi nhận theo điều kiện. " + " · ".join(counts) + "."
    if exp.number == 13:
        for row in exp.rows:
            if row["metric"] == "design_bits":
                power = next(
                    r
                    for r in exp.rows
                    if r["metric"] == "design_power" and r["series"] == row["series"]
                )
                note += (
                    f" Ở điểm thiết kế, {row['series']} dùng trung bình "
                    f"{_number(row, 'value'):.1f} bit và báo động "
                    f"{power['successes']}/{power['n']} lượt."
                )
        note += " Mẫu ít lượt cần xét khoảng tin cậy trước khi so tỷ lệ lỗi."
    if exp.number == 14:
        rows = [row for row in exp.rows if row["metric"] == "pass"]
        passed = sum(_number(row, "successes") for row in rows)
        total = sum(_number(row, "n") for row in rows)
        note += f" Có {passed:g}/{total:g} phép thử riêng lẻ đạt ngưỡng."
    return note


def result_table(exp: Experiment) -> list[str]:
    """Embed the principal E8 and E15 tables from the same rows as the CSVs."""
    if exp.number == 8:
        noise = min(_number(row, "x") for row in exp.rows)
        groups: dict[str, dict[str, Row]] = {}
        for row in exp.rows:
            if row["x"] == noise:
                groups.setdefault(str(row["series"]), {})[str(row["metric"])] = row
        lines = [
            f"So sánh tại xác suất lật bit nền {noise:g}.",
            "",
            "| Giao thức | Sàng lọc | Phiên dừng | Bit/lượt phát | ms/phiên |",
            "|---|---:|---:|---:|---:|",
        ]
        for name, rows in groups.items():
            metrics = ("sift_rate", "abort", "rate", "session_ms")
            values = [_number(rows[metric], "value") for metric in metrics]
            lines.append(
                f"| {name} | {values[0]:.2%} | {values[1]:.2%} "
                f"| {values[2]:.4g} | {values[3]:.3g} |"
            )
        return [*lines, ""]
    if exp.number == 15:
        classical = {
            row["x"]: row for row in exp.rows if row["series"] == "classical"
        }
        lines = [
            "| Thuật toán | Cỡ khóa (bit) | An toàn cổ điển (bit) "
            "| Tấn công lượng tử | Mô hình chi phí |",
            "|---|---:|---:|---|---|",
        ]
        for row in exp.rows:
            if row["series"] == "quantum":
                cost = (
                    f"Bậc 2^{_number(row, 'value'):g} truy vấn"
                    if row["value"] is not None
                    else "Đa thức"
                )
                strength = classical[row["x"]]["value"]
                lines.append(
                    f"| {row['x']} | {row['key_bits']} | {strength} "
                    f"| {row['attack']} | {cost} |"
                )
        return [*lines, ""]
    return []
