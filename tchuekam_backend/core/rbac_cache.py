"""Cache des décisions d'autorisation RBAC.

Pourquoi
--------
``require_permission`` est monté sur la plupart des endpoints, et
``RbacService.has_permission`` exécute deux requêtes à chaque appel : une
jointure pour les rôles de l'utilisateur, une jointure sur trois tables pour
ses permissions. C'est le poste de coût dominant en base sous charge — bien
avant la lecture de la session et de l'utilisateur, qui sont deux accès par
clé primaire.

Ce module centralise les clés et l'invalidation. Il vit dans ``core`` parce que
les deux couches en dépendent : le service pour *lire*, le dépôt pour
*invalider* lors d'une mutation. Mettre l'invalidation dans le dépôt et non
dans le service est délibéré — ``api/v1/rbac.py`` appelle le dépôt
directement (``rbac_service.rbac_repo.create_permission``), donc le dépôt est
le seul passage obligé.

Fraîcheur
---------
Deux mécanismes se superposent :

* **invalidation explicite** à chaque mutation RBAC, qui couvre le cas normal ;
* **TTL court** (``TCHUEKAM_RBAC_CACHE_TTL``, 30 s par défaut), qui borne la
  fenêtre de deux situations que l'invalidation seule ne couvre pas : une
  écriture directe en base hors application, et la course classique du
  cache-aside — un lecteur lit la base, une mutation s'intercale et invalide,
  puis le lecteur écrit sa valeur déjà périmée. La fenêtre d'obsolescence
  maximale est donc le TTL. Mettre ``TCHUEKAM_RBAC_CACHE_TTL=0`` désactive le
  cache et rétablit une lecture en base à chaque requête.
"""

from __future__ import annotations

import logging
import os

from tchuekam_backend.core.cache import cache_service

logger = logging.getLogger("tchuekam_backend.rbac_cache")

#: Préfixe commun à toutes les entrées, pour l'invalidation en masse.
RBAC_PREFIX = "rbac:"


def cache_ttl_seconds() -> int:
    """TTL des décisions d'autorisation. ``0`` désactive le cache."""
    raw = os.getenv("TCHUEKAM_RBAC_CACHE_TTL", "").strip()
    if raw:
        try:
            value = int(raw)
        except ValueError:
            logger.warning("TCHUEKAM_RBAC_CACHE_TTL invalide (%r), valeur par défaut utilisée.", raw)
            return 30
        return max(0, value)
    return 30


def is_enabled() -> bool:
    return cache_ttl_seconds() > 0


def user_key(user_id: str) -> str:
    return f"{RBAC_PREFIX}user:{user_id}"


def invalidate_user(user_id: str) -> None:
    """Invalide les autorisations d'un seul utilisateur.

    À appeler quand l'appartenance de *cet* utilisateur à des rôles change.
    """
    if not user_id:
        return
    cache_service.delete(user_key(str(user_id)))


def invalidate_all() -> None:
    """Invalide les autorisations de tous les utilisateurs.

    À appeler quand c'est la définition d'un rôle qui change (permissions
    attachées, suppression du rôle) : l'effet porte sur tous ses porteurs, et
    la table d'association ne permet pas de les énumérer à moindre coût depuis
    le dépôt. Les mutations RBAC étant rares et administratives, purger le
    préfixe entier est à la fois correct et suffisant.
    """
    removed = cache_service.invalidate_pattern(RBAC_PREFIX)
    if removed:
        logger.info("Cache RBAC invalidé (%s entrées).", removed)
