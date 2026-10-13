"""Tests for the Aadhaar validator.

The valid numbers here are constructed, not real Aadhaar numbers. The
prefix 23456789012 has Verhoeff check digit 4, giving 234567890124.
"""

from vaultscan.validators.aadhaar import (
    find_aadhaar_candidates,
    is_valid_aadhaar,
)


class TestIsValidAadhaar:
    def test_valid_check_digit(self):
        assert is_valid_aadhaar("234567890124") is True

    def test_valid_all_nines(self):
        # 999999999999 happens to be Verhoeff-valid; useful edge case.
        assert is_valid_aadhaar("999999999999") is True

    def test_invalid_check_digit(self):
        assert is_valid_aadhaar("234567890123") is False

    def test_rejects_leading_zero(self):
        assert is_valid_aadhaar("034567890124") is False

    def test_rejects_leading_one(self):
        assert is_valid_aadhaar("134567890124") is False

    def test_rejects_too_short(self):
        assert is_valid_aadhaar("23456789012") is False

    def test_rejects_too_long(self):
        assert is_valid_aadhaar("2345678901234") is False

    def test_rejects_non_digits(self):
        assert is_valid_aadhaar("23456789012a") is False

    def test_rejects_empty(self):
        assert is_valid_aadhaar("") is False

    def test_rejects_non_string(self):
        assert is_valid_aadhaar(234567890124) is False  # type: ignore[arg-type]
        assert is_valid_aadhaar(None) is False  # type: ignore[arg-type]

    def test_accepts_spaces_and_hyphens(self):
        assert is_valid_aadhaar("2345 6789 0124") is True
        assert is_valid_aadhaar("2345-6789-0124") is True


class TestFindCandidates:
    def test_finds_plain_aadhaar(self):
        text = "My number is 234567890124, please call."
        matches = find_aadhaar_candidates(text)
        assert len(matches) == 1
        start, end, val = matches[0]
        assert val == "234567890124"
        assert text[start:end] == "234567890124"

    def test_finds_multiple(self):
        text = "A: 234567890124 B: 234567890123"
        assert len(find_aadhaar_candidates(text)) == 2

    def test_does_not_match_inside_longer_number(self):
        text = "Order 1234567890123456 confirmed"
        assert find_aadhaar_candidates(text) == []

    def test_does_not_match_leading_zero_or_one(self):
        assert find_aadhaar_candidates("012345678901") == []
        assert find_aadhaar_candidates("112345678901") == []

    def test_empty_text(self):
        assert find_aadhaar_candidates("") == []

    def test_rejects_non_string(self):
        assert find_aadhaar_candidates(None) == []  # type: ignore[arg-type]


class TestAadhaarScan:
    def test_valid_aadhaar_is_full_confidence(self):
        from vaultscan.validators import aadhaar

        [f] = aadhaar.scan("ID: 234567890124")
        assert f.category == "aadhaar"
        assert f.validator == "aadhaar.verhoeff"
        assert f.source == "validator"
        assert f.confidence == 1.0
        assert f.notes is None

    def test_checksum_failure_is_low_confidence(self):
        from vaultscan.validators import aadhaar

        [f] = aadhaar.scan("ID: 234567890123")
        assert f.confidence == 0.3
        assert f.notes is not None and "near-miss" in f.notes
