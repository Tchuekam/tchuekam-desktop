# TchueKAM Backend - Diagramme Entité-Association (ERD Diagram)

Diagramme Mermaid complet modélisant les 16 tables relationnelles du système d'Information TchueKAM (Authentification, RBAC, Organisations, Workspaces, Équipes, Invitations et Clés API).

```mermaid
erDiagram
    users ||--o| profiles : "possède"
    users ||--o{ sessions : "ouvre"
    users ||--o{ oauth_accounts : "lie"
    users ||--o{ user_roles : "reçoit"
    users ||--o{ organization_memberships : "appartient à"
    users ||--o{ workspace_memberships : "accède à"
    users ||--o{ team_members : "fait partie de"
    users ||--o{ api_keys : "génère"

    organizations ||--o{ organization_memberships : "contient"
    organizations ||--o{ workspaces : "abrite"
    organizations ||--o{ teams : "regroupe"
    organizations ||--o{ invitations : "émet"
    organizations ||--o{ api_keys : "possède"

    workspaces ||--o{ workspace_memberships : "contient"
    workspaces ||--o{ teams : "associe"
    workspaces ||--o{ invitations : "scie"

    teams ||--o{ team_members : "inclut"
    teams ||--o{ teams : "équipe parente"

    roles ||--o{ role_permissions : "détient"
    permissions ||--o{ role_permissions : "est attribué"
    roles ||--o{ user_roles : "est assigné"

    users {
        string id PK
        string email
        string password_hash
        boolean is_active
        boolean is_verified
        timestamp created_at
    }

    profiles {
        string id PK
        string user_id FK
        string username
        string full_name
        string avatar_url
        string language
        string timezone
    }

    organizations {
        string id PK
        string name
        string slug
        string logo_url
        string custom_domain
        string billing_plan
        boolean is_archived
    }

    workspaces {
        string id PK
        string org_id FK
        string name
        string slug
        boolean is_archived
    }

    teams {
        string id PK
        string org_id FK
        string workspace_id FK
        string parent_team_id FK
        string name
        string leader_id FK
    }

    invitations {
        string id PK
        string org_id FK
        string email
        string role
        string status
        timestamp expires_at
    }

    api_keys {
        string id PK
        string org_id FK
        string user_id FK
        string name
        string prefix
        string key_hash
    }
```
