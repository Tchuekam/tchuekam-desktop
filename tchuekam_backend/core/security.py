"""
Module de sécurité : Hachage des mots de passe, gestion des jetons JWT,
génération de jetons sécurisés et liste noire de révocations.
"""

import base64
import hashlib
import hmac
import logging
import os
import re
import secrets
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Set, Tuple

import jwt
from tchuekam_backend.core import redis_client
from tchuekam_backend.core.config import settings

logger = logging.getLogger("tchuekam_backend.security")

# Liste noire de révocation, pour invalidation immédiate d'un JWT.
#
# Elle est portée par Redis dès qu'il est configuré, donc partagée par tous
# les workers et toutes les instances : un jeton révoqué sur un worker est
# rejeté par tous. Sans Redis, le repli est le dictionnaire local ci-dessous,
# qui ne protège qu'un déploiement mono-worker.
#
# Dans les deux cas cette liste n'est qu'un accélérateur : la révocation
# durable s'appuie sur ``UserSession.is_revoked`` et sur la comparaison du
# ``refresh_token_hash`` persisté (voir ``AuthService.refresh_access_token``),
# vérifiés en base à chaque requête authentifiée.
#
# JTI -> horodatage d'expiration (epoch). Les entrées périmées sont purgées
# pour éviter une croissance non bornée.
_REVOKED_JTI_BLACKLIST: Dict[str, float] = {}
_REVOCATION_LOCK = threading.Lock()
_REVOCATION_SWEEP_THRESHOLD = 10_000


def _jti_redis_key(jti: str) -> str:
    return redis_client.namespaced("jti", jti)

def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value > 0 else default


#: Paramètres Argon2id. Les valeurs par défaut sont celles d'``argon2-cffi``
#: (time_cost=3, memory_cost=64 MiB, parallelism=4), conformes à la RFC 9106.
#:
#: Elles sont rendues configurables parce qu'elles ne concernent pas seulement
#: la robustesse du hachage : 64 MiB sont alloués *par vérification en cours*.
#: Quarante connexions simultanées réservent donc 2,5 Gio, et un service qui ne
#: borne pas cette concurrence se fait évincer par l'OOM killer sur une simple
#: rafale de connexions. On préfère borner la concurrence (voir
#: ``_HASHING_SLOTS``) plutôt qu'affaiblir le hachage, mais un exploitant qui
#: connaît sa cible doit pouvoir arbitrer.
_ARGON2_TIME_COST = _int_env("TCHUEKAM_ARGON2_TIME_COST", 3)
_ARGON2_MEMORY_COST_KIB = _int_env("TCHUEKAM_ARGON2_MEMORY_KIB", 65536)
_ARGON2_PARALLELISM = _int_env("TCHUEKAM_ARGON2_PARALLELISM", 4)

# Try importing argon2 or bcrypt for primary enterprise hashing
try:
    from argon2 import PasswordHasher

    _ARGON2_HASHER = PasswordHasher(
        time_cost=_ARGON2_TIME_COST,
        memory_cost=_ARGON2_MEMORY_COST_KIB,
        parallelism=_ARGON2_PARALLELISM,
    )
except ImportError:
    _ARGON2_HASHER = None


def _default_hashing_slots() -> int:
    """Nombre de hachages de mot de passe autorisés en parallèle.

    Mesuré sur ce backend : le chemin de connexion plafonne à 17,8 req/s avec
    un p50 de 2,1 s à 40 connexions simultanées, pendant que le reste de l'API
    est privé de processeur. C'est le comportement attendu d'une fonction
    délibérément coûteuse — mais sans borne, une rafale de connexions (après un
    déploiement, ou une attaque par bourrage d'identifiants répartie sur de
    nombreuses adresses) consomme tout le processeur et toute la mémoire.

    Les protections existantes ne couvrent pas ce cas : le limiteur
    anti-force-brute est indexé *par e-mail* (5 tentatives / 5 min), et le
    quota global est *par adresse IP*. Ni l'un ni l'autre ne borne la
    concurrence agrégée.

    La valeur par défaut suit le nombre de cœurs, puisque le hachage est
    borné par le processeur : au-delà, les hachages supplémentaires ne font
    que se disputer les mêmes cœurs tout en réservant chacun leur mémoire.
    """
    explicit = _int_env("TCHUEKAM_PASSWORD_HASH_CONCURRENCY", 0)
    if explicit:
        return explicit
    return max(2, min(os.cpu_count() or 2, 8))


#: Les endpoints synchrones de FastAPI tournent dans un pool de threads, donc
#: un sémaphore de threads est le bon outil (et non un sémaphore asyncio).
_HASHING_SLOTS = threading.BoundedSemaphore(_default_hashing_slots())

#: Attente maximale d'un créneau de hachage. Au-delà, mieux vaut refuser que
#: faire patienter un client qui a déjà abandonné.
_HASHING_WAIT_SECONDS = float(os.getenv("TCHUEKAM_PASSWORD_HASH_WAIT_SECONDS", "") or 5.0)


class PasswordHashingBusy(RuntimeError):
    """Aucun créneau de hachage disponible dans le délai imparti.

    L'appelant doit répondre 503 : le service est saturé, l'identifiant fourni
    n'est pas en cause et le client peut réessayer.
    """


@contextmanager
def _hashing_slot():
    acquired = _HASHING_SLOTS.acquire(timeout=_HASHING_WAIT_SECONDS)
    if not acquired:
        raise PasswordHashingBusy(
            "Trop de vérifications de mot de passe simultanées."
        )
    try:
        yield
    finally:
        _HASHING_SLOTS.release()


def hashing_capacity() -> dict:
    """État du limiteur de hachage (observabilité et tests)."""
    return {
        "slots": _default_hashing_slots(),
        "argon2_memory_kib": _ARGON2_MEMORY_COST_KIB,
        "argon2_time_cost": _ARGON2_TIME_COST,
        "max_resident_kib": _default_hashing_slots() * _ARGON2_MEMORY_COST_KIB,
    }


def hash_password(password: str) -> str:
    """Hache un mot de passe de manière sécurisée (Argon2id si disponible, ou PBKDF2-HMAC-SHA256).

    Raises:
        PasswordHashingBusy: si aucun créneau n'est libre dans le délai imparti.
    """
    with _hashing_slot():
        if _ARGON2_HASHER:
            try:
                return f"argon2id${_ARGON2_HASHER.hash(password)}"
            except Exception:
                pass

        salt = os.urandom(16)
        key = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 120_000)
        return f"pbkdf2_sha256$120000${base64.b64encode(salt).decode('ascii')}${base64.b64encode(key).decode('ascii')}"


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Vérifie qu'un mot de passe en clair correspond au hash enregistré (Argon2id ou PBKDF2).

    Raises:
        PasswordHashingBusy: si aucun créneau n'est libre dans le délai imparti.
            Volontairement propagé et non transformé en ``False`` : renvoyer
            « mot de passe invalide » parce que le serveur est chargé
            verrouillerait des comptes légitimes et enverrait l'utilisateur
            réinitialiser un mot de passe correct.
    """
    with _hashing_slot():
        try:
            if hashed_password.startswith("argon2id$"):
                if _ARGON2_HASHER:
                    raw_hash = hashed_password[len("argon2id$"):]
                    return _ARGON2_HASHER.verify(raw_hash, plain_password)

            parts = hashed_password.split('$')
            if len(parts) != 4 or parts[0] != 'pbkdf2_sha256':
                return False
            iterations = int(parts[1])
            salt = base64.b64decode(parts[2].encode('ascii'))
            expected_key = base64.b64decode(parts[3].encode('ascii'))
            computed_key = hashlib.pbkdf2_hmac('sha256', plain_password.encode('utf-8'), salt, iterations)
            return hmac.compare_digest(computed_key, expected_key)
        except Exception:
            return False


#: Hash de leurre calculé paresseusement, utilisé pour égaliser le temps de
#: réponse lorsqu'aucun utilisateur ne correspond à l'email fourni.
_DUMMY_PASSWORD_HASH: Optional[str] = None


def dummy_verify_password(plain_password: str) -> None:
    """Effectue le même travail cryptographique qu'une vérification réelle.

    Sans cela, une connexion avec un email inconnu retourne sans jamais dériver
    de clé, alors qu'un email connu paie le coût d'Argon2/PBKDF2. L'écart de
    latence (mesuré à ~290 ms contre ~50 ms, sans recouvrement) constitue un
    oracle d'énumération des comptes : il permet de déterminer d'une seule
    requête si une adresse est enregistrée. Le limiteur anti-force-brute est
    indexé par email et ne freine donc pas ce balayage.
    """
    global _DUMMY_PASSWORD_HASH
    if _DUMMY_PASSWORD_HASH is None:
        _DUMMY_PASSWORD_HASH = hash_password(secrets.token_urlsafe(32))
    verify_password(plain_password, _DUMMY_PASSWORD_HASH)


def validate_password_complexity(password: str) -> Tuple[bool, Optional[str]]:
    """Valide la complexité minimale d'un mot de passe."""
    if len(password) < settings.PASSWORD_MIN_LENGTH:
        return False, f"Le mot de passe doit contenir au moins {settings.PASSWORD_MIN_LENGTH} caractères."
    if settings.PASSWORD_REQUIRE_UPPERCASE and not re.search(r'[A-Z]', password):
        return False, "Le mot de passe doit contenir au moins une lettre majuscule."
    if settings.PASSWORD_REQUIRE_LOWERCASE and not re.search(r'[a-z]', password):
        return False, "Le mot de passe doit contenir au moins une lettre minuscule."
    if settings.PASSWORD_REQUIRE_DIGIT and not re.search(r'\d', password):
        return False, "Le mot de passe doit contenir au moins un chiffre."
    if settings.PASSWORD_REQUIRE_SPECIAL and not re.search(r'[@$!%*?&_\-#^\(\)\[\]\{\}]', password):
        return False, "Le mot de passe doit contenir au moins un caractère spécial (@$!%*?&_)."
    return True, None


def generate_secure_token() -> str:
    """Génère un jeton aléatoire sécurisé de 32 octets (hex)."""
    return secrets.token_hex(32)


def hash_token(token: str) -> str:
    """Hache un jeton temporaire avec SHA256."""
    return hashlib.sha256(token.encode('utf-8')).hexdigest()


def create_access_token(
    user_id: str,
    email: str,
    session_id: str,
    roles: list = None,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """Crée un Access Token JWT avec une durée de vie courte (par défaut 15 min)."""
    now = datetime.now(timezone.utc)
    delta = expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    expire = now + delta
    jti = secrets.token_hex(16)
    
    payload = {
        "sub": str(user_id),
        "email": email,
        "session_id": str(session_id),
        "roles": roles or [],
        "type": "access",
        "jti": jti,
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }
    encoded_jwt = jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    return encoded_jwt


def create_refresh_token(
    user_id: str,
    session_id: str,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """Crée un Refresh Token JWT avec une durée de vie plus longue (par défaut 7 jours)."""
    now = datetime.now(timezone.utc)
    delta = expires_delta or timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    expire = now + delta
    jti = secrets.token_hex(16)
    
    payload = {
        "sub": str(user_id),
        "session_id": str(session_id),
        "type": "refresh",
        "jti": jti,
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }
    encoded_jwt = jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    return encoded_jwt


def decode_jwt_token(token: str) -> Dict[str, Any]:
    """Décode et vérifie la signature et l'expiration d'un jeton JWT.
    
    Raises:
        jwt.ExpiredSignatureError: Si le jeton est expiré.
        jwt.InvalidTokenError: Si le jeton est invalide ou en liste noire.
    """
    payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    jti = payload.get("jti")
    if jti and is_jti_revoked(jti):
        raise jwt.InvalidTokenError("Ce jeton a été révoqué.")
    return payload


def _revoke_jti_in_memory(jti: str, expires_at: float) -> None:
    with _REVOCATION_LOCK:
        _REVOKED_JTI_BLACKLIST[jti] = expires_at
        now = time.time()
        if len(_REVOKED_JTI_BLACKLIST) > _REVOCATION_SWEEP_THRESHOLD:
            for stale in [j for j, exp in _REVOKED_JTI_BLACKLIST.items() if exp <= now]:
                del _REVOKED_JTI_BLACKLIST[stale]


def revoke_jti(jti: str, expires_at: Optional[float] = None) -> None:
    """Ajoute un ID unique de jeton (JTI) à la liste noire de révocation.

    Chaque entrée porte une date d'expiration : au-delà, le jeton est de toute
    façon rejeté par la vérification de signature, et le conserver ne ferait
    que faire croître l'ensemble sans limite (fuite mémoire alimentée par le
    trafic). À défaut de date connue, on retient l'entrée le temps de vie
    maximal d'un refresh token.

    Avec Redis configuré, l'entrée est écrite dans Redis *et* en mémoire. La
    copie locale coûte un pointeur et garantit que la révocation tient sur ce
    worker même si Redis tombe juste après l'écriture.
    """
    if not jti:
        return
    if expires_at is None:
        expires_at = time.time() + settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400

    remaining = expires_at - time.time()
    if remaining <= 0:
        # Jeton déjà expiré : la vérification de signature le rejette de toute
        # façon, donc l'inscrire en liste noire n'apporte rien. Et il ne faut
        # surtout pas l'y inscrire « au moins une seconde » pour satisfaire le
        # TTL minimum de Redis : ``is_jti_revoked`` le rapporterait alors comme
        # révoqué pendant cette seconde, c'est-à-dire répondrait « révoqué »
        # pour un jeton simplement périmé.
        return

    if redis_client.is_configured():
        client = redis_client.get_sync_client()
        if client is not None:
            # Redis expire l'entrée tout seul : pas de purge à faire, et
            # aucune croissance non bornée même sous un trafic de révocations.
            try:
                client.set(_jti_redis_key(jti), "1", ex=max(1, int(remaining)))
            except Exception as exc:
                redis_client.report_failure(exc)

    _revoke_jti_in_memory(jti, expires_at)


def reset_revocation_state(*jtis: str) -> None:
    """Efface la liste noire de révocation, en mémoire *et* dans Redis.

    Vider ``_REVOKED_JTI_BLACKLIST`` ne suffit plus : depuis que la liste est
    portée par Redis, la copie partagée survit à l'effacement local. Un test
    qui veut exercer la détection de rejeu *durable* — la comparaison du hash
    de refresh token persisté, qui est le mécanisme de défense réel — doit donc
    effacer les deux, sinon ``decode_jwt_token`` court-circuite sur la
    révocation partagée et le code n'atteint jamais cette comparaison.

    Sans argument, efface tout. Avec des JTI, n'efface que ceux-là.
    """
    with _REVOCATION_LOCK:
        if jtis:
            for jti in jtis:
                _REVOKED_JTI_BLACKLIST.pop(jti, None)
        else:
            _REVOKED_JTI_BLACKLIST.clear()

    if not redis_client.is_configured():
        return
    client = redis_client.get_sync_client()
    if client is None:
        return
    try:
        if jtis:
            client.delete(*[_jti_redis_key(jti) for jti in jtis])
            return
        pattern = redis_client.namespaced("jti", "*")
        cursor = 0
        while True:
            cursor, keys = client.scan(cursor=cursor, match=pattern, count=500)
            if keys:
                client.delete(*keys)
            if cursor == 0:
                break
    except Exception as exc:
        redis_client.report_failure(exc)


def is_jti_revoked(jti: str) -> bool:
    """Vérifie si un JTI est dans la liste noire et toujours pertinent.

    La copie locale est consultée d'abord : c'est une recherche en dictionnaire
    et elle évite un aller-retour réseau pour les jetons révoqués par ce
    worker. Redis est ensuite interrogé pour les révocations prononcées
    ailleurs.
    """
    if not jti:
        return False

    with _REVOCATION_LOCK:
        expires_at = _REVOKED_JTI_BLACKLIST.get(jti)
        if expires_at is not None:
            if expires_at > time.time():
                return True
            del _REVOKED_JTI_BLACKLIST[jti]

    if redis_client.is_configured():
        client = redis_client.get_sync_client()
        if client is not None:
            try:
                return bool(client.exists(_jti_redis_key(jti)))
            except Exception as exc:
                # Panne Redis : on retombe sur le résultat local (déjà calculé
                # ci-dessus, donc « non révoqué »). La vérification en base de
                # ``UserSession.is_revoked``, faite à chaque requête
                # authentifiée, reste le filet de sécurité durable.
                redis_client.report_failure(exc)

    return False
