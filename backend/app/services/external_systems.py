"""
Connection status of the systems the Climate Data Repository works with (Concept Note: RTIS, BSIS, QGIS, ArcGIS).

Two kinds of connection exist, and the status of each is worked out differently and honestly:

* PUSH/PULL systems the repository calls (RTIS, BSIS): connected means the Bank's system answered its health
  check with a success status within the timeout, using the address and credential in the settings. Nothing is
  assumed about what else those systems offer - their data exchange is built on top of this once the Bank's ICT
  department gives the interface specification (docs/INTEGRATION_ACCESS.md).
* GIS tools that call the repository (QGIS, ArcGIS): they authenticate with a READ API key, so "connected" means
  a READ key exists that is neither revoked nor expired and was used within the last `GIS_ACTIVE_DAYS` days. The
  tools are not distinguished from each other by the key (a key is named by the person who creates it), so the key
  name is matched: a name containing "qgis" or "arcgis".
"""
from dataclasses import dataclass
from datetime import timedelta

import httpx
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.timeutil import utcnow
from app.models.models import ApiClient

GIS_ACTIVE_DAYS = 30


@dataclass
class SystemStatus:
    name: str
    kind: str          # "CALLED_BY_CDR" (RTIS, BSIS) or "CALLS_CDR" (QGIS, ArcGIS)
    configured: bool
    connected: bool
    detail: str


def check_http_system(name: str, base_url: str, api_key: str, health_path: str, production: bool | None = None) -> SystemStatus:
    """Health check of a system the repository calls. Never raises: any failure is reported as 'not connected'."""
    if production is None:
        production = settings.ENVIRONMENT.lower() == "production"
    base = (base_url or "").strip().rstrip("/")
    if not base:
        return SystemStatus(name, "CALLED_BY_CDR", False, False, "Not configured (no address set)")
    if not base.lower().startswith(("https://", "http://")):
        return SystemStatus(name, "CALLED_BY_CDR", True, False, "The address must start with https://")
    if production and not base.lower().startswith("https://"):
        return SystemStatus(name, "CALLED_BY_CDR", True, False, "Production requires an https:// address")
    path = health_path if health_path.startswith("/") else "/" + health_path
    headers = {"Authorization": f"Bearer {api_key}", "X-API-Key": api_key} if api_key else {}
    try:
        # follow_redirects is off: a credential must never be re-sent to an address nobody configured.
        response = httpx.get(base + path, headers=headers, timeout=settings.EXTERNAL_SYSTEM_TIMEOUT_SECONDS, follow_redirects=False)
    except httpx.TimeoutException:
        return SystemStatus(name, "CALLED_BY_CDR", True, False, "No answer within the time limit")
    except httpx.HTTPError:
        return SystemStatus(name, "CALLED_BY_CDR", True, False, "The system could not be reached")
    if 200 <= response.status_code < 300:
        return SystemStatus(name, "CALLED_BY_CDR", True, True, "Answered its health check")
    return SystemStatus(name, "CALLED_BY_CDR", True, False, f"The system answered with HTTP {response.status_code}")


def check_gis_tool(db: Session, name: str, keyword: str) -> SystemStatus:
    now = utcnow()
    keys = db.query(ApiClient).filter(ApiClient.scope == "READ", ApiClient.revoked_at.is_(None), ApiClient.expires_at > now).all()
    named = [k for k in keys if keyword in (k.name or "").lower()]
    if not named:
        return SystemStatus(name, "CALLS_CDR", False, False, f"No active read key named for {name} (create one in Integration Access)")
    recent = [k for k in named if k.last_used_at and now - k.last_used_at <= timedelta(days=GIS_ACTIVE_DAYS)]
    if recent:
        return SystemStatus(name, "CALLS_CDR", True, True, f"A key was used within the last {GIS_ACTIVE_DAYS} days")
    return SystemStatus(name, "CALLS_CDR", True, False, f"A key exists but has not been used in {GIS_ACTIVE_DAYS} days")


def all_statuses(db: Session) -> list[SystemStatus]:
    return [
        check_gis_tool(db, "ArcGIS", "arcgis"),
        check_gis_tool(db, "QGIS", "qgis"),
        check_http_system("BSIS", settings.BSIS_BASE_URL, settings.BSIS_API_KEY, settings.BSIS_HEALTH_PATH),
        check_http_system("RTIS", settings.RTIS_BASE_URL, settings.RTIS_API_KEY, settings.RTIS_HEALTH_PATH),
    ]
