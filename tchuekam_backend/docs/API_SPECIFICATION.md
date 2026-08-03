# TchueKAM Backend - Spécification et Documentation des APIs REST & WebSockets

Cette documentation présente l'ensemble de la spécification technique et la structure des endpoints exposés par l'infrastructure backend **TchueKAM** (`tchuekam_backend`).

---

## 🌐 Informations Générales & Swaggers

- **Base URL API v1** : `/api/v1`
- **Spécification OpenAPI (JSON)** : `/api/v1/openapi.json`
- **Documentation Interactive (Swagger UI)** : `/docs`
- **Documentation ReDoc** : `/redoc`

---

## 📐 Structure Standard des Réponses (Response Envelope)

Tous les endpoints retournent des réponses au format JSON structuré et prévisible.

### 1. Format de Succès
```json
{
  "success": true,
  "message": "Opération effectuée avec succès.",
  "data": {}
}
```

### 2. Format d'Erreur Centralisé
```json
{
  "success": false,
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Erreur de validation de la requête.",
    "details": [
      {
        "field": "email",
        "issue": "value is not a valid email address",
        "type": "value_error"
      }
    ]
  }
}
```

### 3. Format de Données Paginées
```json
{
  "items": [],
  "pagination": {
    "total": 120,
    "page": 1,
    "per_page": 20,
    "total_pages": 6
  }
}
```

---

## 🔐 Paramètres de Sécurité et En-têtes HTTP

Chaque réponse HTTP inclut automatiquement les en-têtes de sécurité enterprise :
- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
- `X-XSS-Protection: 1; mode=block`
- `Referrer-Policy: strict-origin-when-cross-origin`
- `Content-Security-Policy: default-src 'self'; script-src 'self'; object-src 'none';`

---

## 📑 Endpoints de l'API REST v1

### 1. Authentification & Jetons (`/api/v1/auth`)

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

### 2. Authentification OAuth & Logins Sociaux (`/api/v1/oauth`)

| Méthode | Endpoint | Description | Auth requise |
| :--- | :--- | :--- | :--- |
| `GET` | `/oauth/{provider}/authorize` | URL de redirection vers le fournisseur social | Non |
| `POST` | `/oauth/{provider}/callback` | Callback OAuth et création/liaison du compte | Non |

Fournisseurs : `google`, `github`, `apple`, `microsoft`, `facebook`.

### 3. Profils Utilisateurs et Appareils (`/api/v1/users`)

| Méthode | Endpoint | Description | Auth requise |
| :--- | :--- | :--- | :--- |
| `GET` | `/users/me` | Consulter le profil et les rôles de l'utilisateur | Oui (Bearer) |
| `PUT` | `/users/me/profile` | Mettre à jour le profil | Oui (Bearer) |
| `POST` | `/users/me/password` | Modifier le mot de passe | Oui (Bearer) |
| `GET` | `/users/me/devices` | Liste des sessions actives | Oui (Bearer) |
| `DELETE` | `/users/me/devices/{session_id}` | Révoquer une session spécifique | Oui (Bearer) |

### 4. Gestion des Fichiers Téléversés (`/api/v1/files`)

| Méthode | Endpoint | Description | Auth requise |
| :--- | :--- | :--- | :--- |
| `POST` | `/files/upload` | Téléverser un fichier sécurisé (10MB max, validation MIME & sanitization) | Oui (Bearer) |
| `GET` | `/files/{file_id}` | Obtenir les métadonnées d'un fichier | Oui (Bearer) |
| `GET` | `/files/{file_id}/download` | Télécharger un fichier téléversé | Oui (Bearer) |
| `DELETE` | `/files/{file_id}` | Supprimer définitivement un fichier | Oui (Bearer) |

### 5. Multi-Tenancy & Organisations (`/api/v1/organizations`)

| Méthode | Endpoint | Description | Auth requise |
| :--- | :--- | :--- | :--- |
| `POST` | `/organizations` | Créer une organisation multi-tenant | Oui (Bearer) |
| `GET` | `/organizations/my-organizations` | Obtenir les organisations de l'utilisateur (filtrage, tri, pagination) | Oui (Bearer) |
| `GET` | `/organizations/current` | Obtenir l'organisation active (`X-Organization-Id`) | Oui (Bearer + Tenant) |
| `PUT` | `/organizations/current` | Mettre à jour l'organisation | Oui (Bearer + Tenant) |
| `DELETE` | `/organizations/current` | Archiver l'organisation | Oui (Bearer + Tenant) |
| `GET` | `/organizations/current/members` | Lister les membres isolés du tenant | Oui (Bearer + Tenant) |

### 6. Workspaces & Équipes (`/api/v1/workspaces` & `/api/v1/teams`)

| Méthode | Endpoint | Description | Auth requise |
| :--- | :--- | :--- | :--- |
| `POST` | `/workspaces` | Créer un espace de travail dans l'organisation | Oui (Bearer + Tenant) |
| `GET` | `/workspaces` | Lister les espaces de travail de l'organisation | Oui (Bearer + Tenant) |
| `POST` | `/teams` | Créer une équipe | Oui (Bearer + Tenant) |
| `GET` | `/teams` | Lister les équipes | Oui (Bearer + Tenant) |
| `POST` | `/teams/{team_id}/members` | Ajouter un membre à l'équipe | Oui (Bearer + Tenant) |

### 7. RBAC & Attributions (`/api/v1/rbac`)

| Méthode | Endpoint | Description | Permission Requise |
| :--- | :--- | :--- | :--- |
| `GET` | `/rbac/roles` | Lister les rôles et permissions | `rbac.roles.READ` |
| `POST` | `/rbac/roles` | Créer un rôle personnalisé | `rbac.roles.UPDATE` |
| `GET` | `/rbac/permissions` | Lister toutes les permissions | `rbac.roles.READ` |
| `POST` | `/rbac/user-roles` | Attribuer des rôles à un utilisateur | `rbac.roles.UPDATE` |

### 8. Journaux d'Audit (`/api/v1/audit`)

| Méthode | Endpoint | Description | Permission Requise |
| :--- | :--- | :--- | :--- |
| `GET` | `/audit/logs` | Consulter les événements d'audit (pagination & recherche) | `audit.logs.READ` |

### 9. WebSockets (`/api/v1/ws`)

- **WS Endpoint** : `/api/v1/ws/security-alerts/{user_id}`
- **Usage** : Notifications en direct (révocations de sessions, alertes de sécurité).
