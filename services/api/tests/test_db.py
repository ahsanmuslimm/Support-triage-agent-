"""Tests for triage.db helpers (DATABASE_URL normalization, tenancy)."""

from triage.db import normalize_database_url


class TestNormalizeDatabaseUrl:
    def test_rewrites_postgres_scheme(self):
        assert (
            normalize_database_url("postgres://u:p@h:5432/db")
            == "postgresql+asyncpg://u:p@h:5432/db"
        )

    def test_rewrites_psycopg_scheme(self):
        assert (
            normalize_database_url("postgresql+psycopg://u:p@h/db")
            == "postgresql+asyncpg://u:p@h/db"
        )

    def test_plain_url_untouched(self):
        url = "postgresql+asyncpg://u:p@localhost:5432/triage"
        assert normalize_database_url(url) == url

    def test_translates_sslmode_for_asyncpg(self):
        # asyncpg's connect() only understands `ssl=`; hosted providers
        # (Neon, Railway, Heroku) hand out libpq-style `sslmode=`.
        normalized = normalize_database_url(
            "postgresql://u:p%40ss@ep-x.neon.tech/neondb?sslmode=require"
        )
        assert normalized == "postgresql+asyncpg://u:p%40ss@ep-x.neon.tech/neondb?ssl=require"

    def test_preserves_other_query_params(self):
        normalized = normalize_database_url(
            "postgresql://u:p@h/db?sslmode=require&application_name=triage"
        )
        assert "ssl=require" in normalized
        assert "application_name=triage" in normalized
