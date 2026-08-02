# TchueKAM Enterprise SaaS Backend (tchuekam.com)

Infrastructure Backend Haute Sécurité, Multi-Tenant, Évolutive et Prête pour la Montée en Charge Mondiale.

---

## 🚀 Présentation du Projet

L'infrastructure backend `tchuekam_backend` est la plateforme centrale de **[TchueKAM](https://tchuekam.com)**. Elle respecte l'architecture en couches **Clean Architecture** et garantit la conformité aux meilleures pratiques de l'industrie (SOLID, DRY, KISS, Isolation stricte des données).

### Démonstrateur et Domaine Officiel
- **Domaine principal** : `https://tchuekam.com`
- **API Server** : `https://api.tchuekam.com/api/v1`
- **Documentation OpenAPI / Swagger** : `https://api.tchuekam.com/docs`

---

## 🏛️ Architecture Système & Principes de Conception

```text
tchuekam_backend/
├── core/                  # Sécurité, JWT, Hashing PBKDF2/Argon2, Tenant Context, Rate Limiting, Audit
├── domain/                # Modèles ORM (16 Tables SQLAlchemy 2.0) et DTOs Pydantic V2
├── repositories/          # Abstraction de la couche d'accès aux données (11 Repositories)
├── services/              # Logique métier distribuée (10 Services de domaine)
├── api/                   # Routeurs FastAPI REST v1 et Gateways WebSockets
├── docs/                  # Documentation technique (ERD, Architecture, OpenAPI, Validation, Déploiement)
└── tests/                 # Suite de 18 tests d'intégration et End-to-End (100% de réussite)
```

---

## 🔑 Fonctionnalités Implémentées

### Module 1 — Authentification, JWT, OAuth2 & RBAC Dynamique
1. **Authentification & Session Management** :
   - Inscription (`Sign Up`), Connexion (`Sign In`), Validation d'adresse e-mail et réinitialisation sécurisée du mot de passe.
   - Jetons JWT avec rotation automatique des *Refresh Tokens*.
   - Liste noire des jetons révoqués (`JTI Blacklist`) et déconnexion multi-appareils.
2. **Fournisseurs OAuth2 Extensibles** :
   - Intégration modulaire pour Google, GitHub, Apple, Microsoft et Facebook.
3. **Moteur RBAC Dynamique Piloté par la Base de Données** :
   - Évaluation granulaire `(module, ressource, action)`.
   - Seeding automatique des 7 rôles système (*Super Admin*, *Admin*, *Team Owner*, *Manager*, *Developer*, *Support*, *User*).

### Module 2 — Multi-Tenancy, Organisations, Workspaces, Équipes & Collaboration
1. **Organisations Multi-Tenant** :
   - Isolation stricte des données inter-organisations via le header `X-Organization-Id`.
   - Slugs uniques, logos, domaines personnalisés, archivage et restauration d'organisations.
2. **Workspaces & Isolation Spatiale** :
   - Espaces de travail isolés par organisation (style Notion/GitHub), paramétrables via `X-Workspace-Id`.
3. **Équipes & Arborescence Hiérarchique** :
   - Hiérarchie d'équipes (`parent_team_id`), responsable d'équipe (*Leader*) et gestion des membres.
4. **Onboarding & Invitations** :
   - Jetons d'invitation temporaires et hachés, envoi par e-mail et acceptation avec attribution automatique de rôles.
5. **Profils Étendus & Clés API** :
   - Préférences utilisateur (langue, fuseau horaire, thème).
   - Génération de clés API hachées SHA256 avec préfixe visible `tk_live_...`.
6. **Sécurité, Audit & Temps Réel** :
   - Token Bucket / Sliding Window Rate Limiter anti force-brute.
   - Logs d'audit JSON structurés.
   - Gateway WebSockets pour les notifications en temps réel.

---

## 📊 Modèle de Données Relational (16 Tables)

Le schéma relationnel est modélisé dans [ERD_DIAGRAM.md](docs/ERD_DIAGRAM.md) :
1. `users` & `profiles`
2. `sessions` & `oauth_accounts`
3. `roles`, `permissions`, `role_permissions`, `user_roles`
4. `organizations` & `organization_memberships`
5. `workspaces` & `workspace_memberships`
6. `teams` & `team_members`
7. `invitations`, `api_keys`, `audit_logs`

---

## 🧪 Tests Automatisés & Validation (100% Passed)

L'ensemble du backend est couvert par 18 tests automatisés (`pytest tchuekam_backend/tests -v`) :
- Auth & Refresh Tokens
- OAuth2 Providers
- RBAC & Permissions
- Multi-Tenant Strict Isolation
- Organisations, Workspaces, Teams, Invitations
- Profils & Clés API
- End-to-End (E2E) Workflow complet

```text
============================= 18 passed in 9.12s ==============================
```

---

## 📄 Documentation Complémentaire

- [Diagramme Entité-Association (Mermaid ERD)](docs/ERD_DIAGRAM.md)
- [Diagramme d'Architecture Système](docs/ARCHITECTURE_DIAGRAM.md)
- [Spécification API & Endpoints](docs/API_SPECIFICATION.md)
- [Schéma Détaillé de la Base de Données](docs/DATABASE_SCHEMA.md)
- [Guide de Déploiement Production](docs/DEPLOYMENT.md)
- [Rapport de Validation & Assurance Qualité](docs/VALIDATION_REPORT.md)
