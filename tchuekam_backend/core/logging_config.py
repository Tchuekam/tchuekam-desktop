"""Configuration de la journalisation du backend.

Pourquoi ce module est nécessaire
---------------------------------
L'application n'appelait ``logging.basicConfig()`` nulle part. Sans
configuration, le logger racine de Python n'a aucun handler et retombe sur
``logging.lastResort``, qui écrit sur ``stderr`` *à partir du niveau
WARNING*, sans horodatage ni nom de logger.

Conséquence en production : tout ce qui est émis en INFO disparaissait — les
logs d'accès, la ligne de posture au démarrage, la révision de schéma
appliquée, la bascule de Redis en mode dégradé. Il ne restait que des
avertissements et des traces d'exception sans date ni contexte. Autrement dit,
l'observabilité construite ailleurs dans ce paquet n'arrivait pas jusqu'aux
journaux de l'hébergeur.

Format
------
* **Production** : une ligne JSON par enregistrement. C'est ce que consomment
  les collecteurs (Loki, CloudWatch, Datadog) sans motif d'extraction à
  maintenir. L'identifiant de requête y est injecté automatiquement, donc une
  erreur signalée par un utilisateur se relie à ses lignes de log serveur.
* **Développement** : une ligne lisible à l'œil, plus utile dans un terminal.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from typing import Any, Dict

from tchuekam_backend.core.config import _is_production
from tchuekam_backend.core.request_context import get_request_id

#: Attributs standard de ``LogRecord``. Tout le reste a été passé via
#: ``extra=`` par l'appelant et mérite d'apparaître dans la sortie JSON.
_STANDARD_RECORD_FIELDS = frozenset(
    {
        "args", "asctime", "created", "exc_info", "exc_text", "filename",
        "funcName", "levelname", "levelno", "lineno", "module", "msecs",
        "message", "msg", "name", "pathname", "process", "processName",
        "relativeCreated", "stack_info", "thread", "threadName",
        "taskName",
    }
)


class JsonFormatter(logging.Formatter):
    """Rend chaque enregistrement comme un unique objet JSON sur une ligne."""

    def format(self, record: logging.LogRecord) -> str:
        payload: Dict[str, Any] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
        }

        message = record.getMessage()
        # Les middlewares émettent déjà du JSON (log d'accès, refus de quota).
        # On le réinjecte comme objet plutôt que comme chaîne échappée, sinon
        # ses champs ne sont pas interrogeables côté collecteur.
        if message.startswith("{") and message.endswith("}"):
            try:
                payload.update(json.loads(message))
            except ValueError:
                payload["message"] = message
        else:
            payload["message"] = message

        request_id = get_request_id()
        if request_id:
            payload.setdefault("request_id", request_id)

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        if record.stack_info:
            payload["stack"] = self.formatStack(record.stack_info)

        for key, value in record.__dict__.items():
            if key not in _STANDARD_RECORD_FIELDS and not key.startswith("_"):
                payload.setdefault(key, value)

        return json.dumps(payload, separators=(",", ":"), default=str, ensure_ascii=False)


class HumanFormatter(logging.Formatter):
    """Format lisible, avec l'identifiant de requête quand il y en a un."""

    def __init__(self) -> None:
        super().__init__(
            fmt="%(asctime)s %(levelname)-7s %(name)-32s %(message)s",
            datefmt="%H:%M:%S",
        )

    def format(self, record: logging.LogRecord) -> str:
        rendered = super().format(record)
        request_id = get_request_id()
        if request_id:
            rendered = f"{rendered}  [req={request_id[:12]}]"
        return rendered


def log_level() -> int:
    raw = os.getenv("TCHUEKAM_LOG_LEVEL", "").strip().upper()
    if raw:
        resolved = logging.getLevelNamesMapping().get(raw)
        if resolved is not None:
            return resolved
    return logging.INFO


#: Évite de poser deux fois les handlers. ``configure_logging`` est appelé à
#: l'import de ``main``, qui peut être importé plusieurs fois (tests, workers,
#: rechargement) ; sans garde, chaque ligne serait dupliquée autant de fois.
_configured = False


def configure_logging(force: bool = False) -> None:
    """Installe le handler racine. Idempotent."""
    global _configured
    if _configured and not force:
        return

    formatter: logging.Formatter = JsonFormatter() if _is_production() else HumanFormatter()

    # stdout et non stderr : les collecteurs des hébergeurs lisent les deux,
    # mais garder stderr pour les seules anomalies permet de repérer un
    # plantage de démarrage sans le noyer dans le trafic nominal.
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    # On retire les handlers déjà posés (dont ``lastResort`` et ceux qu'une
    # bibliothèque importée aurait installés) pour ne pas écrire deux fois.
    for existing in list(root.handlers):
        root.removeHandler(existing)
    root.addHandler(handler)
    root.setLevel(log_level())

    # uvicorn installe ses propres handlers sur ``uvicorn``, ``uvicorn.error``
    # et ``uvicorn.access``. Sans ``propagate = False`` *et* retrait de leurs
    # handlers, chaque ligne apparaîtrait deux fois : une au format uvicorn,
    # une au nôtre.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access", "gunicorn.error", "gunicorn.access"):
        lib_logger = logging.getLogger(name)
        lib_logger.handlers.clear()
        lib_logger.propagate = True

    # L'access log d'uvicorn est redondant avec ``ObservabilityMiddleware``,
    # qui mesure la même requête avec l'identifiant de corrélation en plus.
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

    # SQLAlchemy en INFO imprime chaque requête SQL et ses paramètres : du
    # bruit en continu, et une fuite de données personnelles dans les
    # journaux. Il faut le demander explicitement via TCHUEKAM_SQL_ECHO.
    sql_level = logging.INFO if os.getenv("TCHUEKAM_SQL_ECHO", "").strip() == "1" else logging.WARNING
    logging.getLogger("sqlalchemy.engine").setLevel(sql_level)

    _configured = True
