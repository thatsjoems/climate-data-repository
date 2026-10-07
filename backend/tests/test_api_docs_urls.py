"""The interactive API documentation is not served in production (it lists every endpoint)."""
import pytest

from app.core.startup_checks import api_docs_urls


@pytest.mark.parametrize("environment", ["production", "Production", " PRODUCTION ", "production\n"])
def test_no_interactive_documentation_in_production(environment):
    assert api_docs_urls(environment) == {"docs_url": None, "redoc_url": None, "openapi_url": None}


@pytest.mark.parametrize("environment", ["development", "staging", "", None])
def test_documentation_is_kept_everywhere_else(environment):
    assert api_docs_urls(environment) == {"docs_url": "/docs", "redoc_url": "/redoc", "openapi_url": "/openapi.json"}
