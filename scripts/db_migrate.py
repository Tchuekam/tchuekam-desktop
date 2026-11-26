#!/usr/bin/env python
"""Applique les migrations Alembic, en sérialisant les instances concurrentes.

Pourquoi ce script plutôt que ``alembic upgrade head`` directement
-----------------------------------------------------------------
Les hébergeurs n'offrent pas tous une étape de pré-déploiement exécutée une
seule fois. Quand il n'y en a pas, la commande de démarrage de *chaque*
instance lance la migration, et deux instances qui démarrent ensemble
l'exécutent en parallèle.

PostgreSQL applique le DDL dans une transaction, ce qui rend cette course
« généralement » bénigne — la seconde instance attend puis constate qu'il n'y
a rien à faire. Mais « généralement » n'est pas une garantie : une migration
en plusieurs étapes, ou un backend qui ne gère pas le DDL transactionnel,
laisse une fenêtre où le schéma est à moitié appliqué. Ce script prend donc le
même verrou consultatif que le semis RBAC : une instance migre, les autres
attendent la fin avant de démarrer leur serveur.

Usage
-----
    python scripts/db_migrate.py              # upgrade head
    python scripts/db_migrate.py --revision -1  # downgrade d'une révision

Code de sortie non nul si la migration échoue, pour que la commande de
démarrage s'arrête avant de lancer un serveur sur un schéma incorrect.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [migrate] %(message)s",
)
logger = logging.getLogger("tchuekam.migrate")

#: Le verrou est tenu le temps de la migration. Une migration longue (index
#: sur une grosse table) peut dépasser largement les 30 s du semis RBAC, d'où
#: un délai d'attente bien plus généreux pour les instances en attente.
_LOCK_TIMEOUT_SECONDS = 600.0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--revision",
        default="head",
        help="Révision cible (défaut : head). Un préfixe '-' déclenche un downgrade.",
    )
    parser.add_argument(
        "--lock-timeout",
        type=float,
        default=_LOCK_TIMEOUT_SECONDS,
        help="Secondes d'attente du verrou avant abandon.",
    )
    args = parser.parse_args()

    from alembic import command
    from alembic.config import Config

    from tchuekam_backend.core import database

    if database._IS_SQLITE:
        logger.info(
            "Base SQLite détectée : migration appliquée sans verrou (un seul "
            "écrivain par définition)."
        )

    config = Config(str(REPO_ROOT / "alembic.ini"))

    with database.exclusive_startup_lock(timeout_seconds=args.lock_timeout) as holds_lock:
        if not holds_lock:
            # Une autre instance migre. Elle détient le verrou, donc elle est
            # vivante ; on la laisse finir et on démarre sur son schéma.
            current = database.current_schema_revision()
            logger.info(
                "Migration menée par une autre instance (révision actuelle : %s). "
                "Rien à faire ici.",
                current or "inconnue",
            )
            return 0

        before = database.current_schema_revision()
        target = args.revision
        try:
            if target.startswith("-"):
                logger.warning("Downgrade demandé vers %s.", target)
                command.downgrade(config, target)
            else:
                command.upgrade(config, target)
        except Exception as exc:
            logger.error("Migration échouée : %s", exc, exc_info=True)
            return 1

        after = database.current_schema_revision()
        if before == after:
            logger.info("Schéma déjà à jour (révision %s).", after)
        else:
            logger.info("Schéma migré : %s -> %s.", before or "vide", after)
    return 0


if __name__ == "__main__":
    sys.exit(main())
