from kaithem.api import settings


def test_setting_overrides():
    settings.add_val("test_key", "test_value", "test_source", 1)

    assert settings.get_val("test_key") == "test_value"

    settings.add_val("test_key", "foo", "test_source2", 2)

    assert settings.get_val("test_key") == "foo"

    settings.add_val("test_key", "", "test_source2", 9)

    assert settings.get_val("test_key") == "test_value"

    assert "test_key" in settings.list_keys()

    settings.add_val("test_key", "", "test_source", 1)

    assert settings.get_val("test_key") == ""

    assert "test_key" not in settings.list_keys()
