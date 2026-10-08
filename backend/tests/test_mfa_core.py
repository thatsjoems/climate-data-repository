"""
The building blocks of two-step sign-in (app/core/mfa.py): the one-time code, the secret at rest, the recovery codes and the step token.

The code algorithm is checked against the published test vectors of RFC 6238 (Appendix B, SHA-1), so it agrees with every authenticator app.
The rest pins down the properties that make it safe: a code works once, within one step either side of now and not beyond; a copy of the
database cannot produce codes; a recovery code works once; and a step token is valid only for its own purpose and only for five minutes.
"""
import json

import pytest
from jose import jwt

from app.core import mfa
from app.core.config import settings

RFC_SECRET = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"      # the ASCII string 12345678901234567890 in base32, as in the RFC


@pytest.mark.parametrize("seconds, expected", [
    (59, "94287082"), (1111111109, "07081804"), (1111111111, "14050471"),
    (1234567890, "89005924"), (2000000000, "69279037"), (20000000000, "65353130"),
])
def test_the_code_matches_the_rfc_6238_test_vectors(seconds, expected):
    assert mfa.totp_at(RFC_SECRET, seconds // 30, digits=8) == expected


def test_a_code_is_six_digits_by_default():
    code = mfa.totp_at(RFC_SECRET, 123456)
    assert len(code) == 6 and code.isdigit()


def test_a_code_is_accepted_one_step_either_side_of_now_and_not_two():
    now = 1_700_000_000
    centre = mfa.current_step(now)
    for step in (centre - 1, centre, centre + 1):
        assert mfa.verify_totp(RFC_SECRET, mfa.totp_at(RFC_SECRET, step), now=now) == step
    for step in (centre - 2, centre + 2):
        assert mfa.verify_totp(RFC_SECRET, mfa.totp_at(RFC_SECRET, step), now=now) is None


def test_a_code_works_once_and_nothing_older_is_accepted_afterwards():
    now = 1_700_000_000
    centre = mfa.current_step(now)
    code = mfa.totp_at(RFC_SECRET, centre)
    assert mfa.verify_totp(RFC_SECRET, code, last_step=centre - 1, now=now) == centre
    assert mfa.verify_totp(RFC_SECRET, code, last_step=centre, now=now) is None                      # replay
    assert mfa.verify_totp(RFC_SECRET, mfa.totp_at(RFC_SECRET, centre - 1), last_step=centre, now=now) is None   # older
    assert mfa.verify_totp(RFC_SECRET, mfa.totp_at(RFC_SECRET, centre + 1), last_step=centre, now=now) == centre + 1


@pytest.mark.parametrize("bad", [None, "", "12345", "1234567", "abcdef", "12 34 5", "12-456"])
def test_a_malformed_code_is_refused(bad):
    assert mfa.verify_totp(RFC_SECRET, bad, now=1_700_000_000) is None


def test_spaces_inside_a_code_are_tolerated():
    now = 1_700_000_000
    code = mfa.totp_at(RFC_SECRET, mfa.current_step(now))
    assert mfa.verify_totp(RFC_SECRET, f"{code[:3]} {code[3:]}", now=now) is not None


def test_a_new_secret_is_random_and_in_the_form_authenticator_apps_expect():
    a, b = mfa.generate_secret(), mfa.generate_secret()
    assert a != b and len(a) == 32 and set(a) <= set("ABCDEFGHIJKLMNOPQRSTUVWXYZ234567")


def test_the_secret_is_encrypted_at_rest_and_a_different_key_cannot_read_it(monkeypatch):
    secret = mfa.generate_secret()
    stored = mfa.encrypt_secret(secret)
    assert secret not in stored and mfa.decrypt_secret(stored) == secret
    monkeypatch.setattr(settings, "SECRET_KEY", "another-key-" + "x" * 40)
    with pytest.raises(Exception):
        mfa.decrypt_secret(stored)


def test_recovery_codes_are_ten_distinct_codes_kept_only_as_hashes():
    codes, stored = mfa.new_recovery_codes()
    hashes = json.loads(stored)
    assert len(codes) == 10 and len(set(codes)) == 10 and len(hashes) == 10
    assert all(len(c) == 11 and c[5] == "-" for c in codes)
    assert not any(c.replace("-", "") in stored or c in stored for c in codes)


def test_a_recovery_code_works_once_whatever_its_case_or_dashes():
    codes, stored = mfa.new_recovery_codes()
    typed = codes[3].lower().replace("-", " ")
    remaining = mfa.use_recovery_code(stored, typed)
    assert remaining is not None and mfa.recovery_codes_left(remaining) == 9
    assert mfa.use_recovery_code(remaining, codes[3]) is None                  # already used
    assert mfa.use_recovery_code(remaining, codes[4]) is not None              # the others still work


@pytest.mark.parametrize("bad", ["", "   ", "AAAAA-AAAAA", None])
def test_a_wrong_or_blank_recovery_code_is_refused(bad):
    _, stored = mfa.new_recovery_codes()
    assert mfa.use_recovery_code(stored, bad) is None


def test_recovery_hashes_depend_on_the_secret_key(monkeypatch):
    codes, stored = mfa.new_recovery_codes()
    monkeypatch.setattr(settings, "SECRET_KEY", "another-key-" + "y" * 40)
    assert mfa.use_recovery_code(stored, codes[0]) is None


def test_a_step_token_is_valid_only_for_its_own_purpose():
    token = mfa.make_step_token("user-1", "mfa")
    assert mfa.read_step_token(token, "mfa") == "user-1"
    assert mfa.read_step_token(token, "mfa_setup") is None


def test_an_ordinary_access_token_is_not_a_step_token_and_a_tampered_one_is_refused():
    access_like = jwt.encode({"sub": "user-1", "role": "BOT_USER"}, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    assert mfa.read_step_token(access_like, "mfa") is None
    token = mfa.make_step_token("user-1", "mfa")
    assert mfa.read_step_token(token[:-3] + ("AAA" if token[-3:] != "AAA" else "BBB"), "mfa") is None


def test_a_step_token_expires(monkeypatch):
    monkeypatch.setattr(mfa, "STEP_TOKEN_MINUTES", -1)
    assert mfa.read_step_token(mfa.make_step_token("user-1", "mfa"), "mfa") is None


def test_the_authenticator_address_names_the_service_and_the_account():
    uri = mfa.otpauth_uri(RFC_SECRET, "bot analyst", issuer="Climate Data Repository (BOT)")
    assert uri.startswith("otpauth://totp/Climate%20Data%20Repository%20%28BOT%29:bot%20analyst?")
    assert f"secret={RFC_SECRET}" in uri and "period=30" in uri and "digits=6" in uri
