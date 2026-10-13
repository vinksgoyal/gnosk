"""Tests for email, Indian phone, and API-key validators.

Sample API keys here are constructed to match each provider's documented
shape. None of them are real, and none will authenticate anywhere.
"""

from vaultscan.validators import email, phone, secrets


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
