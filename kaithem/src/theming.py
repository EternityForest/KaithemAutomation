from src.config import config
from src import registry


def getCSSTheme():
    return registry.get("/system.theming/csstheme", config['theme-url'])
