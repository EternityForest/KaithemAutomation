def setup():
    import config
    import logging
    level = logging.INFO
    if config.DEBUG:
        level = logging.DEBUG
    logging.basicConfig(level=level)
