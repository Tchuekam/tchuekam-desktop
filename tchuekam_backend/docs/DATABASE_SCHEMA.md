# TchueKAM Backend - Schéma de Base de Données Relational & RBAC

Ce document détaille le modèle Entité-Association (ERD) et les tables de la base de données relationnelle TchueKAM.

---

## Tables de Données et Identité

### 1. `users`
- `id` (UUID PK)
- `email` (String, Unique, Index)
- `password_hash` (String, Nullable pour OAuth)
- `is_active` (Boolean)
- `is_verified` (Boolean)
- `created_at` (Timestamp)
- `updated_at` (Timestamp)

### 2. `profiles`
- `id` (UUID PK)
- `user_id` (UUID FK -> users.id, Unique, Cascade Delete)
- `full_name` (String, Nullable)
- `avatar_url` (String, Nullable)
- `phone_number` (String, Nullable)
- `preferences_json` (Text)
- `created_at` (Timestamp)
- `updated_at` (Timestamp)

### 3. `sessions`
- `id` (UUID PK)
- `user_id` (UUID FK -> users.id, Cascade Delete, Index)
- `refresh_token_hash` (String, Index)
- `device_name` (String)
- `device_type` (String)
- `ip_address` (String)
- `user_agent` (Text)
- `is_revoked` (Boolean, Index)
- `expires_at` (Timestamp)
- `created_at` (Timestamp)
- `last_active_at` (Timestamp)

### 4. `oauth_accounts`
- `id` (UUID PK)
- `user_id` (UUID FK -> users.id, Cascade Delete, Index)
- `provider` (String: google, github, apple, microsoft, facebook)
- `provider_user_id` (String)
- `email` (String, Nullable)
- `access_token` (Text, Nullable)
- `created_at` (Timestamp)
- *Constraint*: Unique(provider, provider_user_id)

---

## Dynamic RBAC Engine

### 5. `roles`
- `id` (UUID PK)
- `name` (String, Unique, Index)
- `description` (String)
- `is_system_role` (Boolean)
- `created_at` (Timestamp)

### 6. `permissions`
- `id` (UUID PK)
- `name` (String, Unique, Index)
- `module` (String, Index)
- `resource` (String, Index)
- `action` (String: CREATE, READ, UPDATE, DELETE, EXECUTE)
- `description` (String)

### 7. `role_permissions`
- `id` (UUID PK)
- `role_id` (UUID FK -> roles.id, Cascade Delete)
- `permission_id` (UUID FK -> permissions.id, Cascade Delete)
- *Constraint*: Unique(role_id, permission_id)

### 8. `user_roles`
- `id` (UUID PK)
- `user_id` (UUID FK -> users.id, Cascade Delete)
- `role_id` (UUID FK -> roles.id, Cascade Delete)
- *Constraint*: Unique(user_id, role_id)

---

## Jetons Temporaires & Audit

### 9. `password_reset_tokens`
- `id` (UUID PK)
- `user_id` (UUID FK -> users.id, Cascade Delete, Index)
- `token_hash` (String, Index)
- `expires_at` (Timestamp)
- `is_used` (Boolean)
- `created_at` (Timestamp)

### 10. `email_verification_tokens`
- `id` (UUID PK)
- `user_id` (UUID FK -> users.id, Cascade Delete, Index)
- `token_hash` (String, Index)
- `expires_at` (Timestamp)
- `is_used` (Boolean)
- `created_at` (Timestamp)

### 11. `audit_logs`
- `id` (UUID PK)
- `user_id` (UUID, Index, Nullable)
- `action` (String, Index)
- `resource` (String, Nullable)
- `details_json` (Text)
- `ip_address` (String)
- `user_agent` (Text)
- `created_at` (Timestamp, Index)
