# TchueKAM Backend - Diagramme d'Architecture Système Multi-Tenant

Diagramme d'architecture système Clean Architecture pour TchueKAM Enterprise SaaS.

```mermaid
graph TD
    Client[Clients Web / Mobile / API / SDK] -->|HTTP / HTTPS REST| Gateway[FastAPI API Router]
    Client -->|WebSocket| WSGateway[Real-Time Security & Notifications WS]

    subgraph Middleware & Sécurité
        AuthMiddleware[JWT Bearer Auth & JTI Blacklist]
        TenantContext[Tenant Isolation Middleware X-Org-Id / X-Ws-Id]
        RateLimiter[Token Bucket Anti-Brute Force]
    end

    Gateway --> AuthMiddleware
    AuthMiddleware --> TenantContext
    TenantContext --> RateLimiter

    subgraph Layer 1 : API Controllers (REST v1)
        AuthAPI[/api/v1/auth]
        OAuthAPI[/api/v1/oauth]
        UserAPI[/api/v1/users]
        RbacAPI[/api/v1/rbac]
        OrgAPI[/api/v1/organizations]
        WsAPI[/api/v1/workspaces]
        TeamAPI[/api/v1/teams]
        InvAPI[/api/v1/invitations]
        ProfAPI[/api/v1/profiles]
        KeyAPI[/api/v1/api-keys]
    end

    RateLimiter --> Layer1

    subgraph Layer 2 : Services Métier (Domain Business Logic)
        AuthService[AuthService]
        OAuthService[OAuthService]
        RbacService[RbacService]
        OrgService[OrganizationService]
        WorkspaceService[WorkspaceService]
        TeamService[TeamService]
        InvService[InvitationService]
        ProfileService[ProfileService]
    end

    Layer1 --> Layer2

    subgraph Layer 3 : Repositories (Accès aux Données & Abstractions)
        UserRepo[UserRepository]
        SessionRepo[SessionRepository]
        RbacRepo[RbacRepository]
        OrgRepo[OrganizationRepository]
        WsRepo[WorkspaceRepository]
        TeamRepo[TeamRepository]
        InvRepo[InvitationRepository]
        ApiKeyRepo[ApiKeyRepository]
    end

    Layer2 --> Layer3

    subgraph Layer 4 : Persistance (SQLAlchemy 2.0 ORM)
        Database[(SQLite Local / PostgreSQL Cluster)]
    end

    Layer3 --> Database
```
