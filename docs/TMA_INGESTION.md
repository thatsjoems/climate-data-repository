# TMA Climate Data Ingestion Pipeline

## Status: architecture ready, no real TMA connection exists yet

This document describes how climate observations get into the CDR, and
exactly what is needed to switch from synthetic demo data to real TMA data.
**No TMA API, file format, or delivery mechanism has been invented or
assumed** — TMA has not yet agreed on one. What exists is a validation
pipeline that any future real feed (API, CSV, XLSX, SFTP, database export)
can plug into without a redesign.

## Pipeline

```
Raw file (CSV/XLSX)
      ↓
Schema check (required columns present?)
      ↓
Per-row validation (region, district, year, month, numeric fields)
      ↓
Duplicate detection (region + district + year + month + source_record_id)
      ↓
Accepted rows → ClimateRecord (quality_flag = UNVALIDATED)
Rejected rows → ClimateIngestionError (with the specific reason)
      ↓
ClimateIngestionBatch (provenance: who, when, source, counts)
```

Implementation: `backend/app/services/climate_ingestion_service.py` (parsing
and validation, pure functions, no DB access — independently testable) and
`backend/app/api/climate_data.py` (the endpoint that wires validation to the
database and provenance tables).

## Today: the file-upload adapter

`POST /api/climate-data/ingest` (BOT_USER only) accepts a `.csv` or `.xlsx`
file with these columns:

| Column | Required | Notes |
|---|---|---|
| `region` | Yes | Must be one of the 31 official Tanzania regions |
| `district` | No | Must belong to the given region if provided |
| `year` | Yes | 1990 to (current year + 1) |
| `month` | No | 1-12; if blank, the observation is treated as annual |
| `rainfall_mm` | No* | Numeric |
| `avg_temperature_c` | No* | Numeric |
| `temperature_min_c` | No* | Numeric |
| `temperature_max_c` | No* | Numeric |
| `hazard_type` | No | Free text (e.g. Drought, Flood, Cyclone) |
| `hazard_severity` | No | LOW, MEDIUM, HIGH, or blank |
| `station_id` / `station_name` | No | For traceability to a specific weather station |
| `latitude` / `longitude` | No | Station or observation point coordinates |
| `source_record_id` | No | The source system's own ID for this observation — used for duplicate detection on re-ingestion |

\* At least one of `rainfall_mm`, `avg_temperature_c`, `temperature_min_c`,
`temperature_max_c` must be present — a row with no measurement at all is
rejected as having nothing to record.

Every accepted row is stored with `quality_flag = "UNVALIDATED"` — ingestion
success is not the same as scientific validation. A human QC step (promoting
selected records to `VALIDATED`, or marking suspect ones `FLAGGED`) is not
yet built as a UI action; the field exists and is ready for that workflow.

## What is explicitly NOT done, and why

- **No TMA API client.** TMA has not published or agreed on an API. Building
  one now would mean inventing an integration contract that would likely be
  wrong and need to be thrown away.
- **No automatic scheduling/polling.** There is nothing to poll yet.
- **No interpolation, estimation, or backfilling of missing data.** If a
  region/period has no observation, the system shows "No data available" —
  never a guessed, copied, or averaged-from-elsewhere value. This is a hard
  rule (see `docs/ASSUMPTIONS_AND_LIMITATIONS.md`).
- **No automatic overwrite of existing observations.** Duplicate detection
  rejects a re-ingested observation rather than silently replacing the
  existing one — a real correction/replacement workflow would need an
  explicit human decision, which is not yet built.

## Steps to connect real TMA data, when TMA is ready

1. **Get the real format from TMA**: file layout (or API contract), column
   names/units, delivery frequency, and a sample file.
2. **Add a thin adapter** that maps TMA's actual column names to the
   `climate_ingestion_service.py` internal record shape (region, year, month,
   rainfall_mm, etc.) — the validation logic itself does not change.
3. **If TMA sends region names that don't match our 31 official region
   names** (e.g. abbreviations, different spelling), add a mapping table
   rather than loosening validation — an unmapped region should stay
   rejected, not silently guessed.
4. **Switch `source` from `"SYNTHETIC_SAMPLE"`/`"MANUAL_UPLOAD"` to the real
   source label** (e.g. `"TMA_FILE"` or `"TMA_API"`) so every downstream
   view (Combined Climate-Financial Exposure, Risk Advisory Reports, Data
   Quality dashboard) automatically distinguishes real from demo data — no
   other code change needed, since these views already read `source` and
   `quality_flag` from each record.
5. **Decide the QC promotion workflow**: who reviews `UNVALIDATED` records
   and promotes them to `VALIDATED`/`FLAGGED`, and add that as a UI action
   (currently only the data model supports this state, not a review screen).
6. **Retire the synthetic seed data** from `init_db.py` once real data is
   flowing (or keep both, clearly labelled, during a transition period).

## Data quality visibility

`GET /api/climate-data/quality-summary` and the "Climate Data Quality"
section on the BOT Analyst dashboard show, from live counts (never
estimated): total observations, how many are synthetic vs validated vs
unvalidated vs flagged, which of the 31 regions have zero observations, and
recent ingestion batch history (received/accepted/rejected/duplicate counts
per upload).
