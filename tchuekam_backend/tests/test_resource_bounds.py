"""Tests de bornage des structures en mémoire (fuites et concurrence).

Le limiteur de débit et la liste noire de JTI sont indexés par des valeurs
fournies par le client (email, identifiant de jeton). Sans purge ni plafond,
un attaquant les fait croître indéfiniment.
"""

import sys
import threading
import time

from tchuekam_backend.core.rate_limiter import RateLimiter
from tchuekam_backend.core import security as security_module


def test_rate_limiter_prunes_expired_keys_instead_of_growing():
    limiter = RateLimiter()
    # 500 emails distincts : autant de cles, comme lors d'un balayage.
    for i in range(500):
        limiter.is_allowed(f"login:1.2.3.4:user{i}@example.com", max_requests=5, window_seconds=1)
    assert limiter.tracked_keys() == 500

    # Une fois la fenetre ecoulee, la purge periodique doit liberer les cles.
    time.sleep(1.1)
    limiter._last_sweep = time.monotonic() - 3600  # force le passage de la purge
    limiter.is_allowed("login:1.2.3.4:trigger@example.com", max_requests=5, window_seconds=1)
    assert limiter.tracked_keys() < 500, (
        f"Aucune cle purgee: {limiter.tracked_keys()} cles encore suivies"
    )


def test_rate_limiter_enforces_hard_key_cap():
    limiter = RateLimiter(max_tracked_keys=100)
    for i in range(400):
        limiter.is_allowed(f"k{i}", max_requests=5, window_seconds=3600)
    assert limiter.tracked_keys() <= 100


def test_rate_limiter_is_thread_safe_under_concurrency():
    """Le quota ne doit pas etre depasse par des requetes concurrentes.

    Les threads sont synchronises par une barriere et l'intervalle de bascule
    de l'interpreteur est reduit : sans ces deux precautions le GIL serialise
    de fait la section critique et le test passerait meme sur une
    implementation non verrouillee (verifie : la version sans verrou accorde
    jusqu'a 7 jetons pour un quota de 5 dans ces conditions).
    """
    previous_interval = sys.getswitchinterval()
    sys.setswitchinterval(1e-6)
    try:
        worst = 0
        for _ in range(20):
            limiter = RateLimiter()
            granted = []
            lock = threading.Lock()
            barrier = threading.Barrier(40)

            def attempt():
                barrier.wait()
                ok, _ = limiter.is_allowed(
                    "login:9.9.9.9:victim@example.com",
                    max_requests=5,
                    window_seconds=300,
                )
                if ok:
                    with lock:
                        granted.append(1)

            threads = [threading.Thread(target=attempt) for _ in range(40)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
            worst = max(worst, len(granted))
    finally:
        sys.setswitchinterval(previous_interval)

    assert worst == 5, (
        f"Course critique: jusqu'a {worst} tentatives autorisees au lieu de 5"
    )


def test_revoked_jti_blacklist_drops_expired_entries():
    security_module._REVOKED_JTI_BLACKLIST.clear()
    # Entree deja expiree : elle ne doit pas etre consideree comme revoquee...
    security_module.revoke_jti("expired-jti", expires_at=time.time() - 10)
    assert security_module.is_jti_revoked("expired-jti") is False
    # ...ni rester en memoire.
    assert "expired-jti" not in security_module._REVOKED_JTI_BLACKLIST

    security_module.revoke_jti("live-jti", expires_at=time.time() + 300)
    assert security_module.is_jti_revoked("live-jti") is True
    security_module._REVOKED_JTI_BLACKLIST.clear()


def test_revoked_jti_blacklist_sweeps_when_oversized():
    security_module._REVOKED_JTI_BLACKLIST.clear()
    past = time.time() - 10
    threshold = security_module._REVOCATION_SWEEP_THRESHOLD
    for i in range(threshold + 5):
        security_module._REVOKED_JTI_BLACKLIST[f"stale-{i}"] = past
    # Une revocation supplementaire doit declencher la purge des entrees mortes.
    security_module.revoke_jti("fresh-jti", expires_at=time.time() + 300)
    assert len(security_module._REVOKED_JTI_BLACKLIST) < threshold
    assert security_module.is_jti_revoked("fresh-jti") is True
    security_module._REVOKED_JTI_BLACKLIST.clear()
