#!/usr/bin/env python
"""Échoue si une requête du chemin critique perd son index.

Pourquoi en CI
--------------
Un index manquant est invisible sur une petite table : le planificateur
choisit un parcours séquentiel, qui est le bon plan sur dix lignes et coûte
quelques microsecondes. Les tests passent, la revue ne voit rien, et le défaut
n'apparaît qu'en production, une fois la table peuplée — en général sous forme
de latence qui grimpe lentement puis d'une saturation du pool de connexions.

Ce contrôle sème un jeu de données de taille non triviale, lit le plan réel de
chaque requête du chemin critique, et échoue sur tout parcours séquentiel
d'une table assez grande pour que cela compte. C'est la classe de régression
qu'on ne trouve autrement qu'en incident.

Il réutilise le volet ``database`` de ``scripts/benchmark.py``, pour qu'il n'y
ait qu'une seule définition de « requête du chemin critique » à maintenir.

Usage
-----
    TCHUEKAM_DATABASE_URL=postgres://... python scripts/check_query_plans.py
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
for candidate in (REPO_ROOT, REPO_ROOT / "scripts"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

#: Volume semé. Il doit dépasser le seuil au-delà duquel un parcours
#: séquentiel cesse d'être le plan optimal (voir ``_SEQ_SCAN_ROW_THRESHOLD``
#: dans benchmark.py), sinon le contrôle ne peut rien détecter : chaque plan
#: serait légitimement un parcours séquentiel.
_SEED_USERS = 1_200
_SEED_AUDIT = 5_000


def seed_minimum() -> None:
    """Sème juste assez de lignes pour que les plans soient représentatifs."""
    import json
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import text

    from tchuekam_backend.core.database import engine, new_session
    from tchuekam_backend.domain.models import (
        AuditLog,
        Organization,
        OrganizationMembership,
        Role,
        User,
        UserRole,
        UserSession,
    )
    from tchuekam_backend.services.rbac_service import RbacService

    db = new_session()
    try:
        RbacService(db).seed_default_roles_and_permissions()
        role = db.query(Role).filter(Role.name == "Support").first()

        existing = db.query(User).filter(User.email.like("planprobe-%@probe.local")).count()
        now = datetime.now(timezone.utc)

        if existing < _SEED_USERS:
            fresh = []
            for i in range(existing, _SEED_USERS):
                user = User(
                    email=f"planprobe-{i}@probe.local",
                    password_hash="x",
                    is_active=True,
                    is_verified=True,
                )
                fresh.append(user)
                db.add(user)
            db.flush()
            for user in fresh:
                if role is not None:
                    db.add(UserRole(user_id=user.id, role_id=role.id))
                db.add(UserSession(
                    user_id=user.id,
                    refresh_token_hash=f"probe-{user.id}",
                    device_name="probe",
                    expires_at=now + timedelta(days=7),
                    is_revoked=False,
                ))
            db.commit()

        # Les adhésions doivent être semées elles aussi : sur une table vide
        # le planificateur parcourt séquentiellement — à raison — et la
        # requête correspondante échapperait au contrôle. Une table non semée
        # est un angle mort, pas un succès.
        if db.query(OrganizationMembership).count() < _SEED_USERS:
            org = db.query(Organization).filter(Organization.slug == "plan-probe").first()
            if org is None:
                org = Organization(name="Plan Probe", slug="plan-probe")
                db.add(org)
                db.flush()
            probes = db.query(User).filter(User.email.like("planprobe-%@probe.local")).all()
            for user in probes:
                db.add(OrganizationMembership(
                    org_id=org.id, user_id=user.id, role="MEMBER", status="ACTIVE",
                ))
            db.commit()

        if db.query(AuditLog).count() < _SEED_AUDIT:
            batch = []
            for i in range(_SEED_AUDIT):
                batch.append(AuditLog(
                    action="PLAN_PROBE",
                    resource=f"r-{i}",
                    details_json=json.dumps({}),
                    created_at=now - timedelta(minutes=i),
                ))
            db.bulk_save_objects(batch)
            db.commit()
    finally:
        db.close()

    # Sans ANALYZE, le planificateur travaille sur des statistiques absentes
    # ou périmées et peut choisir un plan qui n'a rien à voir avec celui qu'il
    # choisirait en production.
    with engine.connect() as conn:
        conn.execute(text("ANALYZE"))
        conn.commit()


def main() -> int:
    from tchuekam_backend.core.database import _IS_SQLITE

    if _IS_SQLITE:
        print("Ignoré : EXPLAIN ANALYZE requiert PostgreSQL.")
        return 0

    import benchmark

    print(f"Semis minimal ({_SEED_USERS} utilisateurs, {_SEED_AUDIT} journaux)...")
    seed_minimum()

    report = benchmark.suite_database()
    if "skipped" in report:
        print(f"Ignoré : {report['skipped']}")
        return 0

    print("\nTailles de tables :", report["table_sizes"])
    print(f"\n{'requête du chemin critique':44s} {'ms':>9s}  index")
    for query in report["hot_queries"]:
        if "error" in query:
            print(f"{query['query']:44s} {'ERREUR':>9s}  {query['error']}")
            continue
        print(
            f"{query['query']:44s} {query['execution_ms'] or 0:9.3f}  "
            f"{'oui' if query['uses_index'] else 'NON'}"
        )

    failures = report["needs_an_index"]
    if failures:
        print("\nÉCHEC — parcours séquentiel sur une table de taille non triviale :",
              file=sys.stderr)
        for item in failures:
            print(f"  - {item['query']} parcourt {', '.join(item['tables'])}", file=sys.stderr)
        print(
            "\nAjoutez l'index correspondant. Ces requêtes sont exécutées à "
            "chaque requête HTTP authentifiée : leur coût croît avec la table, "
            "donc le défaut tient en test et s'effondre en production.",
            file=sys.stderr,
        )
        return 1

    print("\nOK : chaque requête du chemin critique est servie par un index.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
