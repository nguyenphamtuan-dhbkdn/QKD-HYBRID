# Cơ sở lý thuyết

## Qubit và phép đo

Qubit thuần có dạng $|\psi\rangle=\alpha|0\rangle+\beta|1\rangle$ với $|\alpha|^2+|\beta|^2=1$. Đo theo Z cho bit 1 với xác suất $|\beta|^2$. Cơ sở X gồm $|\pm\rangle=(|0\rangle\pm|1\rangle)/\sqrt2$. Vì $|\langle0|+\rangle|^2=1/2$, đo trạng thái thuộc cơ sở này bằng cơ sở kia cho hai bit đồng xác suất. Backend nhanh lấy mẫu xác suất đo trong `physics/states.py`. Backend Aer áp dụng Hadamard để đổi giữa Z và X. `qrng.py` chuẩn bị $H|0\rangle$ rồi đo Z bằng bộ mô phỏng.

## Định lý không nhân bản

Giả sử cùng một phép unita $U$ sao chép được hai trạng thái $|a\rangle$, $|b\rangle$ lên thanh ghi trắng. Bảo toàn tích vô hướng buộc $\langle a|b\rangle=(\langle a|b\rangle)^2$. Hai trạng thái phân biệt, không trực giao vi phạm điều kiện này. Eve trong `attacks/intercept_resend.py` đo rồi chuẩn bị lại theo kết quả đo. Lựa chọn sai cơ sở tạo nhiễu quan sát được. [Wootters và Zurek](https://www.nature.com/articles/299802a0)

## BB84 và QBER

Alice gửi từng bit theo cơ sở ngẫu nhiên. Bob chọn cơ sở đo độc lập. Sau khi công bố cơ sở qua kênh cổ điển xác thực, họ giữ các bit phát hiện cùng cơ sở. Nếu xác suất chọn Z là $p_Z$, phần giữ kỳ vọng trên lượt phát hiện là $p_Z^2+(1-p_Z)^2$. Eve chặn ngẫu nhiên tỷ lệ $p$ trong trường hợp cơ sở đồng xác suất làm tăng QBER thêm $p/4$ khi kênh lý tưởng. Hai cơ chế lật bit độc lập cho $Q=e_{ch}+p/4-2e_{ch}(p/4)$. Tham khảo `protocols/bb84.py`, `postprocess/sifting.py` và `analysis/theory.py`. [Bennett và Brassard](https://arxiv.org/abs/2003.06557)

Trong E3, kênh lý tưởng và Eve chặn toàn phần cho xác suất phát hiện ít nhất một sai khác bằng $1-(3/4)^k$. Trên kênh có nhiễu, một bit sai cũng có thể xuất hiện trong phiên trung thực. E13 ước lượng cả xác suất báo động nhầm và độ trễ trên các vết lỗi mô phỏng.

Với $x$ lỗi trên $k$ bit công khai, $\hat Q=x/k$ và
$Q_{ub}=\min(1,\hat Q+\sqrt{\ln(1/\epsilon_{PE})/(2k)})$. `postprocess/estimation.py` loại các bit mẫu và dừng nếu $Q_{ub}>Q_{max}$. Hoeffding là cận giản lược trong dự án. Phân tích chặt hơn phải theo dõi lấy mẫu không hoàn lại và ngân sách an toàn. [Tomamichel và cộng sự](https://arxiv.org/abs/1103.4130)

## E91 và CHSH

Mô phỏng dùng $|\Phi^+\rangle=(|00\rangle+|11\rangle)/\sqrt2$. Ekert dùng trạng thái singlet trong bài gốc. Theo quy ước góc Bloch trong `protocols/e91.py`, với độ hiển thị Werner $V$, tương quan là $E(a,b)=V\cos(a-b)$. Hai cặp thiết lập cùng góc tạo khóa. Bốn cặp khác dùng $S=E_{00}-E_{02}+E_{20}+E_{22}=2\sqrt2V$ trong mô hình lý tưởng. Trên mẫu, $\hat E=1-2x/n$ và $\sigma_S^2=\sum_{ab}(1-\hat E_{ab}^{2})/(n_{ab}-1)$. `analysis/chsh.py` tính $S$ và độ không chắc chắn. Phiên dừng khi $S-z\sigma_S\le 2$ hoặc mẫu chưa đủ. [Ekert](https://journals.aps.org/prl/abstract/10.1103/PhysRevLett.67.661) · [Clauser và cộng sự](https://journals.aps.org/prl/abstract/10.1103/PhysRevLett.23.880)

## Suy hao và tốc độ khóa

`physics/channel.py` dùng độ truyền qua của sợi $\eta_{ch}=10^{-\alpha L/10}$ với $\alpha$ tính bằng dB/km. Khi bỏ qua đếm tối, hiệu suất của một nhánh đơn photon là $\eta_d\eta_{ch}$ và xác suất trùng phùng E91 là tích hiệu suất hai nhánh. E5 đối chiếu tốc độ hữu hạn với phần khóa tiệm cận $\max\{0,1-(1+f_{EC})h_2(Q)\}$ trên bit giữ cho khóa. E6 nhân phần khóa với xác suất dò và sàng lọc, đồng thời dùng cận trạng thái mồi cho nguồn kết hợp yếu. [Ma và cộng sự](https://arxiv.org/abs/quant-ph/0503005)

## Giám sát công khai

SPRT cộng $\log(e_1/e_0)$ khi lỗi và $\log[(1-e_1)/(1-e_0)]$ khi khớp. Hai biên Wald là $\log[(1-\beta)/\alpha]$ và $\log[\beta/(1-\alpha)]$. CUSUM cập nhật $C_i=\max(0,C_{i-1}+\log LR_i)$ theo cửa sổ. Kiểm định chung chia ngân sách sai lầm giữa QBER và tỷ lệ dò. Các phép thử trong `monitor/detectors.py` chỉ dùng dữ liệu công khai và đường nền hiệu chuẩn.

## Cascade và xác minh

`postprocess/cascade.py` hoán vị bit qua các lượt. Kích thước khối ban đầu là $k_1=\max(2,\lceil0.73/\hat Q\rceil)$ với mặc định nội bộ khi $\hat Q=0$. Khối có chẵn lẻ khác nhau được chia đôi để tìm bit sai. Sửa một bit có thể làm thay đổi chẵn lẻ ở lượt trước. Hiệu suất công bố là $f_{EC}=\mathrm{leak}_{EC}/[n\,h_2(\hat Q)]$ khi mẫu số dương. Bước xác minh trong `postprocess/verification.py` dùng đánh giá đa thức tại một điểm ngẫu nhiên của trường $\mathrm{GF}(2^{61}-1)$. Đa thức khác không bậc $d$ có tối đa $d$ nghiệm. [Brassard và Salvail](https://link.springer.com/chapter/10.1007/3-540-48285-7_35)

## Khuếch đại riêng tư và độ dài hữu hạn

Toeplitz cho $K=Tx\bmod2$. Ma trận $\ell\times n$ được mô tả bằng $n+\ell-1$ bit seed và tính bằng tích chập FFT trong `postprocess/privacy_amp.py`. `postprocess/keylength.py` dùng
$\ell=\lfloor n[1-h_2(Q_{ub})]-\mathrm{leak}_{EC}-\mathrm{leak}_{verify}-2\log_2(1/\epsilon_{PA})\rfloor$ với entropy nhị phân $h_2(q)=-q\log_2 q-(1-q)\log_2(1-q)$ và giá trị bất lợi nhất khi $Q_{ub}\ge1/2$. Phiên dừng nếu $\ell\le0$. Chứng minh an toàn đầy đủ phụ thuộc giả thiết nguồn phát, mẫu hữu hạn và mô hình tấn công. [Shor và Preskill](https://arxiv.org/abs/quant-ph/0003004) · [Tomamichel và cộng sự](https://arxiv.org/abs/1103.4130)

## Xác thực, HKDF và AEAD

`auth/channel.py` kiểm tra HMAC của khung gồm mã phiên, chiều truyền, số thứ tự, loại và nội dung. Khóa xác thực ban đầu được chia sẻ trước. Phiên thành công dành một phần khóa cuối để làm mới HMAC. `crypto/kdf.py` dùng $\mathrm{HKDF\text{-}Extract}(salt,IKM)=\mathrm{HMAC}(salt,IKM)$ và các nhãn Expand riêng theo mục đích. [RFC 5869](https://www.rfc-editor.org/rfc/rfc5869)

AEAD nhận khóa $K$, nonce $N$, bản rõ $M$ và dữ liệu liên kết $A$, rồi trả $(C,T)=\mathrm{Seal}_K(N,A,M)$. `crypto/container.py` xác thực header, chỉ số khối và cờ cuối ở mỗi lần mở. `crypto/aead.py` ghép tiền tố ngẫu nhiên với bộ đếm tăng dần. Khi cố ý lặp cùng $(K,N)$ trong E11, hai bản mã dùng cùng dòng khóa và cho $C_1\oplus C_2=M_1\oplus M_2$. [NIST SP 800-38D](https://csrc.nist.gov/pubs/sp/800/38/d/final) · [RFC 8439](https://www.rfc-editor.org/rfc/rfc8439)

## Grover và Shor

Với không gian $2^k$ khóa có entropy $k$ bit, Grover cần $O(2^{k/2})$ truy vấn oracle. Chi phí cổng mỗi truy vấn, độ sâu tuần tự và sửa lỗi lượng tử ảnh hưởng chi phí thực tế. Chia không gian đều cho $P$ bộ xử lý cho độ sâu truy vấn theo $O(\sqrt{2^k/P})$ trong mô hình lý tưởng. Shor giải phân tích thừa số và logarit rời rạc trong thời gian đa thức trên máy lượng tử phù hợp. `analysis/quantum_security.py` tách số mũ tìm khóa đối xứng khỏi mô hình đa thức cho RSA và ECC. [Grover](https://arxiv.org/abs/quant-ph/9605043) · [Shor](https://klein.mit.edu/~shor/papers/algsfqc-dlf.pdf) · [Grassl và cộng sự](https://arxiv.org/abs/1512.04965)
