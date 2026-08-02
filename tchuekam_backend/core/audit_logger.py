"""
Système de journalisation d'audit (Audit Logger) pour les évènements de sécurité.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger("tchuekam_audit")
logger.setLevel(logging.INFO)

# Handler console avec format d'audit JSON
if not logger.handlers:
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    ch.setFormatter(formatter)
    logger.addHandler(ch)


def log_security_event(
    action: str,
    user_id: Optional[str] = None,
    org_id: Optional[str] = None,
    resource: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
    status: str = "SUCCESS",
) -> Dict[str, Any]:
    """Enregistre un évènement de sécurité structuré et l'envoie aux logs."""
    event_data = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "action": action,
        "user_id": user_id,
        "org_id": org_id,
        "resource": resource,
        "status": status,
        "ip_address": ip_address,
        "user_agent": user_agent,
        "details": details or {},
    }
    log_msg = json.dumps(event_data, ensure_ascii=False)
    if status == "SUCCESS":
        logger.info(f"AUDIT_EVENT: {log_msg}")
    else:
        logger.warning(f"AUDIT_SECURITY_ALERT: {log_msg}")
    return event_data
