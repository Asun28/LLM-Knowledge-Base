"""Verify augment config constants are present with sensible defaults and types."""


def test_augment_constants_exist_with_correct_types():
    from kb import config

    assert config.AUGMENT_FETCH_MAX_BYTES == 5_000_000
    assert config.AUGMENT_FETCH_CONNECT_TIMEOUT == 5.0
    assert config.AUGMENT_FETCH_READ_TIMEOUT == 30.0
    assert config.AUGMENT_FETCH_MAX_REDIRECTS == 10
    assert config.AUGMENT_FETCH_MAX_CALLS_PER_RUN == 10  # hard ceiling
    assert config.AUGMENT_FETCH_MAX_CALLS_PER_HOUR == 60
    assert config.AUGMENT_FETCH_MAX_CALLS_PER_HOST_PER_HOUR == 3
    assert config.AUGMENT_COOLDOWN_HOURS == 24
    assert config.AUGMENT_RELEVANCE_THRESHOLD == 0.5
    assert config.AUGMENT_WIKIPEDIA_FUZZY_THRESHOLD == 0.7
    assert isinstance(config.AUGMENT_ALLOWED_DOMAINS, tuple)
    assert "en.wikipedia.org" in config.AUGMENT_ALLOWED_DOMAINS
    assert "arxiv.org" in config.AUGMENT_ALLOWED_DOMAINS
    assert isinstance(config.AUGMENT_CONTENT_TYPES, tuple)
    assert "text/html" in config.AUGMENT_CONTENT_TYPES
    assert "application/pdf" in config.AUGMENT_CONTENT_TYPES


def test_augment_allowed_domains_env_override(monkeypatch):
    monkeypatch.setenv("AUGMENT_ALLOWED_DOMAINS", "example.com,foo.org")
    # Force re-import
    import importlib

    from kb import config

    importlib.reload(config)
    try:
        assert config.AUGMENT_ALLOWED_DOMAINS == ("example.com", "foo.org")
    finally:
        # Restore default after test
        monkeypatch.delenv("AUGMENT_ALLOWED_DOMAINS")
        importlib.reload(config)
