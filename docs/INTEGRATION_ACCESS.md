# Integration access: read-only keys for external systems

A key lets an external system either **read approved figures** or **send climate files**, over HTTPS, with no person signed in. A key has exactly one of three types, chosen when it is created: **READ**, **INGEST_TMA** or **INGEST_PMO**. A key never does the other type's job.

## What each type of key can and cannot do

| Type | It can | It can never |
|---|---|---|
| **READ** | Read the approved, current figures, sector-wide, exactly as a BOT analyst sees them on the dashboard (same functions, so the numbers cannot differ), through the `GET /api/integration/...` endpoints below | Write anything, read a pending, invalid or rejected submission, send a file, or call any other endpoint |
| **INGEST_TMA**, **INGEST_PMO** | Send a climate file (CSV or Excel) to `POST /api/integration/climate-data`. It is checked exactly like a manual upload and stored as **UNVALIDATED** | Read anything (not even the dashboard figures), choose its own source label, mark data validated, or call any other endpoint |
| any | Work until it expires (1 to 365 days, 180 by default) or is revoked | Outlive its expiry; revoking cuts it at once |

A key of one type that is used for the other type's job is refused with `403 This key is not allowed to do that`, and the refusal is audited.

## Who does what (separation of duties)

| Role | Create a key | See the list | Revoke |
|---|---|---|---|
| BOT analyst | **Yes** | Yes | Yes |
| System Administrator | **No** (this role may not read supervisory data, and a key would be a way round that rule) | Yes (names, prefixes, dates; never a key) | **Yes**: an emergency control |
| Institution user | No | No | No |

The key is shown **once**, when it is created, and is never stored (only its SHA-256 hash is). Lose it and you create a new one.

## Create, test and revoke

1. Sign in as a BOT analyst, open **Integration Access** in the left menu, choose the **type** (read approved data, send TMA climate files, or send PMO climate files), enter a name that says which system it is for (for example `QGIS - FSD GIS desk`) and the number of days, optionally list the addresses it may be used from, press **Create key**, and copy the key from the yellow box. Keep it in a secret store, never in an e-mail, a chat or git.
2. Test the connection (it reads nothing sensitive):

       curl -H "X-API-Key: <the key>" https://<address>/api/integration/whoami

   (`Authorization: Bearer <the key>` works too.) A good key answers with its name and expiry; any bad key answers `401 Invalid, expired or revoked API key`, whatever the reason.
3. To stop a system: **Revoke** in the same list (an administrator can do it too). To rotate: create a new key, switch the system to it, revoke the old one.

## The endpoints (all GET, all read-only)

| Path | What it returns |
|---|---|
| `/api/integration/whoami` | The key's name and expiry (a connection test) |
| `/api/integration/kpi-summary` | Summary figures |
| `/api/integration/hazard-exposure` | Exposure by hazard (`validated_only`, `filter_hazard_type`, `filter_region`, `filter_reporting_period`, `filter_institution_id`) |
| `/api/integration/combined-climate-financial-exposure` | Climate readings joined to loan and collateral exposure, by region and period (same filters) |
| `/api/integration/map-points` | Region-level points for a map (same filters) |
| `/api/integration/exposure-points` | The loan and collateral coordinates entered on the template (JSON) |
| `/api/integration/exposure-points.geojson` | The same points as GeoJSON (WGS 84, longitude first), ready for QGIS and ArcGIS |
| `POST /api/integration/climate-data` | **Sending keys only.** Receives a climate file; see the next section |

## QGIS and ArcGIS (not run against a live server here; test on a copy first)

QGIS Python console (the key comes from your secret store, not from a shared script; with a trial self-signed certificate the HTTPS call fails until the Bank certificate is installed):

    import urllib.request
    from qgis.core import QgsVectorLayer, QgsProject
    req = urllib.request.Request("https://<address>/api/integration/exposure-points.geojson", headers={"X-API-Key": KEY})
    layer = QgsVectorLayer(urllib.request.urlopen(req).read().decode("utf-8"), "CDR exposure points", "ogr")
    QgsProject.instance().addMapLayer(layer)

QGIS can also keep the key in its own authentication store (an "API Header" configuration with the header `X-API-Key`, available in recent versions) and load the GeoJSON address as a vector layer. ArcGIS Pro: download the GeoJSON with a short Python script (`requests.get(url, headers={"X-API-Key": KEY})`) and convert it with the JSON To Features tool. Menu names differ by version.

## Sending climate files (an INGEST_TMA or INGEST_PMO key)

This is a **channel the Bank can offer** to TMA, to PMO or to its own scheduled job. It is not an agreed TMA or PMO interface: neither has agreed one (see TMA_INGESTION.md), and the label below names the channel, not a verified sender.

    curl -X POST -H "X-API-Key: YOUR_API_KEY" -F "file=@tma_observations_2026_09.csv" \
         -F "dataset_name=TMA monthly observations" -F "dataset_version=2026-09" \
         https://<address>/api/integration/climate-data

The file has the same columns as the manual upload (`region` and `year` are required, at least one measurement per row; the full list is in TMA_INGESTION.md), for example:

    region,district,year,month,rainfall_mm,avg_temperature_c,hazard_type,station_id,source_record_id
    Dodoma,,2026,9,45.2,24.1,Drought,TMA-DOD-01,T2026-09-001

What happens, and what the sender cannot influence:

- **The source label comes from the key**: `API_KEY_TMA` or `API_KEY_PMO`. The sender cannot choose it, and a person cannot type these labels in the manual upload.
- **Every row is checked exactly as in a manual upload** (one shared implementation: official regions and districts, plausible ranges, coordinates, hazard names, duplicates). Rejected rows are not stored; the reply lists the first 500 of them (row, column, reason) and says how many there are in all.
- **Everything accepted arrives UNVALIDATED.** It enters the analysis only after a BOT analyst promotes it, so a feed cannot change a dashboard figure by itself.
- **Sending the same file again is safe.** What is already stored comes back as duplicates; nothing is overwritten.
- **Limits:** 20 MB and 100,000 rows per file, 30 files a minute per key.
- **Recorded:** the batch stores which key delivered it (and no user); the audit log holds an `INTEGRATION_INGEST` entry with the key's name, the file and the counts; every BOT analyst gets a notification that records await validation.

The reply is the batch (`source`, `records_received`, `records_accepted`, `records_rejected`, `records_duplicate`, `status`), an `errors` list with the row, the column and the reason of up to the first 500 rejected rows, and `errors_total`, the number of rejected rows in all. A sender with more than 500 bad rows fixes those and sends again (what was accepted comes back as duplicates); a BOT analyst can page through all of them with `GET /api/climate-data/ingestions/{id}?error_offset=500`.

## Limits to know

- **A key sees the whole sector's approved data**, like a BOT analyst. There are no per-institution or per-dataset scopes yet; give a system its own key and a name that says why it has one.
- **120 requests a minute per key** for reading, 30 files a minute for sending, counted for the key itself.
- **An optional list of allowed addresses per key** (for example `203.0.113.7, 10.20.0.0/16`; blank means any address). A key used from any other address is refused like every other bad key, and the audit log records the reason (`address not allowed`) and the address it came from. Fill it in whenever the sender has a fixed address: a leaked key is then of little use. It relies on the proxy setting described in PRODUCTION_DEPLOYMENT.md (`TRUSTED_PROXIES`), because behind the production web server every connection otherwise appears to come from the web server.
- Always HTTPS. The trial certificate is self-signed; a real certificate comes from BOT ICT.
- **Every read is audited**: the client's name, the path and the filters, and how many rows. Every refusal is audited with its real reason (wrong secret, unknown, revoked, expired), while the caller only ever sees one message. The key is never written anywhere.
- A sending key brings files in; it does not fetch anything by itself. A scheduled job, TMA or PMO must call it, and calling BSIS and RTIS still needs those systems' specifications.

## RTIS and BSIS (connection status; data exchange waits for the Bank's specification)

The sidebar of the BOT dashboard shows **Connected / Not Connected** for ArcGIS, QGIS, BSIS and RTIS. It is worked out by the server (`GET /api/integration-clients/platform-status`, BOT analysts only), never assumed:

| System | Connected means |
|---|---|
| QGIS, ArcGIS | A READ key whose name contains `qgis` or `arcgis` exists (not revoked, not expired) **and was used in the last 30 days**. Name each key after the tool, as in the example above. |
| BSIS, RTIS | The repository called the system's health-check address with its credential and got a 2xx answer within `EXTERNAL_SYSTEM_TIMEOUT_SECONDS` (5). Redirects are never followed, so the credential cannot be sent to another address. In production the address must be `https://`. |

To connect BSIS or RTIS, BOT ICT supplies the address, a credential and the health-check path, and they are set in `.env.production` (`RTIS_BASE_URL`, `RTIS_API_KEY`, `RTIS_HEALTH_PATH`, and the same three for `BSIS_`), then `scripts/prod_up` is run again. The credential is read only from the environment; it is never shown, stored in the database or written to the audit log.

**What this does not do yet.** It proves the link works. What data moves between the repository and RTIS or BSIS (for example the list of supervised institutions from BSIS) depends on those systems' interface specifications, which the project has not been given. When BOT ICT provides them, the exchange is added in `app/services/external_systems.py` next to the health check, with its own tests.

## After upgrading an existing production stack

Run `scripts/prod_up.ps1` (or `.sh`) again: it rebuilds the backend (which creates the `api_clients` table by migration `c6e9b2d4f713`) and re-applies the restricted-role grants. Then `python scripts/prod_ops.py backup` and `python scripts/prod_ops.py drill`.
