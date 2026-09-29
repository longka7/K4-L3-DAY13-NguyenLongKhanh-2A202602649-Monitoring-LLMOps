from app.pii import scrub_text


def test_scrub_email() -> None:
    out = scrub_text("Email me at student@vinuni.edu.vn")
    assert "student@" not in out
    assert "REDACTED_EMAIL" in out


def test_scrub_common_vietnamese_phone_formats() -> None:
    phone_numbers = (
        "0901234567",
        "090 123 4567",
        "090.123.4567",
        "090-123-4567",
        "+84 90 123 4567",
    )

    for phone_number in phone_numbers:
        out = scrub_text(f"Contact: {phone_number}")
        assert phone_number not in out
        assert "REDACTED_PHONE_VN" in out


def test_scrub_cccd_12_digits() -> None:
    out = scrub_text("CCCD 079204001234 da xac minh")
    assert "079204001234" not in out
    assert "REDACTED_CCCD" in out


def test_scrub_credit_card_formats_fully() -> None:
    for card in ("4111111111111111", "4111 1111 1111 1111", "4111-1111-1111-1111"):
        out = scrub_text(f"Card: {card}")
        assert "REDACTED_CREDIT_CARD" in out
        # Không được để sót 4 số cuối vì pattern ngắn hơn chạy trước
        assert "1111" not in out


def test_scrub_passport_vn() -> None:
    out = scrub_text("Passport B1234567 het han 2030")
    assert "B1234567" not in out
    assert "REDACTED_PASSPORT_VN" in out


def test_khong_che_nham_du_lieu_binh_thuong() -> None:
    text = "req-1a2b3c4d latency 1234ms cost 0.000123 order 2026 total 500000"
    assert scrub_text(text) == text


def test_khong_che_nham_id_hex() -> None:
    # Lỗi thật gặp ở CP3: 12 chữ số giữa trace_id hex bị che thành [REDACTED_CCCD]
    for hex_id in ("8968fc9b123456789012c176ae223299", "req-0901234567ab", "a4111111111111111b"):
        assert scrub_text(hex_id) == hex_id
