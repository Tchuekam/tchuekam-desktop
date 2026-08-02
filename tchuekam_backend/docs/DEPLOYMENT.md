# TchueKAM Backend - Guide de Déploiement et Sécurité en Production

Ce document fournit la procédure étape par étape pour déployer le backend TchueKAM sur une infrastructure Cloud / Kubernetes / Serverless.

---

## 1. Prérequis & Variables d'Environnement

Définir les variables de production sécurisées dans votre gestionnaire de secrets (AWS Secrets Manager, GCP Secret Manager, Vault) :

```bash
# Configuration Base de données PostgreSQL distribuée
export TCHUEKAM_DATABASE_URL="postgresql+psycopg2://tchuekam_admin:StrongProdSecret@db.tchuekam.com:5432/tchuekam_prod"

# Clé Secrète JWT (générer 64 octets hexades via `openssl rand -hex 64`)
export TCHUEKAM_JWT_SECRET_KEY="c839a04f98129801..."

# Paramètres des jetons JWT
export ACCESS_TOKEN_EXPIRE_MINUTES=15
export REFRESH_TOKEN_EXPIRE_DAYS=7

# Identifiants OAuth Production
export GOOGLE_CLIENT_ID="prod_google_client_id"
export GOOGLE_CLIENT_SECRET="prod_google_client_secret"
export GITHUB_CLIENT_ID="prod_github_client_id"
export GITHUB_CLIENT_SECRET="prod_github_client_secret"
```

---

## 2. Déploiement via Uvicorn & Gunicorn

Lancement avec 4 workers asynchrones derrière un reverse-proxy Nginx / Traefik :

```bash
gunicorn tchuekam_backend.main:app \
    --workers 4 \
    --worker-class uvicorn.workers.UvicornWorker \
    --bind 0.0.0.0:8000 \
    --access-logfile - \
    --error-logfile -
```

---

## 3. Configuration Nginx Reverse Proxy (SSL / TLS & WebSockets)

```nginx
server {
    listen 443 ssl http2;
    server_name api.tchuekam.com;

    ssl_certificate /etc/letsencrypt/live/api.tchuekam.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/api.tchuekam.com/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Prise en charge des WebSockets
    location /api/v1/ws/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "Upgrade";
        proxy_set_header Host $host;
    }
}
```

---

## 4. Exécution de la Suite de Tests Automatisée

```bash
pytest tchuekam_backend/tests -v --cov=tchuekam_backend
```
