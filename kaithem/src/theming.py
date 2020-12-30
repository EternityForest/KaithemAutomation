from src.config import config
from src import auth, util, notifications, pages, modules, registry


def getCSSTheme():
    return registry.get("/system.theming/csstheme", config['theme-url'])
