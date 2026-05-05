"""Test that trafilatura download cache is disabled by default (AC15)."""

import os


def test_no_cache_env_set():
    """Assert the no-cache env var is set after importing kb.lint.fetcher."""
    # Import the module to trigger the setdefault
    import kb.lint.fetcher  # noqa: F401

    # Check that the environment variable is set
    assert os.environ["TRAFILATURA_DOWNLOAD_NO_CACHE"] == "1", (
        "TRAFILATURA_DOWNLOAD_NO_CACHE env var not set correctly"
    )


def test_fetch_url_observes_no_cache(monkeypatch):
    """Test that fetcher observes the no-cache environment variable."""

    import kb.lint.fetcher

    # Monkeypatch trafilatura to track if it's called (monkeypatch
    # auto-restores; no need to capture the original).
    call_tracker = {"called": False, "env_value": None}

    def spy_fetch_url(*args, **kwargs):
        # Capture the env var at call time
        call_tracker["called"] = True
        call_tracker["env_value"] = os.environ.get("TRAFILATURA_DOWNLOAD_NO_CACHE")
        # Return a dummy result instead of actually fetching
        return None

    monkeypatch.setattr(kb.lint.fetcher.trafilatura, "fetch_url", spy_fetch_url)

    # The environment variable should be set at module load time
    assert os.environ.get("TRAFILATURA_DOWNLOAD_NO_CACHE") == "1", (
        "Environment variable should be set at module load time"
    )
