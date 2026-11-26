"""Environnement Alembic du backend TchueKAM.

L'URL de connexion n'est pas lue dans ``alembic.ini`` mais dérivée de la même
configuration que l'application (``core.database``). Deux sources de vérité
pour l'adresse de la base finiraient par divergerger, et une migration
appliquée à la mauvaise base est irréversible.
"""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context

# ``core.database`` normalise l'URL (``postgres://`` → ``postgresql+<pilote>://``)
# et construit déjà un moteur correctement configuré : on le réutilise tel quel.
from tchuekam_backend.core.database import Base, engine

# ``domain.models`` doit être importé pour que chaque table soit enregistrée
# dans ``Base.metadata`` ; sans cet import, ``--autogenerate`` croit que le
# schéma est vide et génère une migration qui supprime tout.
import tchuekam_backend.domain.models  # noqa: F401

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Génère le SQL sans se connecter (``alembic upgrade head --sql``).

    Utile quand les migrations sont appliquées par une équipe qui exige de
    relire le SQL avant exécution.
    """
    context.configure(
        url=engine.url.render_as_string(hide_password=False),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Applique les migrations sur une connexion réelle."""
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            # Sans ``compare_type``, une colonne dont le type change ne
            # produit aucune opération et la dérive passe inaperçue.
            compare_type=True,
            compare_server_default=True,
            # SQLite ne sait pas modifier une colonne en place ; le mode
            # « batch » reconstruit la table. Nécessaire pour que les
            # migrations restent exécutables sur la base de développement.
            render_as_batch=connection.dialect.name == "sqlite",
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
