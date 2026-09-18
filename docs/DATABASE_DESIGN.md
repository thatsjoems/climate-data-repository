# CDR Database Design & Cleanliness

## Design principles

The database separates identity/access, financial submissions, climate ingestion,
climate observations, risk advisory notes, notifications, and audit logging.
Foreign keys are used for core ownership relationships and indexes follow the
main filtering/join paths used by analytics and workflow APIs.

## Climate provenance

Every climate observation ingested from a file is linked to its
`climate_ingestion_batches` row through `climate_records.batch_id`. This makes
the provenance chain explicit:

`source file -> ingestion batch -> climate record -> QC state -> analytics`

Legacy records created before batch linkage may have `batch_id = NULL`; new
ingestion records must always have a batch.

## Duplicate identity

The ingestion service uses the source-aware observation identity:

`region + district + year + month + source_record_id + station_id`

The application rejects duplicates rather than overwriting observations. A
non-unique database index is deliberately used for this composite identity
because `source_record_id` and `station_id` may legitimately be missing; a
blind UNIQUE constraint would incorrectly reject multiple source rows with
missing identifiers. If a future source provides a guaranteed immutable record
identifier, a source-specific UNIQUE constraint can be introduced safely.

## Synthetic data policy

Seed/demo climate observations remain `quality_flag = SYNTHETIC`. They are never
seeded as `VALIDATED` or `FLAGGED`. Those states are reserved for the human QC
workflow on ingested observations.

## Transaction integrity

Climate ingestion writes the batch, accepted observations, row-level errors, and
ingestion audit event in one transaction. If the transaction fails, the data and
its corresponding ingestion audit event are not partially committed.

## Empty files

`__init__.py` files and `uploads/.gitkeep` are intentional empty files. They are
not data files and should not be removed merely because they contain no text.

## Migrations and existing database compatibility

Schema evolution is controlled by Alembic. The migration chain preserves
existing data and applies additive/controlled integrity changes. Pre-Alembic
CDR databases are baselined only when the expected legacy tables are present;
subsequent migrations add missing provenance/index/uniqueness protections. No
database volume is deleted automatically. If a migration detects duplicate
rows that would make a uniqueness rule unsafe, it fails without deleting or
merging data.
