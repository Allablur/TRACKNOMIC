from app.core.config import Settings


def test_managed_postgres_url_uses_installed_driver():
    for scheme in ["postgres://", "postgresql://", "postgresql+psycopg://"]:
        settings = Settings(
            _env_file=None, database_url=scheme + "user:pass@db.example/db?sslmode=require"
        )
        assert (
            settings.database_url == "postgresql+psycopg://user:pass@db.example/db?sslmode=require"
        )


def test_render_hostname_is_accepted_without_disabling_host_validation():
    settings = Settings(
        _env_file=None, render_external_hostname="trackonomics-example.onrender.com"
    )
    assert "trackonomics-example.onrender.com" in settings.allowed_hosts
    assert "*" not in settings.allowed_hosts
