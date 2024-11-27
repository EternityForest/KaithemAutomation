# SPDX-FileCopyrightText: Copyright 2013 Daniel Dunn
# SPDX-License-Identifier: GPL-3.0-only
import base64
import collections
import json
import logging
import threading
import time

import quart
import quart.utils
import structlog

from . import auth, kaithemobj, messagebus, pages, quart_app, util

logger = structlog.get_logger(__name__)
failureRecords = collections.OrderedDict()
recordslock = threading.RLock()

# indexed by username, they are numbers of what time to lock out logins until
lockouts = {}

# Experimenal code not implemented, intended to send warning if the ratio of failed logins to real logins is excessive
# in a short period.
lastCleared = time.time()
recentAttempts = 0
alreadySent = 0


def onAttempt():
    global lastCleared, recentAttempts, alreadySent
    if time.time() - lastCleared > 60 * 30:
        lastCleared = time.time()
        if recentAttempts < 50:
            alreadySent = 0
        recentAttempts = 0
    recentAttempts += 1
    if recentAttempts > 150 and not alreadySent:
        alreadySent = 1
        logging.warning("Many failed login attempts have occurred")
        messagebus.post_message(
            "/system/notifications/warnings",
            "Excessive number of failed attempts in the last 30 minutes.",
        )


def onFail(ip, user, lockout=True):
    with recordslock:
        if ip in failureRecords:
            r = failureRecords[ip]
            failureRecords[ip] = (time.time(), r[1] + 1, user)
        else:
            failureRecords[ip] = (time.time(), 1, user)

        if len(failureRecords) > 1000:
            failureRecords.popitem(last=False)
    if lockout:
        if user in auth.Users:
            lockouts[user] = time.time() + 3


@quart_app.app.route("/login")
def login_index():
    kwargs = quart.request.args
    if not quart.request.scheme == "https":
        x = quart.request.remote_addr
        if not pages.isHTTPAllowed(x):
            return quart.redirect("/errors/gosecure")
    return pages.get_template("login.html").render(
        target=kwargs.get("go", "/"), kaithemobj=kaithemobj
    )


@quart_app.app.route("/login/login", methods=["POST"])
async def login():
    kwargs = dict(quart.request.args)
    kwargs.update(await quart.request.form)
    # Handle some nuisiance errors.

    def f():
        if "username" not in kwargs:
            return quart.redirect("/index")

        if "__nologin__" in pages.getSubdomain():
            raise RuntimeError(
                "To prevent XSS attacks, login is forbidden from any subdomain containing __nologin__"
            )

        # Empty fields try the default. But don't autofill username if password is set.
        # If that actually worked because someone didn't fill the username in, they might be confused and
        # feel like the thing wasn't validating input at all.
        if not kwargs["username"] and not kwargs["password"]:
            kwargs["username"] = "admin"
        if not kwargs["password"]:
            kwargs["password"] = "password"  # pragma: allowlist secret

        if auth.getUserSetting(pages.getAcessingUser(), "restrict-lan"):
            if not util.is_private_ip(quart.request.remote_addr):
                r = quart.redirect("/errors/localonly")

        if not quart.request.scheme == "https":
            x = quart.request.remote_addr
            if not pages.isHTTPAllowed(x):
                r = quart.redirect("/errors/gosecure")
        # Insert a delay that has a random component of up to 256us that is derived from the username
        # and password, to prevent anyone from being able to average it out, as it is the same per
        # query
        auth.resist_timing_attack(
            kwargs["username"].encode("utf8")
            + kwargs["password"].encode("utf8")
        )
        x = auth.userLogin(kwargs["username"], kwargs["password"])
        # Don't ratelimit very long passwords, we'll just assume they are secure
        # Someone might still make a very long insecure password, but
        # for now lets assume that people with long passwords know what they're doing.
        if len(kwargs["password"]) < 32:
            if kwargs["username"] in lockouts:
                if time.time() < lockouts[kwargs["username"]]:
                    raise RuntimeError(
                        "Maximum 1 login attempt per 3 seconds per account."
                    )

        if not x == "failure":
            if "maxgotime" in kwargs:
                if time.time() > float(kwargs["maxgotime"]):
                    r = quart.redirect("/")
            try:
                dest = base64.b64decode(kwargs["go"]).decode()
            except Exception:
                dest = "/index"
            if "/errors/loginerror" not in dest:
                r = quart.redirect(dest)
            else:
                r = quart.redirect("/index")
            # todo: Secure cookies?

            # Give the user the security token.
            # AFAIK this is and should at least for now be the
            # ONLY place in which the auth cookie is set.
            r.set_cookie(
                "kaithem_auth",
                x,
                samesite="Strict",
                path="/",
                httponly=True,
                secure=False,
            )

            x = auth.Users[kwargs["username"]]
            if "loginhistory" not in x:
                x["loginhistory"] = [(time.time(), quart.request.remote_addr)]
            else:
                x["loginhistory"].append(
                    (time.time(), quart.request.remote_addr)
                )
                x["loginhistory"] = x["loginhistory"][:100]

            messagebus.post_message(
                "/system/auth/login",
                [kwargs["username"], quart.request.remote_addr],
            )

            return r
        else:
            onFail(quart.request.remote_addr, kwargs["username"])
            messagebus.post_message(
                "/system/auth/loginfail",
                [kwargs["username"], quart.request.remote_addr],
            )
            return quart.redirect("/errors/loginerror")

    return await quart.utils.run_sync(f)()


@quart_app.app.route("/login/logout", methods=["POST"])
def logout():
    # Delete token on client
    pages.postOnly()
    if quart.request.cookies["kaithem_auth"] in auth.Tokens:
        messagebus.post_message(
            "/system/auth/logout",
            [
                auth.whoHasToken(quart.request.cookies["kaithem_auth"]),
                quart.request.remote_addr,
            ],
        )
    r = quart.redirect("/index")
    r.set_cookie(
        "kaithem_auth",
        "",
        samesite="Strict",
        path="/",
        httponly=True,
        secure=False,
    )
    return r


@quart_app.app.route("/api.core/check-permission/<permission>", methods=["GET"])
def check_own_permissions(permission: str) -> str:
    return json.dumps(auth.canUserDoThis(pages.getAcessingUser(), permission))
