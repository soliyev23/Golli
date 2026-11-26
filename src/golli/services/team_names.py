"""Klub nomlarining tarjimalari: data/team_names.toml.

Kalit — provayder bergan nom. Tarjimasi yo'q klub provayder nomi bilan ko'rsatiladi,
shuning uchun yangi klub paydo bo'lsa ham bot ishlayveradi.
"""

import tomllib
from pathlib import Path

TEAM_NAMES_FILE = Path(__file__).parent.parent / "data" / "team_names.toml"


class TeamNames:
    def __init__(self, path: Path = TEAM_NAMES_FILE) -> None:
        with path.open("rb") as file:
            self._names: dict[str, dict[str, str]] = tomllib.load(file)

    def get(self, name: str, locale: str) -> str:
        return self._names.get(name, {}).get(locale, name)

    def __contains__(self, name: str) -> bool:
        return name in self._names
