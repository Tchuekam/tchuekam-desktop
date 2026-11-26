"""Alignement du pool de threads sur le pool de connexions.

Le problème
-----------
FastAPI exécute tout endpoint déclaré ``def`` (et non ``async def``) dans le
pool de threads d'AnyIO, dont la largeur par défaut est de 40. Chacun de ces
endpoints réclame une connexion SQL via ``get_db``. Le pool SQLAlchemy, lui,
en offre ``pool_size + max_overflow``, soit 20 avec les valeurs par défaut.

Deux files d'attente de largeurs différentes se succèdent donc sur le chemin
d'une requête, et c'est la plus étroite qui compte. 40 threads se disputent
20 connexions : 20 d'entre eux attendent dans ``QueuePool._do_get`` jusqu'à
``pool_timeout``, puis lèvent ``TimeoutError``. Le client reçoit un 500 alors
que ni le processeur ni la base n'étaient occupés — mesuré sous charge : 40
threads bloqués en attente de connexion, zéro requête SQL en cours, processeur
à 100 % inactif.

Avec un pool de threads de la même largeur que le pool de connexions, un
thread qui démarre a la garantie d'obtenir une connexion. L'attente se fait
alors dans la boucle d'événements, là où elle est gratuite et ordonnée : la
charge excédentaire se traduit par de la latence, pas par des erreurs.

Pourquoi ce n'est pas réglable depuis gunicorn
----------------------------------------------
L'option ``threads`` de gunicorn ne s'applique qu'à ses propres workers
(``gthread``) : ``UvicornWorker`` l'ignore totalement. La largeur du pool
AnyIO ne peut être fixée que depuis le processus, une fois la boucle
d'événements démarrée — d'où ce module, appelé par ``lifespan``.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

logger = logging.getLogger("tchuekam_backend.concurrency")


def configured_thread_limit() -> Optional[int]:
    """Largeur de pool de threads demandée explicitement, s'il y en a une."""
    raw = os.getenv("TCHUEKAM_WORKER_THREADS", "").strip()
    try:
        value = int(raw)
    except ValueError:
        return None
    return value if value > 0 else None


def recommended_thread_limit() -> int:
    """Largeur à appliquer : celle du pool de connexions.

    Pas de marge ajoutée au-dessus du pool de connexions. Un thread
    supplémentaire ne peut que se retrouver à attendre une connexion, ce qui
    est exactement le comportement que l'on supprime. Les requêtes qui ne
    touchent pas la base (sondes, ``/metrics``) sont servies par la boucle
    d'événements ou coûtent si peu qu'elles n'ont pas besoin de leur propre
    voie.
    """
    explicit = configured_thread_limit()
    if explicit is not None:
        return explicit

    from tchuekam_backend.core.database import _IS_SQLITE, pool_settings

    if _IS_SQLITE:
        # SQLite sérialise les écritures : élargir ne sert à rien, et le
        # pool par défaut n'a pas de notion d'``overflow``. On garde une
        # largeur modeste pour le développement et les tests.
        return 16

    settings = pool_settings()
    return max(4, settings["pool_size"] + settings["max_overflow"])


def apply_thread_limit() -> Optional[int]:
    """Fixe la largeur du pool de threads AnyIO. À appeler depuis ``lifespan``.

    Returns:
        La largeur appliquée, ou ``None`` si elle n'a pas pu être fixée (AnyIO
        absent, ou appel hors boucle d'événements).
    """
    try:
        import anyio.to_thread

        limiter = anyio.to_thread.current_default_thread_limiter()
    except Exception as exc:
        logger.warning(
            "Largeur du pool de threads non appliquée (%s) ; la valeur par "
            "défaut d'AnyIO reste en vigueur.",
            exc,
        )
        return None

    target = recommended_thread_limit()
    previous = limiter.total_tokens
    if previous == target:
        return target

    limiter.total_tokens = target
    logger.info(
        "Pool de threads ajusté de %s à %s pour correspondre au pool de "
        "connexions : un thread démarré est ainsi certain d'obtenir une "
        "connexion plutôt que d'attendre pool_timeout.",
        previous,
        target,
    )
    return target
