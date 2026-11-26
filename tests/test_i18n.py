import pytest
from fluent.syntax import ast, parse

from golli.i18n import LOCALES_DIR, I18n


def message_ids(path) -> set[str]:
    resource = parse(path.read_text(encoding="utf-8"))
    junk = [entry.content for entry in resource.body if isinstance(entry, ast.Junk)]
    assert not junk, f"{path.name} faylida sintaksis xatosi: {junk}"
    return {entry.id.name for entry in resource.body if isinstance(entry, ast.Message)}


def test_locale_files_are_valid_and_have_same_keys():
    files = sorted(LOCALES_DIR.glob("*.ftl"))
    assert {path.stem for path in files} == {"uz", "ru", "en"}

    expected = message_ids(LOCALES_DIR / "uz.ftl")
    assert expected
    for path in files:
        assert message_ids(path) == expected, f"{path.name} kalitlari uz.ftl bilan mos emas"


def test_locales_come_in_preferred_order():
    assert I18n("uz").locales == ("uz", "ru", "en")


@pytest.mark.parametrize("locale", ["uz", "ru", "en"])
def test_variable_is_substituted_without_invisible_marks(locale):
    text = I18n("uz").translate(locale, "start-welcome", name="Ali")

    assert "Ali" in text
    assert "{" not in text
    assert "\N{FIRST STRONG ISOLATE}" not in text
    assert "\N{POP DIRECTIONAL ISOLATE}" not in text
    # Ko'p qatorli matnda xatboshilar saqlanadi.
    assert "\n\n" in text


def test_translations_differ_between_languages():
    assert len(I18n("uz").variants("menu-matches")) == 3


def test_missing_key_raises():
    with pytest.raises(KeyError):
        I18n("uz").translate("uz", "bunday-kalit-yoq")


def test_unknown_default_locale_raises(tmp_path):
    with pytest.raises(ValueError):
        I18n("uz", locales_dir=tmp_path)


def test_fallback_to_default_locale(tmp_path):
    (tmp_path / "uz.ftl").write_text("hello = Salom\nbye = Xayr\n", encoding="utf-8")
    (tmp_path / "ru.ftl").write_text("hello = Привет\n", encoding="utf-8")
    i18n = I18n("uz", locales_dir=tmp_path)

    assert i18n.resolve_locale("ru") == "ru"
    assert i18n.resolve_locale("de") == "uz"
    assert i18n.resolve_locale(None) == "uz"
    assert i18n.translator("ru")("hello") == "Привет"
    # ru.ftl da yo'q kalit asosiy tildan olinadi.
    assert i18n.translator("ru")("bye") == "Xayr"
    assert i18n.in_all_locales("hello") == ["Salom", "Привет"]
    assert i18n.variants("hello") == {"Salom", "Привет"}
