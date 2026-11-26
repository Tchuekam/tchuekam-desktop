"""
Point d'entrée principal de l'application FastAPI backend TchueKAM avec sécurité, middlewares et gestionnaire d'erreurs centralisé.
"""

import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

from tchuekam_backend.api.router import api_router
from tchuekam_backend.api.ws.notifications import ws_manager
from tchuekam_backend.core import metrics, redis_client
from tchuekam_backend.core.concurrency import apply_thread_limit
from tchuekam_backend.core.admission import ConcurrencyLimitMiddleware
from tchuekam_backend.core.config import _is_production, settings
from tchuekam_backend.core.database import (
    SessionLocal,
    check_connection,
    current_schema_revision,
    exclusive_startup_lock,
    init_db,
    pool_status,
)
from tchuekam_backend.core.exception_handlers import (
    app_exception_handler,
    global_exception_handler,
    http_exception_handler,
    password_hashing_busy_handler,
    validation_exception_handler,
)
from tchuekam_backend.core.exceptions import AppException
from tchuekam_backend.core.security import PasswordHashingBusy
from tchuekam_backend.core.logging_config import configure_logging
from tchuekam_backend.core.middleware import (
    ObservabilityMiddleware,
    RateLimitMiddleware,
    is_rate_limiting_enabled,
)
from tchuekam_backend.domain.schemas import APIResponse
from tchuekam_backend.services.rbac_service import RbacService

# Avant tout le reste : sans configuration, le logger racine n'a aucun handler
# et Python retombe sur ``lastResort``, qui ne laisse passer que WARNING et
# au-delà. Les logs d'accès, la posture de démarrage et les bascules en mode
# dégradé — tous émis en INFO — seraient perdus.
configure_logging()

logger = logging.getLogger("tchuekam_backend.main")

#: Mis à False lorsque l'arrêt commence, pour que ``/readyz`` échoue tout de
#: suite. Le répartiteur de charge retire alors l'instance de la rotation
#: pendant qu'elle termine les requêtes en vol, au lieu de continuer à lui en
#: envoyer de nouvelles qu'elle refusera.
_accepting_traffic = {"ready": False}


def _seed_rbac_once() -> None:
    """Sème rôles et permissions, une seule fois pour tous les workers.

    Le semis est un « chercher puis créer » : exécuté simultanément par N
    workers au démarrage, deux d'entre eux ne trouvent rien, tentent la
    création, et le second heurte la contrainte d'unicité sur ``roles.name``
    — ce qui fait échouer son démarrage. Le verrou sérialise la phase.
    """
    with exclusive_startup_lock() as holds_lock:
        if not holds_lock:
            logger.info("Semis RBAC effectué par un autre worker ; ignoré ici.")
            return
        db = SessionLocal()
        try:
            RbacService(db).seed_default_roles_and_permissions()
        finally:
            db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Aligne le pool de threads sur le pool de connexions. À faire en premier :
    # c'est ce qui décide si une surcharge se traduit par de la latence ou par
    # des erreurs 500 (voir core/concurrency.py).
    thread_limit = apply_thread_limit()

    # Lifecycle Startup: Initialisation DB et seeding RBAC
    #
    # Les deux étapes touchent la base et sont bloquantes : les exécuter dans
    # la boucle d'événements retarderait tout le démarrage du worker, et le
    # verrou consultatif peut attendre plusieurs secondes.
    await asyncio.to_thread(init_db)
    await asyncio.to_thread(_seed_rbac_once)

    # Diffusion WebSocket inter-workers. Sans cet abonnement, un worker ne
    # reçoit que les événements qu'il publie lui-même.
    await ws_manager.start_subscriber()

    # Start Telegram / Hermes Gateway only when explicitly opted in
    gateway_runner = None
    gateway_task = None
    if settings.TELEGRAM_BOT_TOKEN and os.getenv("TCHUEKAM_ENABLE_EMBEDDED_TELEGRAM", "").strip() == "1":
        try:
            from hermes_cli.env_loader import load_hermes_dotenv
            load_hermes_dotenv()
            from gateway.config import load_gateway_config
            from gateway.run import GatewayRunner
            gw_config = load_gateway_config()
            gateway_runner = GatewayRunner(config=gw_config)

            async def _start_gateway_async():
                try:
                    started = await gateway_runner.start()
                    if started:
                        logger.info("Telegram Bot Gateway (TchuekamCloudbot) connected and started successfully.")
                    else:
                        logger.warning("Telegram Bot Gateway failed to start during lifespan.")
                except Exception as ex:
                    logger.error(f"Error connecting Telegram Bot Gateway: {ex}", exc_info=True)

            gateway_task = asyncio.create_task(_start_gateway_async())
        except Exception as e:
            logger.error(f"Error initializing Telegram Bot Gateway in lifespan: {e}", exc_info=True)

    _log_startup_posture(thread_limit)
    _accepting_traffic["ready"] = True

    yield

    # Lifecycle Shutdown
    _accepting_traffic["ready"] = False

    await ws_manager.stop_subscriber()

    if gateway_task is not None and not gateway_task.done():
        gateway_task.cancel()

    if gateway_runner:
        try:
            await gateway_runner.stop()
            logger.info("Telegram Bot Gateway stopped cleanly.")
        except Exception as e:
            logger.error(f"Error stopping Telegram Bot Gateway: {e}")


def _log_startup_posture(thread_limit) -> None:
    """Journalise la configuration qui décide du comportement sous charge.

    Ces quatre points expliquent la quasi-totalité des incidents de montée en
    charge, et ils sont invisibles depuis l'extérieur du processus. Les voir
    dans les logs de démarrage évite d'avoir à deviner après coup pourquoi un
    quota était dix fois trop permissif ou pourquoi une révocation n'a pas
    pris.
    """
    shared_state = redis_client.is_configured() and redis_client.get_sync_client() is not None
    if _is_production() and not shared_state:
        # Un déploiement multi-workers sans Redis applique N fois le quota,
        # perd les révocations immédiates et ne diffuse pas les événements
        # WebSocket. Ce n'est pas fatal, mais cela doit être un choix conscient.
        logger.warning(
            "Aucun backplane Redis configuré en production : quotas de débit, "
            "révocation de jetons et diffusion WebSocket restent locaux à "
            "chaque worker. Définissez REDIS_URL pour un comportement correct "
            "en multi-workers."
        )

    logger.info(
        "Démarrage %s v%s | env=%s | schéma=%s | threads=%s | pool=%s | "
        "redis=%s | quota_global=%s",
        settings.PROJECT_NAME,
        settings.VERSION,
        settings.ENVIRONMENT,
        current_schema_revision() or "non migré",
        thread_limit,
        pool_status(),
        "partagé" if shared_state else "local au processus",
        f"{settings.RATE_LIMIT_GLOBAL_PER_MINUTE}/min" if is_rate_limiting_enabled() else "désactivé",
    )


_enable_docs = (not _is_production()) or os.getenv("ENABLE_API_DOCS", "").strip() == "1"

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Backend API REST Enterprise pour TchueKAM SaaS Multi-Tenant.",
    version=settings.VERSION,
    openapi_url=f"{settings.API_V1_STR}/openapi.json" if _enable_docs else None,
    docs_url="/docs" if _enable_docs else None,
    redoc_url="/redoc" if _enable_docs else None,
    lifespan=lifespan,
)

# Ordre des middlewares : Starlette les applique en pile inversée, donc le
# dernier ajouté est le plus extérieur et voit la requête en premier.
#
#   ObservabilityMiddleware     <- extérieur : pose l'identifiant de requête
#                                  et mesure la latence totale, refus compris
#   RateLimitMiddleware            quota par client
#   ConcurrencyLimitMiddleware     borne la concurrence, 503 au-delà
#   CORSMiddleware                 répond aux pré-vols
#   GZipMiddleware              <- intérieur : compresse la réponse applicative
#
# Le limiteur doit être *au-dessus* de CORS et de GZip : un refus ne doit ni
# être compressé ni consommer de travail applicatif. L'observabilité doit être
# au-dessus du limiteur, sinon les requêtes refusées n'apparaissent ni dans
# les métriques ni dans les logs — exactement celles qu'on veut voir.

# 1. GZip Compression Middleware (Minimum response size 1000 bytes)
app.add_middleware(GZipMiddleware, minimum_size=1000)

# 2. Configuration CORS
_cors_origins = list(settings.ALLOWED_ORIGINS)
_cors_allow_credentials = "*" not in _cors_origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=_cors_allow_credentials,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=[
        "Authorization",
        "Content-Type",
        "X-Organization-Id",
        "X-Hermes-Session-Token",
        "X-Requested-With",
        "X-Request-Id",
    ],
    expose_headers=[
        # Sans exposition explicite, un client navigateur ne peut lire aucun
        # de ces en-têtes : il ne saurait ni corréler un incident par
        # identifiant de requête, ni savoir combien de quota il lui reste.
        "X-Request-Id",
        "RateLimit-Limit",
        "RateLimit-Remaining",
        "RateLimit-Reset",
        "Retry-After",
    ],
)

# 3. Contrôle d'admission : borne la concurrence et refuse vite le surplus.
#
# Placé sous le limiteur de débit : le quota par client filtre d'abord l'abus
# d'un appelant unique, puis l'admission protège le service contre une charge
# légitime mais supérieure à sa capacité. L'inverse ferait consommer une place
# d'admission à une requête qui va de toute façon être refusée pour quota.
app.add_middleware(ConcurrencyLimitMiddleware)

# 4. Limitation de débit globale
app.add_middleware(RateLimitMiddleware)

# 5. Observabilité (identifiant de requête, log d'accès, métriques) et
#    en-têtes HTTP de sécurité
app.add_middleware(ObservabilityMiddleware)

# Exception Handlers Centralisés
#
# PasswordHashingBusy avant le gestionnaire générique : sans cette entrée, la
# saturation du hachage remonterait en 500, ce qui la ferait passer pour une
# panne dans les tableaux de bord d'erreurs alors que c'est une protection qui
# fonctionne.
app.add_exception_handler(PasswordHashingBusy, password_hashing_busy_handler)
app.add_exception_handler(AppException, app_exception_handler)
app.add_exception_handler(StarletteHTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(Exception, global_exception_handler)

# Inclusion des routes API REST v1
app.include_router(api_router, prefix=settings.API_V1_STR)


@app.get("/health", tags=["Health"], response_model=APIResponse[dict])
@app.get(f"{settings.API_V1_STR}/health", tags=["Health"], response_model=APIResponse[dict])
def health_check():
    """Endpoint de contrôle de santé (Health Check)."""
    return APIResponse(
        message="Service opérationnel.",
        data={
            "status": "healthy",
            "service": settings.PROJECT_NAME,
            "version": settings.VERSION,
            "environment": settings.ENVIRONMENT,
        },
    )


@app.get("/livez", tags=["Health"], include_in_schema=False)
def liveness_probe():
    """Sonde de vivacité : le processus répond-il encore ?

    Distincte de ``/readyz`` à dessein. Une sonde de vivacité qui vérifierait
    la base ferait redémarrer tous les workers lors d'un incident côté base de
    données — un redémarrage ne répare rien et le martèlement de reconnexions
    aggrave la panne. Celle-ci ne teste que la boucle d'événements.
    """
    return {"status": "alive"}


@app.get("/readyz", tags=["Health"], include_in_schema=False)
def readiness_probe(response: Response):
    """Sonde de disponibilité : cette instance peut-elle servir du trafic ?

    Renvoie 503 pendant le démarrage, pendant l'arrêt, et si la base est
    injoignable — dans ces trois cas le répartiteur doit router ailleurs.
    Redis indisponible n'est pas un motif de retrait : le service fonctionne
    en mode dégradé (quotas locaux au processus) et retirer toutes les
    instances pour cela transformerait une dégradation en panne totale.
    """
    database_ok = check_connection()
    redis_state = redis_client.health()
    ready = _accepting_traffic["ready"] and database_ok

    if not ready:
        response.status_code = 503

    return {
        "status": "ready" if ready else "not_ready",
        "accepting_traffic": _accepting_traffic["ready"],
        "database": "up" if database_ok else "down",
        "schema_revision": current_schema_revision(),
        "redis": redis_state,
        "db_pool": pool_status(),
        "degraded": bool(redis_state.get("degraded")),
    }


@app.get("/metrics", tags=["Health"], include_in_schema=False)
def prometheus_metrics():
    """Exposition Prometheus.

    Non authentifiée mais sans donnée métier : seuls des compteurs agrégés et
    des gabarits de route y figurent. Les déploiements qui ne veulent pas
    l'exposer publiquement la bloquent au niveau du proxy, ou la désactivent
    avec ``TCHUEKAM_METRICS_ENABLED=0``.
    """
    if os.getenv("TCHUEKAM_METRICS_ENABLED", "").strip().lower() in {"0", "false", "no"}:
        return Response(status_code=404)
    if not metrics.is_available():
        return Response(
            content="# prometheus_client n'est pas installé\n",
            media_type="text/plain; charset=utf-8",
        )
    payload, content_type = metrics.render_latest()
    return Response(content=payload, media_type=content_type)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("tchuekam_backend.main:app", host="0.0.0.0", port=8000, reload=True)
