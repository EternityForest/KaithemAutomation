# SPDX-FileCopyrightText: Copyright 2013 Daniel Dunn
# SPDX-License-Identifier: GPL-3.0-only
import cherrypy
import time
import collections
import threading
import logging
import base64
from . import pages, auth, util, messagebus, kaithemobj


logger = logging.getLogger("system.auth")
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


class LoginScreen:
    @cherrypy.expose
    def index(self, **kwargs):
        if not cherrypy.request.scheme == "https":
            x = cherrypy.request.remote.ip
            if not pages.isHTTPAllowed(x):
                raise cherrypy.HTTPRedirect("/errors/gosecure")
        return pages.get_template("login.html").render(
            target=kwargs.get("go", "/"), kaithemobj=kaithemobj
        )

    @cherrypy.expose
    def login(self, **kwargs):
        # Handle some nuisiance errors.

        if not "username" in kwargs:
            raise cherrypy.HTTPRedirect("/index")

        if "__nologin__" in pages.getSubdomain():
            raise RuntimeError(
                "To prevent XSS attacks, login is forbidden from any subdomain containing __nologin__"
            )

        # Not exactly needed but it could prevent attackers from making nuisiance log errors to scare you
        pages.postOnly()

        # Empty fields try the default. But don't autofill username if password is set.
        # If that actually worked because someone didn't fill the username in, they might be confused and
        # feel like the thing wasn't validating input at all.
        if not kwargs["username"] and not kwargs["password"]:
            kwargs["username"] = "admin"
        if not kwargs["password"]:
            kwargs["password"] = "password"  # pragma: allowlist secret

        if auth.getUserSetting(pages.getAcessingUser(), "restrict-lan"):
            if not util.is_private_ip(cherrypy.request.remote.ip):
                raise cherrypy.HTTPRedirect("/errors/localonly")

        if not cherrypy.request.scheme == "https":
            x = cherrypy.request.remote.ip
            if not pages.isHTTPAllowed(x):
                raise cherrypy.HTTPRedirect("/errors/gosecure")
        # Insert a delay that has a random component of up to 256us that is derived from the username
        # and password, to prevent anyone from being able to average it out, as it is the same per
        # query
        auth.resist_timing_attack(
            kwargs["username"].encode("utf8") + kwargs["password"].encode("utf8")
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
            # Give the user the security token.
            # AFAIK this is and should at least for now be the
            # ONLY place in which the auth cookie is set.
            cherrypy.response.cookie["kaithem_auth"] = x
            cherrypy.response.cookie["kaithem_auth"]["path"] = "/"
            # This auth cookie REALLY does not belong anywhere near an unsecured connection.
            # For some reason, empty strings seem to mean "Don't put this attribute in.
            # Always test, folks!
            try:
                cherrypy.response.cookie["kaithem_auth"]["SameSite"] = "Strict"
            except Exception:
                logging.exception("Cannot set samesite strict")

            # Over localhost, we can assume the connection is secure, and also that there can be no equivalent insecure connection,
            # Even if the browser thinks localhost is insecure for cookie purposes, for some reason.
            # This will not be secure if someone puts it behind an insecure a proxy that allows HTTP also/s
            ip = cherrypy.request.remote.ip
            if not pages.isHTTPAllowed(ip):
                cherrypy.response.cookie["kaithem_auth"]["secure"] = " "
            cherrypy.response.cookie["kaithem_auth"]["httponly"] = " "
            # Previously, tokens are good for 90 days
            # Now, just never expire, it might break kiosk applications.
            # cherrypy.response.cookie['kaithem_auth']['expires'] = 24 * 60 * 60 * 90
            x = auth.Users[kwargs["username"]]
            if not "loginhistory" in x:
                x["loginhistory"] = [(time.time(), cherrypy.request.remote.ip)]
            else:
                x["loginhistory"].append((time.time(), cherrypy.request.remote.ip))
                x["loginhistory"] = x["loginhistory"][:100]

            messagebus.post_message(
                "/system/auth/login", [kwargs["username"], cherrypy.request.remote.ip]
            )

            if "maxgotime" in kwargs:
                if time.time() > float(kwargs["maxgotime"]):
                    raise cherrypy.HTTPRedirect("/")
            try:
                dest = base64.b64decode(kwargs["go"]).decode()
            except:
                dest = "/index"

            if not "/errors/loginerror" in dest:
                raise cherrypy.HTTPRedirect(dest)
            else:
                raise cherrypy.HTTPRedirect("/index")
        else:
            onFail(cherrypy.request.remote.ip, kwargs["username"])
            messagebus.post_message(
                "/system/auth/loginfail",
                [kwargs["username"], cherrypy.request.remote.ip],
            )
            raise cherrypy.HTTPRedirect("/errors/loginerror")

    @cherrypy.expose
    def logout(self, **kwargs):
        # Change the security token to make the old one invalid and thus log user out.
        pages.postOnly()
        if cherrypy.request.cookie["kaithem_auth"].value in auth.Tokens:
            messagebus.post_message(
                "/system/auth/logout",
                [
                    auth.whoHasToken(cherrypy.request.cookie["kaithem_auth"].value),
                    cherrypy.request.remote.ip,
                ],
            )
            auth.assignNewToken(
                auth.whoHasToken(cherrypy.request.cookie["kaithem_auth"].value)
            )
        raise cherrypy.HTTPRedirect("/index")
