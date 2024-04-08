# SPDX-FileCopyrightText: Copyright 2013 Daniel Dunn
# SPDX-License-Identifier: GPL-3.0-only

# This file manages a work queue that feeds a threadpool
# Tasks will be performed on a best effort basis and errors will be caught and ignored.

from scullery.workers import EXIT
from scullery.workers import do  # noqa

from . import config as cfg
from scullery import workers

import traceback
import cherrypy
import atexit


# I would *really* like to just use this code here. Unfortunately it's too slow.
# import concurrent.futures
# executor = concurrent.futures.ThreadPoolExecutor(max_workers=32)
# def do(f,args=[]):
#     return executor.submit(f, *args)


# import fastthreadpool

# pool = fastthreadpool.Pool()
# def do(f,args=[]):
#     return pool.submit(f, *args)


def workersErrorHandler(f):
    # If we can, try to send the exception back whence it came
    try:
        from . import newevt

        if f[0].__module__ in newevt.eventsByModuleName:
            newevt.eventsByModuleName[f[0].__module__]._handle_exception()
    except Exception:
        print(traceback.format_exc())


workers.backgroundFunctionErrorHandlers = [workersErrorHandler]
# Get the relevant config

qsize = cfg.config["task-queue-size"]
count = cfg.config["worker-threads"]
wait = cfg.config["wait-for-workers"]

# Start
workers.start(count, qsize, wait)

# Only now do we do the import, as we will actually have everything loaded

atexit.register(EXIT)
cherrypy.engine.subscribe("exit", EXIT)
