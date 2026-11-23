import pytest

from app.services.phone import (
    InvalidPhoneError, format_display, mask_phone, normalize_phone, phones_match,
    read_back, read_back_words, spoken_to_digits,
)


@pytest.mark.parametrize("raw,canonical", [
    ("98765 43210", "9876543210"),
    ("+91 98765-43210", "+919876543210"),
    ("(987) 654-3210", "9876543210"),
    ("nine eight seven six five four three two one zero", "9876543210"),
    ("plus nine one 98765 43210", "+919876543210"),
    ("98765 double four 3210", "98765443210"),
    ("nine eight seven six five oh oh one two three", "9876500123"),
    ("triple nine 8765 4321", "99987654321"),
])
def test_valid_numbers(raw, canonical):
    assert normalize_phone(raw).canonical == canonical


@pytest.mark.parametrize("raw", ["", "   ", "12345", "98765", "1234567890123456", "0000000000", "abc"])
def test_invalid_numbers(raw):
    with pytest.raises(InvalidPhoneError):
        normalize_phone(raw)


def test_length_bounds():
    assert normalize_phone("1234567890").digits == "1234567890"      # 10 ok
    assert normalize_phone("+123456789012345").digits == "123456789012345"  # 15 ok
    with pytest.raises(InvalidPhoneError):
        normalize_phone("123456789")      # 9
    with pytest.raises(InvalidPhoneError):
        normalize_phone("1234567890123456")  # 16


def test_country_code_preserved_and_matching():
    assert phones_match("+919876543210", "9876543210")        # one side has no country code
    assert phones_match("+919876543210", "919876543210")
    assert not phones_match("+919876543210", "+449876543210")  # both explicit, differ
    assert not phones_match("9876543210", "9876543211")


def test_read_back_formats():
    assert read_back("9876543210") == "9 8 7 6 5, 4 3 2 1 0"
    assert read_back("+919876543210") == "plus 9 1, 9 8 7 6 5, 4 3 2 1 0"
    assert read_back_words("9876543210").startswith("nine eight seven six five, four")
    assert format_display("+919876543210") == "+91 98765 43210"


def test_mask_hides_all_but_last_three():
    masked = mask_phone("+919876543210")
    assert masked.endswith("210") and "98765" not in masked and "•" in masked


def test_spoken_to_digits_ignores_noise():
    assert spoken_to_digits("my number is 98765 43210 thanks") == "9876543210"
