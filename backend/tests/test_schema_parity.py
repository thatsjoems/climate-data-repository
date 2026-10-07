"""
Static guards against model / migration / verification-script drift.

Why: the test suite builds its SQLite database from models.py (create_all), but the real
PostgreSQL database is built only by Alembic migrations. A constraint declared in models.py
and never created by a migration therefore exists in every test and in no real database -
the suite passes while production silently lacks the protection. That already happened once
(migration 9c1852419557) and again for three more constraints (fixed by f4a9c2d71b05).
scripts/verify_db_constraints.py could not catch the second one either, because it did not
list them. These tests need no database; they read the files.
"""
import re
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]

# Created by raw SQL in migrations (functional/expression indexes the ORM cannot declare),
# so they are deliberately absent from models.py.
MIGRATION_ONLY_UNIQUE_INDEXES = {
    "uq_climate_observation_source_identity",
    "uq_climate_observation_station_identity",
}


def _declared_in_models():
    text = (BACKEND / "app" / "models" / "models.py").read_text(encoding="utf-8")
    checks = set(re.findall(r'name="(ck_[a-z0-9_]+)"', text))
    uniques = set(re.findall(r'Index\(\s*"(uq_[a-z0-9_]+)"', text))
    return checks, uniques


def _migration_sources():
    return {
        p.name: p.read_text(encoding="utf-8")
        for p in sorted((BACKEND / "alembic" / "versions").glob("*.py"))
    }


def test_the_models_declare_a_plausible_number_of_protections():
    # Guards the regexes themselves: if a refactor made them match nothing, every other
    # test here would pass vacuously.
    checks, uniques = _declared_in_models()
    assert len(checks) >= 29
    assert len(uniques) >= 2


def test_every_constraint_declared_in_the_models_is_created_by_a_migration():
    checks, uniques = _declared_in_models()
    all_migrations = "\n".join(_migration_sources().values())
    missing = sorted(n for n in checks | uniques if n not in all_migrations)
    assert not missing, (
        "Declared in models.py but created by no migration - the real database would lack "
        f"these protections while the SQLite test database has them: {missing}"
    )


def test_the_migration_only_unique_indexes_are_created_by_a_migration():
    all_migrations = "\n".join(_migration_sources().values())
    missing = sorted(n for n in MIGRATION_ONLY_UNIQUE_INDEXES if n not in all_migrations)
    assert not missing, f"expected from a migration but not found in any: {missing}"


def test_the_verification_script_expects_every_declared_protection():
    script = (BACKEND / "scripts" / "verify_db_constraints.py").read_text(encoding="utf-8")
    expected = set(re.findall(r'"((?:ck|uq)_[a-z0-9_]+)"', script))
    checks, uniques = _declared_in_models()
    missing = sorted((checks | uniques | MIGRATION_ONLY_UNIQUE_INDEXES) - expected)
    assert not missing, (
        f"scripts/verify_db_constraints.py would not notice if these were missing from the real database: {missing}"
    )


def test_the_migrations_form_one_linear_chain_with_a_single_head():
    revisions, parents = {}, set()
    for name, text in _migration_sources().items():
        # Accepts both `revision = "x"` and the typed form Alembic's own template emits,
        # `revision: str = 'x'` / `down_revision: Union[...] = None` (the first migration).
        rev = re.search(r'^revision\s*(?::[^=\n]+)?=\s*[\'"]([^\'"]+)[\'"]', text, re.M)
        down = re.search(r'^down_revision\s*(?::[^=\n]+)?=\s*(?:[\'"]([^\'"]*)[\'"]|None)', text, re.M)
        assert rev and down, f"{name}: could not read revision / down_revision"
        assert rev.group(1) not in revisions, f"duplicate revision id {rev.group(1)}"
        revisions[rev.group(1)] = down.group(1)
        if down.group(1):
            parents.add(down.group(1))
    heads = [r for r in revisions if r not in parents]
    roots = [r for r, d in revisions.items() if not d]
    assert len(heads) == 1, f"expected exactly one migration head, found {heads}"
    assert len(roots) == 1, f"expected exactly one root migration, found {roots}"
    assert all(d in revisions for d in revisions.values() if d), "a migration points at a revision that does not exist"
