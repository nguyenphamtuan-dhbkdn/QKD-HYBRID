"""Vietnamese theory and design chapters grounded in the implemented QKD model."""

from __future__ import annotations

from typing import Any


def paragraphs(report: Any, *texts: str) -> None:
    """Keep each explanation as a short, connected paragraph."""
    for text in texts:
        report.p(text)


def chapter_one(r: Any) -> None:
    """Explain the physical assumptions and formulas used by the implementation."""
    r.h("CHƯƠNG 1 CƠ SỞ LÝ THUYẾT", 1)
    r.h("1.1 Bài toán phân phối khóa và phạm vi của QKD")
    paragraphs(
        r,
        "Khi Alice muốn gửi thông tin riêng cho Bob, hai bên cần một khóa để mã hóa "
        "và giải mã. Nếu gửi nguyên khóa trên đường truyền thông thường, người theo "
        "dõi đường truyền có thể lấy được khóa. Vì vậy, phân phối khóa là một bước "
        "riêng cần được giải quyết trước khi bảo vệ nội dung tin nhắn hoặc tệp.",
        "QKD khai thác tính chất của trạng thái lượng tử để hai bên tạo dữ liệu có "
        "tương quan và kiểm tra dấu hiệu can thiệp. Khóa cuối được rút ra từ dữ liệu "
        "đã qua sàng lọc, ước lượng lỗi, sửa sai và rút ngắn. Trong đồ án, Alice và "
        "Bob là hai bên trao đổi, còn Eve là bên nghe lén hoặc giả mạo.",
        "Cần phân biệt việc phân phối khóa với việc mã hóa nội dung. QKD cung cấp "
        "vật liệu khóa; AES GCM hoặc ChaCha20 Poly1305 sử dụng khóa để bảo vệ dữ "
        "liệu ứng dụng. Việc một phiên QKD thành công không có nghĩa phần quản lý "
        "tệp, số thứ tự thông điệp hoặc nonce có thể bỏ qua kiểm tra.",
        "Đồ án mô phỏng BB84 và E91 trên máy tính thông thường. Kết quả dùng để "
        "hiểu giao thức và đánh giá cách chương trình phản ứng với các tình huống "
        "đã đặt ra. Các nghiên cứu trước đây là cơ sở cho mô hình, nhưng bộ mô "
        "phỏng này chưa thay thế thiết bị quang học hoặc chứng minh an toàn cho "
        "một hệ thống triển khai thật.",
    )

    r.h("1.2 Qubit và hai cơ sở đo")
    paragraphs(
        r,
        "Bit thông thường có giá trị xác định là không hoặc một. Với qubit, trạng "
        "thái trước phép đo được biểu diễn bằng tổ hợp của hai trạng thái cơ sở. "
        "Các hệ số trong biểu diễn là biên độ xác suất; bình phương độ lớn của "
        "chúng quyết định xác suất nhận kết quả khi đo.",
    )
    r.equation(
        "|ψ⟩ = α|0⟩ + β|1⟩,     |α|² + |β|² = 1",
        "Trong đó |ψ⟩ là trạng thái qubit; |0⟩ và |1⟩ là các trạng thái của cơ sở "
        "Z; α và β là các biên độ, có thể là số phức. Điều kiện tổng bằng một "
        "bảo đảm tổng xác suất các kết quả đo bằng một.",
    )
    r.equation(
        "P(0) = |α|²,     P(1) = |β|²",
        "P(0) và P(1) lần lượt là xác suất nhận bit không và bit một khi đo "
        "theo cơ sở Z. Bộ mô phỏng lấy mẫu theo các xác suất này, thay vì "
        "truyền một hạt vật lý qua đường truyền thật.",
    )
    r.equation(
        "|+⟩ = (|0⟩ + |1⟩)/√2,     |−⟩ = (|0⟩ − |1⟩)/√2",
        "|+⟩ và |−⟩ tạo thành cơ sở X. Nếu chuẩn bị trạng thái thuộc X nhưng "
        "đo theo Z, hai kết quả có xác suất bằng nhau. Tình huống tương tự "
        "xảy ra khi chuẩn bị theo Z và đo theo X.",
    )
    paragraphs(
        r,
        "Nếu Bob dùng đúng cơ sở mà Alice đã chọn và kênh không gây lỗi, Bob "
        "thu được bit tương ứng với bit Alice gửi. Nếu dùng khác cơ sở, kết quả "
        "không cho Bob biết chắc bit gốc. BB84 sử dụng sự khác nhau này để vừa "
        "tạo dữ liệu chung, vừa làm cho việc đo trộm có thể để lại sai lệch.",
        "Trong backend Qiskit, phép đổi cơ sở được biểu diễn bằng cổng Hadamard "
        "và phép đo trên mạch. Backend nhanh tính trực tiếp xác suất rồi lấy "
        "mẫu bằng NumPy. Hai cách triển khai khác nhau về cách tính, nhưng phải "
        "phản ánh cùng quy tắc xác suất tại các điều kiện được đối chiếu.",
    )

    r.h("1.3 Phép đo và giới hạn sao chép trạng thái")
    paragraphs(
        r,
        "Eve không thể giả định rằng mình đọc được qubit mà không tác động đến "
        "nó. Khi chọn một cơ sở đo, Eve chỉ thu được kết quả của phép đo đó. "
        "Nếu cơ sở này không phù hợp với trạng thái Alice chuẩn bị, kết quả "
        "của Eve có tính ngẫu nhiên và tín hiệu gửi tiếp có thể khác tín hiệu gốc.",
        "Định lý không nhân bản cho biết không tồn tại một phép sao chép chung "
        "có thể tạo bản sao hoàn hảo cho mọi trạng thái lượng tử chưa biết. "
        "Trong phạm vi đồ án, điều cần nắm là Eve không được cấp khả năng "
        "sao chép hoàn hảo tín hiệu rồi chờ Alice công bố cơ sở để đọc lại.",
        "Tuy nhiên, nguyên lý này không có nghĩa mọi cuộc tấn công đều lập tức "
        "bị phát hiện. Đồ án chủ yếu xét Eve đo rồi chuẩn bị lại tín hiệu. "
        "Tấn công vào nguồn phát, detector hoặc phần mềm quản lý khóa cần "
        "những mô hình và phép kiểm tra khác.",
    )

    r.h("1.4 Quy trình BB84 và bước sàng lọc")
    paragraphs(
        r,
        "Alice chọn chuỗi bit cùng cơ sở chuẩn bị cho từng lượt phát. Bob "
        "chọn cơ sở đo độc lập. Sau khi truyền xong, hai bên thông báo cơ sở "
        "đã sử dụng qua kênh cổ điển được xác thực, rồi giữ các lượt có phát "
        "hiện tín hiệu và có cơ sở phù hợp. Họ không công khai toàn bộ giá "
        "trị bit được giữ lại.",
    )
    r.equation(
        "Pgiữ = pZ² + (1 − pZ)²",
        "pZ là xác suất mỗi bên chọn cơ sở Z, với giả định hai bên chọn độc "
        "lập và cùng phân bố. Pgiữ là tỷ lệ cùng cơ sở trên các lượt đã phát "
        "hiện; đây chưa phải tỷ lệ khóa cuối trên mọi xung phát.",
    )
    paragraphs(
        r,
        "Khi hai cơ sở được chọn cân bằng, trung bình một nửa số lượt phát "
        "hiện được giữ. Nếu đường truyền có suy hao, một phần xung đã mất "
        "trước khi tới bước này. Sau sàng lọc, hệ thống còn phải bỏ bit "
        "mẫu kiểm tra và trừ chi phí xử lý khóa, nên số bit khóa cuối thấp hơn.",
        "Một điểm dễ nhầm là xem hai chuỗi sau sàng lọc như khóa đã sẵn sàng. "
        "Thực tế, chúng có thể còn khác nhau do nhiễu hoặc sự can thiệp. "
        "Sàng lọc chỉ loại các trường hợp cơ sở không phù hợp; nó không tự "
        "sửa lỗi và cũng không tự đánh giá lượng thông tin Eve có thể biết.",
    )

    r.h("1.5 QBER và tấn công chặn phát lại")
    r.equation(
        "Q̂ = x/k",
        "Q̂ là QBER ước lượng; x là số vị trí Alice và Bob có bit khác nhau "
        "trong mẫu; k là số bit được so sánh công khai. Mẫu này bị loại "
        "khỏi dữ liệu dành cho khóa.",
    )
    paragraphs(
        r,
        "Trong kịch bản chặn và phát lại, Eve chọn một số tín hiệu để đo, "
        "sau đó phát tín hiệu mới theo kết quả đo của mình. Nếu Eve dùng "
        "hai cơ sở với xác suất bằng nhau, một phần phép đo sẽ sai cơ sở. "
        "Sai lệch xuất hiện khi Bob đo tín hiệu gửi lại ở các vị trí được giữ.",
    )
    r.equation(
        "QIR = p/4",
        "p là tỷ lệ tín hiệu Eve chặn; QIR là QBER trung bình do kiểu tấn "
        "công này trên kênh lý tưởng, với các cơ sở chọn cân bằng. Hệ số "
        "một phần tư đến từ khả năng Eve chọn sai cơ sở và khả năng Bob "
        "nhận bit sai sau lần đo đó.",
    )
    r.equation(
        "Q = e + QIR − 2eQIR",
        "e là xác suất lỗi lật bit nền độc lập; QIR là phần lỗi do nghe "
        "lén; Q là xác suất lỗi sau khi kết hợp hai cơ chế theo XOR. Hai "
        "lần lật cùng một bit có thể bù nhau, nên không cộng thẳng hai tỷ lệ.",
    )
    paragraphs(
        r,
        "Các biểu đồ nghe lén cần được đọc cùng đường nền. Nếu kênh có "
        "nhiễu sẵn, một số bit sai xuất hiện ngay cả khi Eve không hoạt "
        "động. QBER tăng cho thấy dữ liệu ít phù hợp hơn để tạo khóa, "
        "nhưng riêng QBER không chỉ ra chắc chắn nguồn gây lỗi.",
        "Đồ án phân biệt tỷ lệ tín hiệu bị chặn với tỷ lệ thông tin Eve "
        "biết về khóa cuối. Tỷ lệ chặn là đầu vào của kịch bản mô phỏng. "
        "Mức thông tin còn lại sau xử lý khóa cần được xét trong mô hình "
        "an toàn phù hợp, không suy ra trực tiếp chỉ từ tỷ lệ chặn.",
    )

    r.h("1.6 Suy hao kênh truyền và thiết bị dò")
    r.equation(
        "ηch = 10^(−aL/10),     η = ηdηch",
        "L là chiều dài sợi theo km; a là hệ số suy hao theo dB/km; ηch "
        "là tỷ lệ truyền qua của sợi; ηd là hiệu suất detector. η là "
        "xác suất ghi nhận tín hiệu đơn photon khi bỏ qua đếm tối.",
    )
    paragraphs(
        r,
        "Khi chiều dài tăng, tín hiệu hữu ích giảm theo hàm mũ. Việc gửi "
        "nhiều xung không bảo đảm Bob nhận được tương ứng nhiều bit. "
        "Nếu chỉ nhìn QBER trên số ít tín hiệu còn lại mà không xét tỷ "
        "lệ dò, có thể bỏ qua việc đường truyền đang mất phần lớn tín hiệu.",
        "Detector còn có thể báo một lần ghi nhận khi không có photon "
        "hữu ích, gọi là đếm tối. Khi tín hiệu mạnh, phần đóng góp này có "
        "thể nhỏ. Khi tín hiệu suy hao nhiều, đếm tối chiếm tỷ lệ đáng "
        "kể hơn và có thể làm tăng lỗi trên dữ liệu nhận được.",
    )
    r.equation(
        "Pcoinc ≈ ηAηB",
        "ηA và ηB là hiệu suất tổng của hai nhánh E91; Pcoinc là xác suất "
        "ghi nhận đồng thời hai phía, khi bỏ qua các hiệu ứng khác. Công "
        "thức giải thích vì sao mất mát ở cả hai nhánh ảnh hưởng mạnh "
        "đến lượng dữ liệu cặp rối dùng được.",
    )
    paragraphs(
        r,
        "Đường BB84 xung yếu trong thực nghiệm khoảng cách là một mốc "
        "ước lượng lạc quan vì chưa tính đầy đủ tấn công tách photon. "
        "Đường trạng thái mồi dùng mô hình ước lượng phần tín hiệu "
        "đơn photon, chưa phải một hệ thống mồi hoàn chỉnh. Vì vậy, "
        "đường tốc độ cao hơn không tự đồng nghĩa với an toàn hơn.",
    )

    r.h("1.7 E91 và kiểm tra tương quan Bell")
    r.equation(
        "|Φ⁺⟩ = (|00⟩ + |11⟩)/√2",
        "|Φ⁺⟩ là trạng thái cặp rối được bộ mô phỏng sử dụng; hai vị trí "
        "trong mỗi ket lần lượt thuộc Alice và Bob. Đây là quy ước của "
        "chương trình; cách chọn trạng thái và góc đo phải được hiểu cùng nhau.",
    )
    paragraphs(
        r,
        "Alice và Bob chọn thiết lập đo cho hai phía của cặp rối. Một "
        "số cặp thiết lập được dùng để tạo bit khóa, các cặp khác phục "
        "vụ kiểm tra tương quan. Dữ liệu đo được gom theo từng nhóm "
        "thiết lập trước khi tính chỉ số Bell.",
    )
    r.equation(
        "E(a,b) = V cos(a − b)",
        "a và b ở công thức này là góc đo Bloch của hai bên, không phải "
        "hệ số suy hao ở mục trước; V biểu diễn chất lượng trạng thái "
        "rối trong mô hình. E là tương quan trung bình giữa hai kết quả đo.",
    )
    r.equation(
        "S = E₀₀ − E₀₂ + E₂₀ + E₂₂,     Smax = 2√2 V",
        "S là chỉ số CHSH theo các nhóm thiết lập trong chương trình. "
        "Biểu thức bên phải là giá trị mô hình ở các góc được chọn khi "
        "không có nhiễu hoặc can thiệp bổ sung; giới hạn Bell cổ điển "
        "là hai đối với trị tuyệt đối của tổ hợp tương quan.",
    )
    r.equation(
        "Tiếp tục kiểm tra khóa khi S − zσS > 2",
        "σS là độ không chắc chắn ước lượng của S; z là hệ số dự phòng "
        "trong cấu hình. Chương trình dùng cận dưới này thay vì chỉ "
        "xét trung bình S vượt giới hạn; sau đó vẫn phải kiểm tra QBER "
        "và các điều kiện xử lý khóa.",
    )
    r.table("protocols", "So sánh các bước chính của BB84 và E91")
    paragraphs(
        r,
        "Bảng trên giúp phân biệt nguồn dữ liệu và cách kiểm tra của "
        "hai giao thức. Cả hai đều cần kênh cổ điển được xác thực và "
        "quy trình xử lý sau đo. Vi phạm Bell trong mô hình cũng chưa "
        "đủ để khẳng định thiết bị thật không có lỗ hổng detector hay "
        "cách chọn mẫu không gây sai lệch.",
    )

    r.h("1.8 Lấy mẫu và ngưỡng phát hiện")
    r.equation(
        "Qub = min(1, Q̂ + √[ln(1/εPE)/(2k)])",
        "Qub là cận trên QBER; Q̂ là tỷ lệ lỗi quan sát; k là cỡ mẫu "
        "công khai; εPE là tham số sai số ước lượng. Phần căn bậc hai "
        "là mức dự phòng mà chương trình cộng vào mẫu đo.",
    )
    r.equation(
        "Dừng phiên nếu Qub > Qmax hoặc k < kmin",
        "Qmax là ngưỡng QBER cấu hình; kmin là số bit kiểm tra tối thiểu. "
        "Điều kiện đủ mẫu được xét trước khi tạo ước lượng. Các ký hiệu "
        "này biểu diễn chính sách của mô phỏng, không phải giới hạn "
        "phổ quát cho mọi hệ thống QKD.",
    )
    paragraphs(
        r,
        "Cùng một QBER quan sát, mẫu ít có phần dự phòng lớn hơn mẫu "
        "nhiều. Vì vậy, phiên ngắn có thể bị dừng dù tỷ lệ lỗi nhìn "
        "qua khá thấp. Tương tự, yêu cầu εPE nhỏ hơn làm việc tiếp "
        "tục phiên thận trọng hơn. Đánh đổi này xuất hiện rõ trong "
        "thực nghiệm số xung và khóa hữu hạn.",
        "Cận Hoeffding ở đây là cách tính giản lược của đặc tả. "
        "Dữ liệu thực được chọn mẫu không hoàn lại, nên một phân "
        "tích khóa hữu hạn đầy đủ cần xét kỹ cách lấy mẫu và ngân "
        "sách sai số. Báo cáo sử dụng cận này để giải thích hành vi "
        "chương trình, không xem nó là chứng minh an toàn hoàn chỉnh.",
    )
    r.equation(
        "Pphát hiện = 1 − (3/4)^k",
        "Đây là xác suất thấy ít nhất một lỗi trong k bit của mô hình "
        "E3 khi Eve chặn toàn bộ và kênh không có nhiễu nền. Công "
        "thức không áp dụng như một bộ phát hiện chung trên kênh "
        "vốn đã có lỗi hoặc khi dữ liệu có phụ thuộc khác.",
    )
    paragraphs(
        r,
        "Báo động đúng là báo động khi tình huống có tấn công; báo "
        "động nhầm là báo động trên tình huống trung thực. Một cách "
        "kiểm tra báo động thường xuyên chưa chắc tốt nếu nó cũng "
        "làm dừng nhiều phiên bình thường. Vì vậy, đồ án theo dõi "
        "cả hai tỷ lệ cùng số mẫu cần để đưa ra quyết định.",
    )

    r.h("1.9 Sửa sai và khuếch đại riêng tư")
    paragraphs(
        r,
        "Cascade giúp Alice và Bob tìm lỗi bằng cách so chẵn lẻ của "
        "các khối bit. Khi chẵn lẻ không khớp, khối được chia nhỏ để "
        "tìm vị trí sai. Các lượt hoán vị làm thay đổi cách gom khối "
        "và hỗ trợ tìm những lỗi chưa thấy ở lượt trước. Chương trình "
        "còn kiểm tra lại hai chuỗi trước khi sử dụng chúng.",
        "Những bit chẵn lẻ được trao đổi là thông tin công khai. "
        "Mặc dù chúng không tiết lộ ngay từng bit khóa, chúng vẫn "
        "giảm lượng thông tin bí mật còn lại. Đây là lý do số bit "
        "sau sửa sai không thể tự động được giữ nguyên làm khóa cuối.",
    )
    r.equation(
        "h₂(q) = −q log₂(q) − (1 − q) log₂(1 − q)",
        "h₂ là entropy nhị phân; q là tỷ lệ lỗi. Hai đầu mút được "
        "lấy theo giới hạn liên tục. Hàm này biểu diễn mức không "
        "chắc chắn của lỗi và xuất hiện trong cách ước lượng lượng "
        "thông tin cần trừ khi tạo khóa.",
    )
    r.equation(
        "ΔPA = 2 log₂(1/εPA)",
        "εPA là tham số dành cho bước rút ngắn khóa; trong chương "
        "trình nó dùng giá trị eps_sec. ΔPA là phần dự phòng bị "
        "trừ khỏi độ dài, không phải số bit được truyền cho Eve.",
    )
    r.equation(
        "ℓ = ⌊n[1 − h₂(Qub)] − leakEC − leakV − ΔPA⌋",
        "n là số bit chưa công khai còn lại trước rút ngắn; leakEC "
        "là lượng rò ghi nhận ở bước sửa sai; leakV là chi phí xác "
        "minh; ℓ là số bit đầu ra dự kiến, làm tròn xuống. Nếu ℓ "
        "không dương, phiên dừng. Đây là công thức giản lược theo "
        "các giả định nguồn đơn photon của đồ án.",
    )
    r.equation(
        "K = T x mod 2",
        "x là chuỗi bit đã sửa và xác minh; T là ma trận Toeplitz "
        "nhị phân; K là khóa rút ngắn. Mỗi bit đầu ra là phép cộng "
        "modulo hai của một số bit đầu vào do T lựa chọn.",
    )
    r.equation(
        "r∞ = max{0, 1 − (1 + fEC)h₂(Q)}",
        "r∞ là phần khóa ước lượng trên bit dành cho khóa khi có rất nhiều "
        "dữ liệu; fEC là hệ số chi phí sửa sai so với mức lý tưởng. Muốn "
        "đổi sang bit trên mỗi xung còn phải xét xác suất dò, sàng lọc và "
        "phần mẫu công khai. Công thức này không thay cho độ dài hữu hạn ℓ.",
    )
    paragraphs(
        r,
        "Seed tạo ma trận Toeplitz có thể công khai sau khi được "
        "chọn độc lập với dữ liệu khóa. Trong cài đặt, seed này lấy "
        "từ ngẫu nhiên hệ điều hành và hai bên dùng cùng seed để "
        "có cùng phép băm. Việc công khai seed không có nghĩa được "
        "công khai chuỗi bit đầu vào hoặc toàn bộ khóa cuối.",
        "Bước rút ngắn không tạo bí mật từ một chuỗi mà Eve đã "
        "biết hoàn toàn. Nó chỉ có ý nghĩa khi đầu vào còn đủ phần "
        "không chắc chắn đối với Eve và độ dài đầu ra được chọn "
        "phù hợp. Đặc biệt, khóa từ dữ liệu mô phỏng có seed dự "
        "đoán được vẫn không an toàn để sử dụng ngoài thực tế.",
    )

    r.h("1.10 Xác thực và mã hóa nội dung")
    paragraphs(
        r,
        "Kênh cổ điển truyền cơ sở đo, vị trí mẫu và thông tin sửa "
        "sai. Nội dung này có thể được quan sát công khai nhưng "
        "phải được bảo vệ khỏi sửa đổi và giả mạo. Đồ án dùng "
        "HMAC với khóa chia sẻ ban đầu; khi bỏ xác thực, Eve có "
        "thể tạo hai liên kết và đóng vai đối tác của từng bên.",
    )
    r.equation(
        "tag = HMAC(Kauth, thông điệp và ngữ cảnh)",
        "Kauth là khóa xác thực đã được hai bên chia sẻ; tag là "
        "thẻ kiểm tra. Ngữ cảnh trong chương trình gồm mã phiên, "
        "chiều truyền, số thứ tự và loại thông điệp để ràng buộc "
        "nội dung với đúng lần trao đổi.",
    )
    r.equation(
        "Kứng dụng = HKDF(Kcuối, salt, info)",
        "Kcuối là vật liệu khóa sau xử lý; salt là giá trị công "
        "khai cho lần dẫn xuất; info là nhãn mục đích sử dụng. "
        "Các nhãn khác nhau tạo khóa dành cho những cách dùng "
        "khác nhau. Đây là cách viết gọn của HKDF Extract và Expand.",
    )
    r.equation(
        "(C, tag) = AEAD.Encrypt(K, N, M, A)",
        "K là khóa; N là nonce; M là bản rõ; A là dữ liệu liên "
        "kết được xác thực nhưng không che nội dung; C là bản "
        "mã. tag cho phép bên nhận kiểm tra tính hợp lệ trước "
        "khi chấp nhận dữ liệu.",
    )
    paragraphs(
        r,
        "AES GCM và ChaCha20 Poly1305 đều đòi hỏi không lặp "
        "nonce với cùng khóa. Lặp nonce có thể làm lộ quan hệ "
        "giữa các bản rõ dù khóa chưa bị công khai. Đồ án dùng "
        "phần ngẫu nhiên kết hợp bộ đếm và kiểm tra giới hạn "
        "sử dụng, thay vì sinh nonce từ bộ ngẫu nhiên mô phỏng.",
        "Tóm lại, các lớp có trách nhiệm riêng nhưng phụ thuộc lẫn nhau. Đo và kiểm "
        "tra thống kê quyết định có thể tiếp tục tạo khóa; xác thực bảo vệ danh "
        "tính và thông điệp trao đổi; mã hóa xác thực bảo vệ nội dung ứng dụng. Bỏ "
        "sót một lớp có thể làm hỏng mục tiêu của toàn bộ hệ thống dù các lớp khác "
        "vẫn chạy đúng.",
    )


def chapter_two(r: Any) -> None:
    """Explain the system through data flow, decisions and reproducibility."""
    r.h("CHƯƠNG 2 THIẾT KẾ HỆ THỐNG", 1)
    r.h("2.1 Yêu cầu và ranh giới mô phỏng")
    paragraphs(
        r,
        "Hệ thống được xây dựng để theo dõi trọn vẹn một phiên phân phối khóa, từ "
        "chuẩn bị tín hiệu đến sử dụng khóa trong ứng dụng. Người chạy có thể thay "
        "đổi giao thức, số lượt phát, mức nhiễu và tỷ lệ Eve can thiệp. Đầu ra cần "
        "cho biết lượng dữ liệu qua từng bước, điều kiện dừng và các chỉ số phục vụ "
        "đánh giá.",
        "Về chức năng, chương trình phải phân biệt phiên không đủ dữ liệu với phiên "
        "có lỗi quá cao. Phiên không tạo được khóa không được phép cấp một chuỗi "
        "ngẫu nhiên khác để ứng dụng tiếp tục như bình thường. Quyết định dừng phải "
        "được truyền đến phần gửi tin hoặc mã hóa tệp để người dùng hiểu vì sao "
        "chưa dùng được khóa.",
        "Về phạm vi, kênh lượng tử là mô hình tính toán trong chương trình. Demo "
        "TCP có trao đổi dữ liệu giữa hai đầu kết nối trên cùng máy nhưng không "
        "truyền photon. Việc tách Alice và Bob trong mã giúp kiểm tra luồng trao "
        "đổi, chưa mô tả mọi vấn đề triển khai giữa hai thiết bị ở xa.",
        "Các yêu cầu về khả năng kiểm tra cũng được đặt ngay từ đầu. Cấu hình phải "
        "được lưu với kết quả; dữ liệu công khai phải đủ giải thích quyết định; "
        "nhật ký không được chứa toàn bộ khóa. Nhờ vậy, việc đánh giá không chỉ dựa "
        "vào một dòng thông báo thành công ở cuối chương trình.",
    )

    r.h("2.2 Kiến trúc và luồng dữ liệu")
    paragraphs(
        r,
        "Luồng chính gồm mô phỏng nguồn và kênh, mô phỏng đo, xử lý dữ liệu sau đo, "
        "theo dõi phiên và lớp ứng dụng. Cấu hình đi vào từ đầu; số đo và trạng "
        "thái phiên đi về phần ghi kết quả. Khóa chỉ được chuyển sang lớp ứng dụng "
        "sau khi các điều kiện tạo khóa và chính sách sử dụng đều được đáp ứng.",
        "Dữ liệu được phân thành phần công khai và phần không công khai. Cơ sở đo, "
        "vị trí lấy mẫu, bit mẫu kiểm tra và thông tin xác thực trao đổi thuộc dữ "
        "liệu giao thức có thể công khai theo ngữ cảnh. Chuỗi bit còn lại, khóa "
        "cuối và khóa ứng dụng phải được giữ riêng, không đưa vào biểu đồ hoặc nhật "
        "ký vận hành.",
        "Các bước không tự ý đọc trạng thái bên trong của Eve để quyết định có dừng "
        "hay không. Bộ giám sát dùng thông tin công khai mà Alice và Bob có thể thu "
        "thập, chẳng hạn lỗi mẫu và tỷ lệ ghi nhận tín hiệu. Phần thực nghiệm được "
        "biết cấu hình tấn công để đối chiếu kết quả, nhưng thông tin đó không được "
        "coi như phép phát hiện của giao thức.",
        "Cách tổ chức theo luồng giúp xác định nguyên nhân khi một kịch bản không "
        "tạo được khóa. Ví dụ, thiếu lượt dò cần được phân biệt với việc đủ lượt dò "
        "nhưng QBER cao. Tương tự, sửa sai thành công nhưng độ dài cuối không dương "
        "vẫn phải được ghi là phiên dừng.",
    )

    r.h("2.3 Cấu hình và lựa chọn tham số")
    r.table("parameters", "Các tham số nền của mô phỏng")
    paragraphs(
        r,
        "Bảng trên là cấu hình nền được ghi cùng dữ liệu, không phải toàn bộ thực "
        "nghiệm đều chạy nguyên các giá trị này. Mỗi phép quét thay một hoặc một "
        "nhóm tham số theo mục tiêu riêng. Chẳng hạn, thực nghiệm nghe lén thay tỷ "
        "lệ chặn, còn thực nghiệm khóa hữu hạn thay số xung và giữ mức nhiễu cố "
        "định.",
        "Số xung ảnh hưởng lượng mẫu và thời gian chạy. Tỷ lệ công khai mẫu ảnh "
        "hưởng đồng thời độ chắc chắn của ước lượng và số bit còn lại làm khóa. "
        "Ngưỡng lỗi quá chặt có thể khiến nhiều phiên trung thực dừng; ngưỡng rộng "
        "hơn cũng không bỏ được yêu cầu rút ngắn khóa theo lượng rò và sai số.",
        "Các giá trị suy hao, hiệu suất detector và đếm tối phải được hiểu như giả "
        "định mô hình. Khi đặt hiệu suất lý tưởng và đếm tối bằng không, kết quả "
        "chỉ phản ánh điều kiện đó. Để đánh giá đường truyền sát thực tế hơn cần "
        "thay cấu hình và kiểm tra lại, không dùng kết quả kênh lý tưởng cho mọi "
        "thiết bị.",
        "Bộ nạp cấu hình kiểm tra xác suất nằm trong miền hợp lệ, số lượt và cỡ "
        "khối phù hợp, cùng các lựa chọn backend được hỗ trợ. Nhờ từ chối cấu hình "
        "sai sớm, lỗi nhập liệu không bị hiểu nhầm thành hiện tượng vật lý hoặc kết "
        "quả bất thường của giao thức.",
    )

    r.h("2.4 Thiết kế mô phỏng vật lý và hai backend")
    paragraphs(
        r,
        "Với BB84, chương trình tạo bit và cơ sở của Alice, chọn cơ sở của Bob, áp "
        "dụng kênh cùng hành vi Eve rồi sinh kết quả đo. Thông tin về lượt phát "
        "hiện được giữ để sàng lọc đúng vị trí, tránh so sánh nhầm hai chuỗi đã bị "
        "mất tín hiệu ở những vị trí khác nhau.",
        "Backend nhanh dùng mảng NumPy cho các bit, cơ sở và mặt nạ phát hiện. Các "
        "thao tác trên nhiều tín hiệu được thực hiện theo mảng, giúp quét nhiều mức "
        "nhiễu hoặc nhiều cỡ phiên trong thời gian phù hợp. Không sử dụng vòng lặp "
        "Python riêng cho từng qubit trong đường mô phỏng nhanh.",
        "Backend Qiskit biểu diễn quá trình chuẩn bị, đổi cơ sở và đo bằng mạch rồi "
        "lấy mẫu qua Aer. Do chi phí mạch lớn hơn, các điểm đối chiếu thường có cỡ "
        "mẫu nhỏ hơn phép quét nhanh. Khi so sánh phải nêu cỡ mẫu và khoảng sai số, "
        "không yêu cầu hai backend cho cùng từng bit hoặc cùng thời gian chạy.",
        "Với E91, dữ liệu được nhóm theo cặp thiết lập đo của Alice và Bob. Những "
        "nhóm tạo khóa và những nhóm ước lượng CHSH phải được phân biệt rõ. Cách "
        "gom nhóm và quy ước dấu tương quan được dùng thống nhất giữa phần mô "
        "phỏng, tính chỉ số và vẽ biểu đồ.",
        "Quét khoảng cách dùng mô hình tốc độ để xem ảnh hưởng của suy hao và đếm "
        "tối. Nó không đồng nhất với việc chạy toàn bộ phiên hữu hạn ở từng khoảng "
        "cách. Báo cáo giữ sự phân biệt này khi đọc các đường tốc độ khóa.",
    )

    r.h("2.5 Quy trình xử lý khóa và điều kiện dừng")
    paragraphs(
        r,
        "Sau sàng lọc, hệ thống chọn mẫu công khai không hoàn lại và tính QBER cùng "
        "các khoảng thống kê. Các bit mẫu bị loại khỏi cả hai chuỗi trước sửa sai. "
        "Điều này tránh việc vô tình dùng lại dữ liệu đã công khai làm vật liệu "
        "khóa.",
        "Chế độ Cascade ghi lại thông tin công bố trong quá trình sửa sai để tính "
        "lượng rò. Chế độ lý tưởng giúp tách ảnh hưởng của mô hình kênh và cỡ mẫu, "
        "nhưng không đo đúng chi phí trao đổi của Cascade. Mỗi thực nghiệm phải ghi "
        "rõ đang dùng chế độ nào.",
        "Sau sửa sai, hai bên xác minh chuỗi trước khi rút ngắn. Khi xác minh không "
        "đạt, chương trình dừng thay vì cố tạo khóa từ hai đầu vào khác nhau. Khi "
        "xác minh đạt, độ dài đầu ra vẫn phải được tính từ QBER dự phòng và lượng "
        "rò.",
    )
    r.table("decisions", "Các điều kiện dừng và ý nghĩa của chúng")
    paragraphs(
        r,
        "Bảng điều kiện dừng giúp đọc kết quả đúng nguyên nhân. Không đủ mẫu nghĩa "
        "là chưa có đủ bằng chứng để ước lượng, còn QBER vượt ngưỡng nghĩa là dữ "
        "liệu hiện tại không đáp ứng chính sách. Cả hai đều khác với một kết luận "
        "chắc chắn rằng Eve đã nghe lén.",
        "Trong thống kê lượng khóa, phiên dừng đóng góp số bit cuối bằng không. Nếu "
        "chỉ lấy trung bình trên các phiên thành công, kết quả có thể tạo cảm giác "
        "hệ thống hiệu quả hơn khi kênh nhiễu cao. Do đó, báo cáo xét lượng khóa "
        "cùng tỷ lệ dừng.",
    )

    r.h("2.6 Giám sát phiên và phản ứng khi có bất thường")
    paragraphs(
        r,
        "Giám sát không chỉ là in QBER ở cuối phiên. Bộ giám sát nhận dữ liệu công "
        "khai, đánh giá mức lỗi hoặc tỷ lệ dò và trả quyết định. Lớp quản lý phiên "
        "sử dụng quyết định đó để cho phép dùng khóa, tạo khóa lại hoặc dừng.",
        "Kiểm tra ngưỡng dựa trên cận QBER; CI xét độ phù hợp của lỗi mẫu với mức "
        "nền. SPRT cộng dồn bằng chứng và có thể ra quyết định sớm. CUSUM tiếp tục "
        "theo dõi mức thay đổi nên phù hợp để khảo sát trường hợp Eve can thiệp "
        "muộn.",
    )
    r.equation(
        "Lₙ = Σᵢ ln[P(xᵢ|e₁)/P(xᵢ|e₀)]",
        "xᵢ là dấu hiệu lỗi của mẫu thứ i; e₀ là mức lỗi nền; "
        "e₁ là mức lỗi giả thuyết khi có bất thường. Lₙ là "
        "bằng chứng tích lũy trong SPRT, không phải lượng "
        "thông tin Eve biết về khóa.",
    )
    r.equation(
        "A = ln[(1 − β)/α],     B = ln[β/(1 − α)]",
        "α và β ở đây là mức sai số mục tiêu của phép "
        "kiểm tra, không phải biên độ qubit. Lₙ vượt A "
        "thì báo động, xuống dưới B thì chấp nhận giả "
        "thuyết nền cho lần kiểm tra; nếu chưa vượt "
        "biên thì chưa kết luận.",
    )
    paragraphs(
        r,
        "Một quyết định sớm chỉ có ý nghĩa trong phạm vi dữ liệu mà phép kiểm tra "
        "đã xem. Nếu SPRT kết thúc trên đoạn đầu bình thường, sự thay đổi ở đoạn "
        "sau cần một cơ chế theo dõi tiếp. Thực nghiệm chặn muộn được dùng để làm "
        "rõ giới hạn này.",
        "Trạng thái phiên cũng ngăn ứng dụng dùng nhầm khóa khi chưa sẵn sàng. Khi "
        "một phiên bị dừng, lý do và số liệu được giữ để đối chiếu. Chính sách thử "
        "lại hoặc tạm khóa hệ thống không làm thay đổi kết quả của phiên đã thất "
        "bại.",
    )

    r.h("2.7 Xác thực và quản lý vật liệu khóa")
    paragraphs(
        r,
        "Thông điệp cổ điển được gắn với mã phiên, hướng truyền, loại thông điệp và "
        "số thứ tự trước khi tính HMAC. Bên nhận kiểm tra ngữ cảnh cùng thẻ xác "
        "thực để tránh dùng lại một thông điệp hợp lệ ở sai phiên hoặc sai vị trí.",
        "Khóa xác thực ban đầu là điểm tin cậy được giả định. QKD trong đồ án không "
        "tự xác định danh tính của một đối tác hoàn toàn chưa biết. Nếu khóa HMAC "
        "bị lộ hoặc phân phối sai, kết quả kiểm tra QBER không đủ bù lại vấn đề đó.",
        "Khóa ứng dụng được dẫn xuất theo nhãn mục đích sử dụng, thay vì dùng "
        "nguyên một khóa cho mọi công việc. HKDF giúp tách các cách dùng trong "
        "thiết kế, nhưng không bổ sung bí mật nếu khóa gốc đã dự đoán được.",
        "Bộ quản lý khóa theo dõi tuổi khóa, lượng dữ liệu và số thông điệp đã dùng "
        "theo chính sách. Ứng dụng có thể yêu cầu tạo khóa mới khi chạm giới hạn. "
        "Nhật ký chỉ giữ mã khóa, độ dài và dấu nhận dạng ngắn, không in toàn bộ "
        "khóa.",
    )

    r.h("2.8 Demo truyền tin và định dạng tệp")
    paragraphs(
        r,
        "Demo truyền tin thiết lập hai đầu kết nối TCP nội bộ để chuyển thông điệp "
        "cổ điển và dữ liệu ứng dụng. Khi khóa chưa được chấp nhận, việc gửi bị từ "
        "chối. Khi bật Eve, người chạy có thể quan sát cách mức lỗi làm thay đổi "
        "quyết định cấp khóa.",
        "Demo tệp dùng định dạng QKDH để lưu thông tin cần cho giải mã và kiểm tra. "
        "Phần đầu ghi nhận phiên, thuật toán và các tham số đóng gói. Dữ liệu được "
        "chia khối để xử lý tệp lớn mà không cần giữ toàn bộ bản rõ trong bộ nhớ.",
        "Mỗi khối được ràng buộc với thông tin đầu tệp, vị trí khối và dấu hiệu "
        "khối cuối. Cách này giúp phát hiện không chỉ việc sửa byte bản mã mà còn "
        "việc cắt thiếu hoặc đảo vị trí khối. Nếu kiểm tra không đạt, chương trình "
        "không công bố tệp khôi phục như một kết quả hợp lệ.",
        "Khóa lưu cục bộ trong demo chỉ phục vụ việc chạy lệnh giải mã ở tiến trình "
        "khác. Tệp chứa vật liệu khóa phải giữ riêng với bản mã. Cách lưu này chưa "
        "phải giải pháp quản lý khóa cho một dịch vụ thật.",
    )

    r.h("2.9 Tái lập thí nghiệm và tách nguồn ngẫu nhiên")
    paragraphs(
        r,
        "Một giá trị khởi tạo ngẫu nhiên, gọi là seed, giúp chạy lại phần mô phỏng "
        "với cùng thiết lập. Các lượt được định danh theo thực nghiệm và chỉ số lặp "
        "để dễ đối chiếu những điều kiện cùng kịch bản. Toàn bộ ngẫu nhiên vật lý "
        "giả lập đi qua bộ sinh được quản lý từ cấu hình.",
        "Ngẫu nhiên của lớp mật mã được lấy riêng từ hệ điều hành. Nó dùng cho các "
        "giá trị như phần ngẫu nhiên của nonce, mã phiên và seed băm riêng tư. Việc "
        "tách hai nguồn ngăn seed mô phỏng vô tình điều khiển những giá trị cần khó "
        "đoán ở lớp mật mã.",
        "Dù tách nguồn đúng, khóa cuối vẫn bắt nguồn từ dữ liệu mô phỏng có seed. "
        "Vì vậy, không dùng khóa này để bảo vệ dữ liệu thật. Khả năng tái lập thí "
        "nghiệm và tính bí mật của khóa là hai yêu cầu khác nhau cần được giải "
        "thích rõ khi trình bày kết quả.",
        "Mỗi kết quả được lưu cùng cấu hình, seed, commit và phiên bản thư viện. "
        "CSV chứa số đo; JSON lưu ngữ cảnh; biểu đồ đọc lại các dữ liệu đó. Script "
        "báo cáo không tự điền một số liệu kỳ vọng khi thiếu kết quả thực nghiệm.",
    )

    r.h("2.10 Chiến lược kiểm thử và tổ chức đánh giá")
    paragraphs(
        r,
        "Kiểm thử đơn vị đối chiếu các hàm với trường hợp có thể tính trước bằng lý "
        "thuyết. Kiểm thử thống kê dùng seed cố định và dung sai dựa trên cỡ mẫu. "
        "Một giá trị ngẫu nhiên lệch nhẹ khỏi trung bình lý thuyết không tự động là "
        "lỗi chương trình.",
        "Kiểm thử tích hợp theo dõi cả phiên tạo khóa hoặc chu trình mã hóa và giải "
        "mã. Các ca âm tính đưa vào khóa sai, ngữ cảnh sai, thẻ bị sửa hoặc tệp bị "
        "cắt để kiểm tra rằng hệ thống từ chối đúng cách. Kết quả từ chối quan "
        "trọng như kết quả khôi phục đúng.",
        "Các thực nghiệm ở chương sau được sắp theo câu hỏi đánh giá: mô hình có "
        "phản ánh dấu vết nghe lén không, đủ dữ liệu để cấp khóa không và ứng dụng "
        "có xử lý đúng dữ liệu hợp lệ hoặc dữ liệu bị sửa không. Việc chia nhóm này "
        "giúp tránh trộn tốc độ xử lý với tính an toàn.",
    )
    r.table("scenarios", "Các kịch bản và số lượt lặp trong bộ kết quả")
    paragraphs(
        r,
        "Số lượt lặp trong bảng là số đã chạy ở chế độ nhanh, không phải số lượt dự "
        "kiến của cấu hình đầy đủ. Các kết quả gần ngưỡng cần xem cùng khoảng sai "
        "số. Khi cần đánh giá các sự cố hiếm, phải tăng số mẫu và thiết kế phép thử "
        "riêng, không suy rộng từ một bộ chạy nhanh.",
    )
