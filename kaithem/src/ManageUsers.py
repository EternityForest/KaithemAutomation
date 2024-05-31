# SPDX-FileCopyrightText: Copyright 2013 Daniel Dunn
# SPDX-License-Identifier: GPL-3.0-only

"""Provides a web interface over the authorization system"""

import cherrypy
import quart

from . import auth, dialogs, messagebus, pages, quart_app
from .util import quote


class ManageAuthorization:
    @quart_app.app.route("/auth")
    def index(self):
        try:
            pages.require("system_admin")
        except PermissionError:
            return pages.loginredirect(pages.geturl())
        cherrypy.response.headers["X-Frame-Options"] = "SAMEORIGIN"
        return pages.get_template("auth/index.html").render(auth=auth)

    # The actual POST target to delete a user
    @quart_app.app.route("/auth/deluser", methods=["POST"])
    async def deluser(self):
        kwargs = await quart.request.form
        try:
            pages.require("system_admin")
        except PermissionError:
            return pages.loginredirect(pages.geturl())
        auth.removeUser(kwargs["user"])
        messagebus.post_message(
            "/system/auth/user/deleted",
            {"user": kwargs["user"], "deletedby": pages.getAcessingUser()},
        )
        return quart.redirect("/auth")

    # POST target for deleting a group
    @quart_app.app.route("/auth/delgroup", methods=["POST"])
    async def delgroup(self):
        kwargs = await quart.request.form
        try:
            pages.require("system_admin")
        except PermissionError:
            return pages.loginredirect(pages.geturl())

        auth.removeGroup(kwargs["group"])
        messagebus.post_message(
            "/system/auth/group/deleted",
            {"group": kwargs["group"], "deletedby": pages.getAcessingUser()},
        )
        return quart.redirect("/auth")

    # INterface to select a user to delete
    @quart_app.app.route("/auth/deleteuser")
    async def deleteuser(self):
        try:
            pages.require("system_admin")
        except PermissionError:
            return pages.loginredirect(pages.geturl())
        cherrypy.response.headers["X-Frame-Options"] = "SAMEORIGIN"
        d = dialogs.SimpleDialog("Delete User")
        d.text_input("user")
        d.submit_button("Delete")

        return d.render("/auth/deluser")

    # Interface to select a group to delete
    @quart_app.app.route("/auth/deletegroup")
    async def deletegroup(self):
        try:
            pages.require("system_admin")
        except PermissionError:
            return pages.loginredirect(pages.geturl())
        cherrypy.response.headers["X-Frame-Options"] = "SAMEORIGIN"
        return pages.get_template("auth/deletegroup.html").render()

    # Add user interface
    @quart_app.app.route("/auth/newuser")
    def newuser(self):
        try:
            pages.require("system_admin")
        except PermissionError:
            return pages.loginredirect(pages.geturl())
        d = dialogs.SimpleDialog("Add New User")
        d.text_input("username")
        d.text_input("password")
        d.checkbox("useSystemPassword", title="Use Linux User Password")

        d.submit_button("Submit")

        cherrypy.response.headers["X-Frame-Options"] = "SAMEORIGIN"
        return d.render("/auth/newusertarget")

    # add group interface
    @quart_app.app.route("/auth/newgroup")
    def newgroup(self):
        try:
            pages.require("system_admin")
        except PermissionError:
            return pages.loginredirect(pages.geturl())
        cherrypy.response.headers["X-Frame-Options"] = "SAMEORIGIN"

        return pages.get_template("auth/newgroup.html").render()

    @quart_app.app.route("/auth/newusertarget", methods=["POST"])
    # handler for the POST request to change user settings
    async def newusertarget(self):
        kwargs = await quart.request.form
        # THIS IS A HACK TO PREVENT UNICODE STRINGS IN PY2.XX FROM GETTING THROUGH
        # BECAUSE QUOTE() IS USUALLY WHERE THEY CRASH. #AWFULHACK
        quote(kwargs["username"])
        try:
            pages.require("system_admin")
        except PermissionError:
            return pages.loginredirect("/")
        # create the new user
        auth.addUser(
            kwargs["username"],
            kwargs["password"],
            useSystem="useSystemPassword" in kwargs,
        )
        # Take the user back to the users page
        messagebus.post_message("/system/notifications", 'New user "' + kwargs["username"] + '" added')
        messagebus.post_message(
            "/system/auth/user/added",
            {"user": kwargs["username"], "addedby": pages.getAcessingUser()},
        )

        return quart.redirect("/auth/")

    @quart_app.app.route("/auth/newgrouptarget", methods=["POST"])
    # handler for the POST request to change user settings
    async def newgrouptarget(self):
        kwargs = await quart.request.form
        # THIS IS A HACK TO PREVENT UNICODE STRINGS IN PY2.XX FROM GETTING THROUGH
        # BECAUSE QUOTE() IS USUALLY WHERE THEY CRASH. #AWFULHACK
        quote(kwargs["groupname"])
        try:
            pages.require("system_admin")
        except PermissionError:
            return pages.loginredirect("/")
        pages.postOnly()
        # create the new user
        auth.addGroup(kwargs["groupname"])
        messagebus.post_message(
            "/system/auth/group/added",
            {"group": kwargs["groupname"], "addedby": pages.getAcessingUser()},
        )

        # Take the user back to the users page
        return quart.redirect("/auth/")

    @quart_app.app.route("/auth/updateuser/<user>", methods=["POST"])
    # handler for the POST request to change user settings
    async def updateuser(self, user):
        kwargs = await quart.request.form

        try:
            pages.require("system_admin")
        except PermissionError:
            return pages.loginredirect(pages.geturl())

        useSystem = "useSystemPassword" in kwargs

        user = user.encode("latin-1").decode("utf-8")
        # THIS IS A HACK TO PREVENT UNICODE STRINGS IN PY2.XX FROM GETTING THROUGH
        # BECAUSE QUOTE() IS USUALLY WHERE THEY CRASH. #AWFULHACK
        quote(kwargs["username"])

        if not useSystem:
            if not kwargs["password"] == kwargs["password2"]:
                raise RuntimeError("passwords must match")

            if auth.Users[user].get("password") == "system":
                if not kwargs["password"]:
                    raise ValueError("Must specify a password to disable the system password feature")

        # Remove the user from all groups that the checkbox was not checked for
        for i in auth.Users[user]["groups"]:
            if ("Group" + i) not in kwargs:
                auth.removeUserFromGroup(user, i)

        # Add the user to all checked groups
        for i in kwargs:
            if i[:5] == "Group":
                if kwargs[i] == "true":
                    auth.addUserToGroup(user, i[5:])

        if (not kwargs["password"] == "") or useSystem:
            auth.changePassword(user, kwargs["password"], useSystem=useSystem)

        auth.setUserSetting(pages.getAcessingUser(), "allow-cors", "allowcors" in kwargs)
        auth.setUserSetting(user, "restrict-lan", "lanonly" in kwargs)
        auth.setUserSetting(user, "telemetry-alerts", "telemetryalerts" in kwargs)

        auth.changeUsername(user, kwargs["username"])

        messagebus.post_message(
            "/system/auth/user/modified",
            {"user": user, "modifiedby": pages.getAcessingUser()},
        )
        # Take the user back to the users page
        return quart.redirect("/auth")

    @quart_app.app.route("/auth/updategroup/<group>", methods=["POST"])
    # handler for the POST request to change user settings
    async def updategroup(self, group):
        kwargs = await quart.request.form

        try:
            pages.require("system_admin")
        except PermissionError:
            return pages.loginredirect(pages.geturl())
        pages.postOnly()
        group = group.encode("latin-1").decode("utf-8")

        auth.Groups[group]["permissions"] = []
        # Handle all the group permission checkboxes
        for i in kwargs:
            # Since HTTP args don't have namespaces we prefix all the permission checkboxes with permission
            if i[:10] == "Permission":
                if kwargs[i] == "true":
                    auth.addGroupPermission(group, i[10:])

        auth.setGroupLimit(group, "web.maxbytes", int(kwargs["maxbytes"]))

        # Take the user back to the users page
        auth.generateUserPermissions()  # update all users to have the new permissions lists
        messagebus.post_message(
            "/system/auth/group/changed",
            {"group": group, "changedby": pages.getAcessingUser()},
        )

        return quart.redirect("/auth")

    # Settings page for one individual user
    @quart_app.app.route("/auth/user/<username>", methods=["POST"])
    def user(self, username):
        # kwargs = await quart.request.form

        username = username.encode("latin-1").decode("utf-8")
        try:
            pages.require("system_admin")
        except PermissionError:
            return pages.loginredirect(pages.geturl())
        cherrypy.response.headers["X-Frame-Options"] = "SAMEORIGIN"

        return pages.get_template("auth/user.html").render(
            usergroups=auth.Users[username]["groups"],
            groups=sorted(auth.Groups.keys()),
            username=username,
        )

    # Settings page for one individual group
    @cherrypy.expose
    def group(self, group):
        group = group.encode("latin-1").decode("utf-8")
        try:
            pages.require("system_admin")
        except PermissionError:
            return pages.loginredirect(pages.geturl())
        cherrypy.response.headers["X-Frame-Options"] = "SAMEORIGIN"
        return pages.get_template("auth/group.html").render(auth=auth, name=group)
