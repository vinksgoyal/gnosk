"""Tests for the deterministic triage layer.

One test per rule, plus the negative cases the rules explicitly must
not catch (e.g. a real-looking API key inside tests/).
"""

from __future__ import annotations

import pytest

from gnosk.findings import Finding
from gnosk.triage import (
    VERDICT_FIXTURE,
    VERDICT_LIKELY_REAL,
    is_known_fixture_value,
    is_test_path,
    triage,
)


def _f(
    cat: str,
    val: str,
    conf: float = 0.9,
    validator: str | None = None,
) -> Finding:
    return Finding(
        category=cat,
        value=val,
        start=0,
        end=len(val),
        confidence=conf,
        source="validator",
        validator=validator or f"{cat}.test",
    )


# ---------------------------------------------------------------------------
# is_test_path
# ---------------------------------------------------------------------------

class TestIsTestPath:
    @pytest.mark.parametrize(
        "path",
        [
            "tests/test_a.py",
            "src/tests/helpers.py",
            "project/fixtures/sample.txt",
            "app/examples/demo.py",
            "data/sample_data/one.json",
            "spec/parser.spec.ts",
            "src/__tests__/button.test.ts",
            "test_models.py",
            "models_test.py",
            "Component.test.jsx",
        ],
    )
    def test_matches_test_paths(self, path):
        assert is_test_path(path) is True

    @pytest.mark.parametrize(
        "path",
        [
            "src/config.py",
            "app/main.go",
            "lib/parser.py",
            "docs/readme.md",
            "README.md",
            "contest/entry.py",  # contains "test" as substring, not a segment
        ],
    )
    def test_does_not_match_production_paths(self, path):
        assert is_test_path(path) is False


# ---------------------------------------------------------------------------
# is_known_fixture_value
# ---------------------------------------------------------------------------

class TestIsKnownFixtureValue:
    @pytest.mark.parametrize(
        "value",
        [
            "alice@example.com",
            "bob@example.org",
            "anyone@example.net",
            "user@test.local",
            "foo@whatever.com",
            "admin@client.com",
            "AKIAIOSFODNN7EXAMPLE",
        ],
    )
    def test_known_fixtures(self, value):
        assert is_known_fixture_value(value) is True

    @pytest.mark.parametrize(
        "value",
        [
            "real@realclientcompany.com",
            "ceo@business.in",
            "AKIAIOSFODNN7REALKEY1",
            "some-random-string",
        ],
    )
    def test_not_known_fixtures(self, value):
        assert is_known_fixture_value(value) is False


# ---------------------------------------------------------------------------
# Rule 1 — known fixture values
# ---------------------------------------------------------------------------

class TestRule1KnownFixtureValues:
    def test_alice_in_production_path_is_still_fixture(self):
        verdict = triage(_f("email", "alice@example.com"), "src/config.py")
        assert verdict is not None
        assert verdict[0] == VERDICT_FIXTURE

    def test_aws_example_key_is_fixture_even_in_production(self):
        verdict = triage(_f("api_key", "AKIAIOSFODNN7EXAMPLE"), "src/aws.py")
        assert verdict is not None
        assert verdict[0] == VERDICT_FIXTURE


# ---------------------------------------------------------------------------
# Rule 2 — API keys always deferred
# ---------------------------------------------------------------------------

class TestRule2ApiKeysDefer:
    def test_real_looking_aws_key_in_tests_is_deferred(self):
        # Negative test: path rule must NOT dismiss a real-looking key.
        f = _f("api_key", "AKIA1234567890ABCDEF")
        assert triage(f, "tests/test_aws.py") is None

    def test_github_pat_in_tests_is_deferred(self):
        f = _f("api_key", "ghp_" + "A" * 36, validator="secrets.github_pat")
        assert triage(f, "tests/test_tokens.py") is None

    def test_stripe_key_in_tests_is_deferred(self):
        f = _f("api_key", "sk_live_" + "A" * 24, validator="secrets.stripe_secret")
        assert triage(f, "app/tests/stripe_test.py") is None


# ---------------------------------------------------------------------------
# Rule 3 — checksum-valid Aadhaar
# ---------------------------------------------------------------------------

class TestRule3ChecksumValidAadhaar:
    # 234567890124 is Verhoeff-valid; constructed for testing.
    VALID = "234567890124"

    def test_valid_aadhaar_in_production_path_is_likely_real(self):
        verdict = triage(_f("aadhaar", self.VALID, conf=1.0), "src/users.py")
        assert verdict is not None
        assert verdict[0] == VERDICT_LIKELY_REAL

    def test_valid_aadhaar_in_tests_is_deferred(self):
        # Negative test: a checksum-valid Aadhaar in tests/ still goes
        # to the model — we don't trust the path rule to dismiss it.
        verdict = triage(_f("aadhaar", self.VALID, conf=1.0), "tests/test_x.py")
        assert verdict is None

    def test_checksum_invalid_aadhaar_is_deferred(self):
        # 234567890123 fails the checksum. Triage leaves it to the model.
        f = _f("aadhaar", "234567890123", conf=0.3)
        assert triage(f, "src/users.py") is None


# ---------------------------------------------------------------------------
# Rule 4 — test path dismisses the rest
# ---------------------------------------------------------------------------

class TestRule4TestPathFallback:
    def test_email_in_tests_is_fixture(self):
        f = _f("email", "someone@realclient.com")
        verdict = triage(f, "tests/test_email.py")
        assert verdict is not None
        assert verdict[0] == VERDICT_FIXTURE

    def test_phone_in_fixtures_is_fixture(self):
        f = _f("phone_in", "9876543210")
        verdict = triage(f, "spec/sample_data/one.txt")
        assert verdict is not None
        assert verdict[0] == VERDICT_FIXTURE

    def test_pan_in_examples_is_fixture(self):
        f = _f("pan", "ABCPD1234E")
        verdict = triage(f, "examples/pan_demo.py")
        assert verdict is not None
        assert verdict[0] == VERDICT_FIXTURE


# ---------------------------------------------------------------------------
# Rule 5 — defer everything else
# ---------------------------------------------------------------------------

class TestRule5Defer:
    def test_email_in_production_path_defers(self):
        f = _f("email", "ceo@realcompany.in")
        assert triage(f, "src/contacts.py") is None

    def test_phone_in_production_path_defers(self):
        f = _f("phone_in", "9876543210")
        assert triage(f, "app/notify.py") is None

    def test_pan_in_production_path_defers(self):
        f = _f("pan", "ABCPD1234E")
        assert triage(f, "src/kyc.py") is None


class TestCountNeedsModel:
    def test_mixed_batch(self):
        from gnosk.triage import count_needs_model

        # alice = triaged, key in tests = deferred (rule 2),
        # phone in tests = triaged, email in src = deferred.
        findings = [
            _f("email", "alice@example.com"),
            _f("api_key", "AKIA1234567890ABCDEF"),
            _f("phone_in", "9876543210"),
            _f("email", "ceo@realclient.com"),
        ]
        assert count_needs_model("tests/x.py", findings[:3]) == 1
        assert count_needs_model("src/x.py", [findings[3]]) == 1
        assert count_needs_model("tests/x.py", []) == 0
