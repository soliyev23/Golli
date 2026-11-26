from golli.config import Settings


def make_settings(**overrides) -> Settings:
    # _env_file=None: test natijasi kompyuterdagi .env fayliga bog'liq bo'lmasin.
    return Settings(_env_file=None, **overrides)


def test_database_url_is_built_from_parts():
    settings = make_settings(
        postgres_host="db.local",
        postgres_port=6543,
        postgres_db="golli",
        postgres_user="golli",
        postgres_password="p@ss:w/rd",
    )

    url = settings.database_url

    assert url.drivername == "postgresql+asyncpg"
    assert (url.host, url.port, url.database, url.username) == ("db.local", 6543, "golli", "golli")
    # Maxsus belgilar buzilmasdan saqlanadi.
    assert url.password == "p@ss:w/rd"


def test_secrets_are_hidden_in_repr():
    settings = make_settings(bot_token="123:SECRET", postgres_password="topsecret")

    assert "SECRET" not in repr(settings)
    assert "topsecret" not in repr(settings)
    assert "topsecret" not in str(settings.database_url)
