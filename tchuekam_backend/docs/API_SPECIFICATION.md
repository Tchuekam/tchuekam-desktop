# TchueKAM Backend - Documentation Spécification API REST & WebSockets

Cette documentation résume l'ensemble des endpoints exposés par le module backend de TchueKAM (`tchuekam_backend`).

---

## Base URL & Swaggers
- **Base URL** : `/api/v1`
- **OpenAPI JSON** : `/api/v1/openapi.json`
- **Swagger UI** : `/docs`
- **ReDoc** : `/redoc`

---

## 1. Authentification & Jetons (`/api/v1/auth`)

| Méthode | Endpoint | Description | Auth requise |
| :--- | :--- | :--- | :--- |
| `POST` | `/auth/signup` | Inscription d'un nouvel utilisateur | Non |
| `POST` | `/auth/signin` | Connexion, vérification anti force-brute et émission JWT | Non |
| `POST` | `/auth/refresh` | Renouvellement de l'Access Token avec rotation du Refresh Token | Non |
| `POST` | `/auth/logout` | Déconnexion de la session courante et révocation du JWT | Oui (Bearer) |
| `POST` | `/auth/logout-all` | Déconnexion globale de toutes les sessions de l'utilisateur | Oui (Bearer) |
| `GET` | `/auth/verify-email` | Validation de l'adresse e-mail via jeton sécurisé | Non |
| `POST` | `/auth/forgot-password` | Demande de réinitialisation de mot de passe | Non |
| `POST` | `/auth/reset-password` | Réinitialisation du mot de passe via jeton sécurisé | Non |

---

## 2. Authentification OAuth & Logins Sociaux (`/api/v1/oauth`)

| Méthode | Endpoint | Description | Auth requise |
| :--- | :--- | :--- | :--- |
| `GET` | `/oauth/{provider}/authorize` | Obtenir l'URL de redirection vers le fournisseur social | Non |
| `POST` | `/oauth/{provider}/callback` | Callback OAuth, liaison automatique et émission des JWT | Non |

**Fournisseurs supportés** : `google`, `github`, `apple`, `microsoft`, `facebook` (extensible via `BaseOAuthProvider`).

---

## 3. Profils Utilisateurs et Appareils Connectés (`/api/v1/users`)

| Méthode | Endpoint | Description | Auth requise |
| :--- | :--- | :--- | :--- |
| `GET` | `/users/me` | Consulter le profil et les rôles de l'utilisateur connecté | Oui (Bearer) |
| `PUT` | `/users/me/profile` | Mettre à jour le profil (nom, téléphone, avatar, préférences) | Oui (Bearer) |
| `POST` | `/users/me/password` | Modifier son mot de passe | Oui (Bearer) |
| `GET` | `/users/me/devices` | Obtenir la liste des appareils et sessions actives | Oui (Bearer) |
| `DELETE` | `/users/me/devices/{session_id}` | Révoquer une session / appareil spécifique | Oui (Bearer) |

---

## 4. Contrôle d'Accès Dynamique RBAC (`/api/v1/rbac`)

| Méthode | Endpoint | Description | Permission Requise |
| :--- | :--- | :--- | :--- |
| `GET` | `/rbac/roles` | Lister tous les rôles et leurs permissions | `rbac.roles.READ` |
| `POST` | `/rbac/roles` | Créer un nouveau rôle personnalisé et lui associer des permissions | `rbac.roles.UPDATE` |
| `GET` | `/rbac/permissions` | Lister toutes les permissions granulaires de la plateforme | `rbac.roles.READ` |
| `POST` | `/rbac/permissions` | Créer une nouvelle permission de module/ressource | `rbac.roles.UPDATE` |
| `POST` | `/rbac/user-roles` | Attribuer dynamiquement un ensemble de rôles à un utilisateur | `rbac.roles.UPDATE` |

---

## 5. Journaux d'Audit & Sécurité (`/api/v1/audit`)

| Méthode | Endpoint | Description | Permission Requise |
| :--- | :--- | :--- | :--- |
| `GET` | `/audit/logs` | Consulter les événements d'audit et alertes de sécurité | `audit.logs.READ` |

---

## 6. WebSockets en Temps Réel (`/api/v1/ws`)

- **WS URL** : `/api/v1/ws/security-alerts/{user_id}`
- **Rôle** : Diffusion en direct des alertes de sécurité et notifications de révocation instantanée de session.
