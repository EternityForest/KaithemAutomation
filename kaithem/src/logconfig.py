import logging

# Make this not spew debug logs, I'm pretty sure that lib is well tested and
# Reliable and we don't need to know about every request.
logs = logging.getLogger("urllib3.connectionpool")
logs.setLevel(logging.INFO)

# Make this not spew debug logs, I'm pretty sure that lib is well tested and
# Reliable and we don't need to know about every request.
logs = logging.getLogger("hbmqtt.broker")
logs.setLevel(logging.WARNING)
logs = logging.getLogger("hbmqtt.client")
logs.setLevel(logging.WARNING)

logs = logging.getLogger("transitions.core")
logs.setLevel(logging.WARNING)
logs = logging.getLogger("hbmqtt.mqtt.protocol.handler")
logs.setLevel(logging.INFO)

logs = logging.getLogger("PIL.Image")
logs.setLevel(logging.WARNING)


rlogger = logging.getLogger()
rlogger.setLevel(logging.INFO)

logger = logging.getLogger("system")
logger.setLevel(logging.INFO)

logger = logging.getLogger("aioesphomeapi.connection")
logger.setLevel(logging.WARNING)

logger = logging.getLogger("aioesphomeapi._frame_helper")
logger.setLevel(logging.WARNING)

logger = logging.getLogger("aioesphomeapi.reconnect_logic")
logger.setLevel(logging.WARNING)

logger = logging.getLogger("PIL.PngImagePlugin")
logger.setLevel(logging.WARNING)


logger = logging.getLogger("peewee")
logger.setLevel(logging.WARNING)


logger = logging.getLogger("tornado.general")
logger.setLevel(logging.WARNING)


logging.getLogger("cherrypy.access").propagate = False
logging.getLogger("tornado.access").propagate = False


# Suppress low level from these outrageously chatty things
excludeDebug = {
    'zeep.xsd.schema': 1,
    'zeep.wsdl.wsdl': 1,
    'zeep.xsd.visitor': 1,
    'zeep.transports': 1,
}

for i in excludeDebug:
    logging.getLogger(i).setLevel(logging.INFO)