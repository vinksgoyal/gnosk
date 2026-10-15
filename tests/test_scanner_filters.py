"""Tests for the hex-run context filter in the scanner.

The filter exists because SHA256 hashes, package lock files, and git
metadata produce endless false positives: a 64-char hex string contains
many 10-digit windows that match the phone regex but are not phone
numbers.
"""

from __future__ import annotations

from pathlib import Path

from gnosk.scanner import _is_inside_hex_run, scan_file


class TestIsInsideHexRun:
    def test_short_digit_run_not_filtered(self):
        text = "phone: 8227518893"
        assert _is_inside_hex_run(text, 7, 17) is False

    def test_inside_long_hex_run_filtered(self):
        # 64-char SHA256 with a 10-digit window inside.
        h = "7550498ba996064feca12005ff4133eb1d35741c4061376e7a987d8227518893"
        text = f"sha256: {h}"
        # locate 8227518893 in text
        start = text.index("8227518893")
        assert _is_inside_hex_run(text, start, start + 10) is True

    def test_exactly_32_hex_chars_filtered(self):
        # Boundary: 32 chars is the minimum to be considered structural.
        text = "a" + "0" * 31  # length 32, all hex
        assert _is_inside_hex_run(text, 1, 11) is True

    def test_31_hex_chars_not_filtered(self):
        text = "a" + "0" * 30  # length 31
        assert _is_inside_hex_run(text, 1, 11) is False

    def test_hex_run_broken_by_non_hex(self):
        # A 10-digit phone sitting between two hex-ish runs separated
        # by a dash is still a candidate.
        text = "abc-8227518893-def"
        start = text.index("8227518893")
        assert _is_inside_hex_run(text, start, start + 10) is False

    def test_uppercase_hex_also_counts(self):
        text = "ABCDEF0123456789ABCDEF0123456789ABCDEF0123456789"
        assert _is_inside_hex_run(text, 10, 20) is True


class TestScanFileSuppressesHexFindings:
    def test_sha256sums_line_is_clean(self, tmp_path: Path):
        p = tmp_path / "SHA256SUMS"
        p.write_text(
            "7550498ba996064feca12005ff4133eb1d35741c4061376e7a987d8227518893"
            "  BirdNET_v2.4_int8_arm_dfttrunc.onnx\n"
        )
        assert scan_file(p).count == 0

    def test_json_sha256_field_is_clean(self, tmp_path: Path):
        p = tmp_path / "models.json"
        p.write_text(
            '{"sha256": "7550498ba996064feca12005ff4133eb1d35741c4061376e7a987d8227518893"}\n'
        )
        assert scan_file(p).count == 0

    def test_real_phone_still_found(self, tmp_path: Path):
        p = tmp_path / "contact.txt"
        p.write_text("Call me on 8227518893 anytime.\n")
        findings = scan_file(p).findings
        assert any(f.category == "phone_in" for f in findings)

    def test_real_email_inside_non_hex_line_still_found(self, tmp_path: Path):
        p = tmp_path / "conf.py"
        p.write_text('EMAIL = "real@client.com"  # ref 7550498ba996064feca12005ff4133eb\n')
        findings = scan_file(p).findings
        assert any(f.category == "email" for f in findings)

    def test_hash_and_email_on_same_line_email_survives(self, tmp_path: Path):
        p = tmp_path / "mixed.txt"
        p.write_text(
            "user real@client.com hash "
            "7550498ba996064feca12005ff4133eb1d35741c4061376e7a987d8227518893\n"
        )
        findings = scan_file(p).findings
        assert any(f.category == "email" for f in findings)
        # The phone-shaped fragment inside the hash is gone.
        assert not any(f.category == "phone_in" for f in findings)


class TestNonHexSpansNotFiltered:
    """A match that contains non-hex characters is never a hex-run fragment."""

    def test_github_pat_with_hex_chars_around_it(self, tmp_path: Path):
        # ghp_ prefixed token: the 'g', 'h', 'p', '_' are non-hex, so the
        # span cannot be a hex-run fragment even if the A's inside it are.
        p = tmp_path / "cfg.py"
        token = "ghp_" + "A" * 36
        p.write_text(f'TOKEN = "{token}"\n')
        findings = scan_file(p).findings
        assert any(f.category == "api_key" for f in findings)

    def test_email_next_to_hex_still_found(self, tmp_path: Path):
        p = tmp_path / "x.txt"
        h = "7550498ba996064feca12005ff4133eb1d35741c4061376e7a987d8227518893"
        p.write_text(f"{h} real@client.com\n")
        findings = scan_file(p).findings
        assert any(f.category == "email" for f in findings)
