"""Tests for email, Indian phone, and API-key validators.

Sample API keys here are constructed to match each provider's documented
shape. None of them are real, and none will authenticate anywhere.
"""

from gnosk.validators import email, phone, secrets


class TestEmail:
    def test_finds_simple_email(self):
        [f] = email.scan("Contact: alice@example.com please")
        assert f.category == "email"
        assert f.value == "alice@example.com"
        assert f.confidence == 0.9
        assert f.validator == "email.shape"

    def test_finds_multiple(self):
        got = email.scan("a@x.com and b@y.co.in")
        assert [f.value for f in got] == ["a@x.com", "b@y.co.in"]

    def test_rejects_no_at_sign(self):
        assert email.scan("not-an-email at example.com") == []

    def test_rejects_no_tld(self):
        assert email.scan("user@localhost") == []

    def test_rejects_non_string(self):
        assert email.scan(None) == []  # type: ignore[arg-type]

    def test_offsets_are_correct(self):
        text = "Email: alice@example.com end"
        [f] = email.scan(text)
        assert text[f.start:f.end] == f.value


class TestIndianPhone:
    def test_plain_ten_digits(self):
        [f] = phone.scan("Call 9876543210 now")
        assert f.category == "phone_in"
        assert f.value == "9876543210"
        assert f.confidence == 0.6

    def test_with_country_code(self):
        got = phone.scan("Ph: +91 9876543210")
        assert len(got) == 1
        assert "9876543210" in got[0].value

    def test_with_country_code_no_space(self):
        got = phone.scan("Ph: +919876543210")
        assert len(got) == 1

    def test_with_trunk_zero(self):
        got = phone.scan("Ph: 09876543210")
        assert len(got) == 1

    def test_with_spaces(self):
        got = phone.scan("Ph: 98765 43210")
        assert len(got) == 1

    def test_rejects_starting_with_5(self):
        assert phone.scan("ID 5876543210") == []

    def test_rejects_inside_longer_number(self):
        assert phone.scan("Order 1234567890123") == []

    def test_rejects_non_string(self):
        assert phone.scan(None) == []  # type: ignore[arg-type]


class TestSecrets:
    def test_aws_access_key(self):
        [f] = secrets.scan("AWS_KEY=AKIAIOSFODNN7EXAMPLE")
        assert f.category == "api_key"
        assert f.validator == "secrets.aws_access_key"
        assert f.confidence == 0.95

    def test_github_pat(self):
        token = "ghp_" + "A" * 36
        [f] = secrets.scan(f"token: {token}")
        assert f.validator == "secrets.github_pat"

    def test_openai_key(self):
        token = "sk-" + "a" * 48
        [f] = secrets.scan(f"OPENAI_API_KEY={token}")
        assert f.validator == "secrets.openai_api_key"

    def test_stripe_secret(self):
        token = "sk_live_" + "A" * 24
        [f] = secrets.scan(f"stripe: {token}")
        assert f.validator == "secrets.stripe_secret"

    def test_slack_token(self):
        token = "xoxb-1234567890-abcdefghij"
        [f] = secrets.scan(f"SLACK={token}")
        assert f.validator == "secrets.slack_token"

    def test_multiple_in_one_text(self):
        aws = "AKIAIOSFODNN7EXAMPLE"
        gh = "ghp_" + "B" * 36
        got = secrets.scan(f"{aws} and {gh}")
        kinds = {f.validator for f in got}
        assert kinds == {"secrets.aws_access_key", "secrets.github_pat"}

    def test_rejects_random_uppercase(self):
        # A git SHA-like string should not match.
        assert secrets.scan("commit 5f2e9b1a7c3d4e5f60718293a4b5c6d7e8f90a1b") == []

    def test_rejects_non_string(self):
        assert secrets.scan(None) == []  # type: ignore[arg-type]


class TestPhoneEntropyFilter:
    """Low-entropy 10-digit runs (5+ zeros) are not reported as phones."""

    def test_fractional_price_fragment_rejected(self):
        # The kind of value produced by OpenRouter's per-token prices.
        assert phone.scan("price: 0.0000008125") == []

    def test_long_zero_suffix_rejected(self):
        assert phone.scan("id 6468000000") == []

    def test_leading_trunk_zero_rejected(self):
        # 07854000000 -> payload 7854000000, 6 zeros -> rejected.
        assert phone.scan("07854000000") == []

    def test_real_number_with_two_zeros_still_found(self):
        # 9800012345 has 3 zeros. Fine.
        findings = phone.scan("call 9800012345")
        assert len(findings) == 1
        assert findings[0].category == "phone_in"

    def test_real_number_with_four_zeros_still_found(self):
        # 9800012340 has exactly 4 zeros. 4 < 5, so it survives.
        assert len(phone.scan("9800012340")) == 1


class TestAadhaarEntropyFilter:
    def test_float_artifact_near_miss_rejected(self):
        # 12 digits, fails checksum, 6 zeros -> suppressed.
        from gnosk.validators import aadhaar

        assert aadhaar.scan("value 234375000000") == []

    def test_real_near_miss_still_reported(self):
        # Fails checksum but has only 1 zero -> keep as low-confidence.
        from gnosk.validators import aadhaar

        findings = aadhaar.scan("ID 234567890123")
        assert len(findings) == 1
        assert findings[0].confidence == 0.3
