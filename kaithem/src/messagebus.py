# SPDX-FileCopyrightText: Copyright 2013 Daniel Dunn
# SPDX-License-Identifier: GPL-3.0-only

from scullery import messagebus
import traceback
import cherrypy
import weakref
import logging

post_message = messagebus.post_message
post = messagebus.post_message
subscribe = messagebus.subscribe
unsubscribe = messagebus.unsubscribe
normalize_topic = messagebus.normalize_topic
log = messagebus.log
MessageBus = messagebus.MessageBus


def handleMsgbusError(f, topic, message):
    try:
        messagebus.log.exception(
            "Error in subscribed function for "
            + topic
            + " with message "
            + str(message)[:64]
        )
        from . import newevt

        if f.__module__ in newevt.eventsByModuleName:
            newevt.eventsByModuleName[f.__module__]._handle_exception()

        # If we can't handle it whence it came
        else:
            try:
                if isinstance(f, (weakref.WeakMethod, weakref.ref)):
                    f = f()
                x = hasattr(f, "_kaithemAlreadyPostedNotificatonError")
                f._kaithemAlreadyPostedNotificatonError = True
                if not x:
                    logging.exception("Message subscriber error for " + str(topic))
            except Exception:
                print(traceback.format_exc())

    except Exception:
        print(traceback.format_exc())
        del f


def _shouldReRaiseAttrErr():
    "Check if we actually need to notify about errors during cherrypy shutdown, to avoid annoyance"
    return cherrypy.engine.state == cherrypy.engine.states.STARTED


messagebus.subscriberErrorHandlers = [handleMsgbusError]
messagebus._shouldReRaiseAttrErr = _shouldReRaiseAttrErr
