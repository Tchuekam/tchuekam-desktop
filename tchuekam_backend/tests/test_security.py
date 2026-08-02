"""
Tests de sécurité : Complexité des mots de passe, Anti-force-brute, Révocation et Audit.
"""

from tchuekam_backend.core.security import (
    validate_password_complexity,
    hash_password,
    verify_password,
    revoke_jti,
    is_jti_revoked,
)
from tchuekam_backend.core.rate_limiter import rate_limiter


def test_password_complexity_rules():
    # Trop court
    valid, msg = validate_password_complexity("Short1!")
    assert valid is False

    # Sans majuscule
    valid, msg = validate_password_complexity("lowercase1!")
    assert valid is False

    # Sans chiffre
    valid, msg = validate_password_complexity("NoDigitsHere!")
    assert valid is False

    # Sans caractère spécial
    valid, msg = validate_password_complexity("NoSpecial123")
    assert valid is False

    # Valide
    valid, msg = validate_password_complexity("ValidPassword123!")
    assert valid is True
    assert msg is None


def test_password_hashing_and_verification():
    raw_pwd = "SuperSecretPassword123!"
    h = hash_password(raw_pwd)
    assert h != raw_pwd
    assert verify_password(raw_pwd, h) is True
    assert verify_password("WrongPassword123!", h) is False


def test_jti_revocation_blacklist():
    test_jti = "unique_jti_token_9999"
    assert is_jti_revoked(test_jti) is False
    revoke_jti(test_jti)
    assert is_jti_revoked(test_jti) is True


def test_rate_limiter_sliding_window():
    key = "test_rate_limit_ip"
    rate_limiter.reset(key)

    # 5 requêtes autorisées
    for _ in range(5):
        allowed, rem = rate_limiter.is_allowed(key, max_requests=5, window_seconds=60)
        assert allowed is True

    # 6ème requête bloquée
    allowed, rem = rate_limiter.is_allowed(key, max_requests=5, window_seconds=60)
    assert allowed is False
    assert rem == 0
