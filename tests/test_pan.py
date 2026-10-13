"""Tests for the PAN validator.

PAN has no public checksum, so these tests cover format + holder code only.
"""

from vaultscan.validators.pan import (
    find_pan_candidates,
    is_valid_pan,
    scan,
)


class TestIsValidPan:
    def test_valid_individual(self):
        assert is_valid_pan("ABCPD1234E") is True

    def test_valid_company(self):
        assert is_valid_pan("ABCCD1234F") is True

    def test_rejects_unknown_holder_code(self):
        # 'Z' is not a valid holder type.
        assert is_valid_pan("ABCZD1234E") is False

    def test_rejects_lowercase(self):
        assert is_valid_pan("abcpd1234e") is False

    def test_rejects_wrong_length(self):
        assert is_valid_pan("ABCPD123E") is False
        assert is_valid_pan("ABCPD12345E") is False

    def test_rejects_wrong_shape(self):
        assert is_valid_pan("ABCD12345E") is False
        assert is_valid_pan("ABCDE1234") is False

    def test_rejects_non_string(self):
        assert is_valid_pan(None) is False  # type: ignore[arg-type]
        assert is_valid_pan(1234567890) is False  # type: ignore[arg-type]

    def test_rejects_empty(self):
        assert is_valid_pan("") is False


class TestFindPanCandidates:
    def test_finds_pan(self):
        text = "Client PAN is ABCPD1234E on file."
        matches = find_pan_candidates(text)
        assert len(matches) == 1
        start, end, value = matches[0]
        assert value == "ABCPD1234E"
        assert text[start:end] == "ABCPD1234E"

    def test_does_not_match_inside_word(self):
        assert find_pan_candidates("xABCPD1234Ey") == []

    def test_empty(self):
        assert find_pan_candidates("") == []

    def test_non_string(self):
        assert find_pan_candidates(None) == []  # type: ignore[arg-type]


class TestPanScan:
    def test_valid_pan_confidence(self):
        [f] = scan("PAN: ABCPD1234E")
        assert f.category == "pan"
        assert f.validator == "pan.format"
        assert f.source == "validator"
        assert f.confidence == 0.7
        assert f.notes is not None and "no public checksum" in f.notes

    def test_unknown_holder_code_is_low_confidence(self):
        [f] = scan("PAN: ABCZD1234E")
        assert f.confidence == 0.3
        assert f.notes is not None and "unknown holder code" in f.notes
