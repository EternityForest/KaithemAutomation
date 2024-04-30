# SPDX-FileCopyrightText: Copyright 2013 Daniel Dunn
# SPDX-License-Identifier: GPL-3.0-only


# This file handles the display of user-created pages
import copy
import gc
import importlib
import mimetypes
import os
import re
import threading
import time
import traceback
import types

import beartype
import cherrypy
import cherrypy.lib.static
import jinja2
import mako
import mako.template
import yaml

# import tornado.exceptions
from mako.lookup import TemplateLookup
from scullery import snake_compat

from kaithem.api.web import render_jinja_template
from kaithem.api.web.dialogs import SimpleDialog
from kaithem.src import auth, directories, messagebus, modules_state, pages, settings_overrides, theming, util
from kaithem.src.util import split_escape, url

_jl = jinja2.FileSystemLoader(
    [directories.htmldir, os.path.join(directories.htmldir, "jinjatemplates")],
    encoding="utf-8",
    followlinks=False,
)

env = jinja2.Environment(loader=_jl, autoescape=False)


errors = {}

_pages_by_module_resource = {}
_page_list_lock = threading.Lock()

# Used for including builtin components
component_lookup = TemplateLookup(
    directories=[
        directories.htmldir,
        os.path.join(directories.htmldir, "makocomponents"),
    ]
)


def markdownToSelfRenderingHTML(content, title):
    """Return self-rendering page body for markdown string"""

    x = (
        "<title>"
        + title
        + "</title>"
        + """
    <section id="content">
    """
        + content
        + """</section>
    <script src="/static/showdown.min.js"></script>
    <link rel="stylesheet" type="text/css" href="/static/css/atelier-dune-light.css">
    <script src="/static/js/thirdparty/highlight.pack.js"></script>
    <script>
    showdown.extension('codehighlight', function() {
    function htmlunencode(text) {
        return (
        text
            .replace(/&amp;/g, '&')
            .replace(/&lt;/g, '<')
            .replace(/&gt;/g, '>')
        );
    }
    return [
        {
        type: 'output',
        filter: function (text, converter, options) {
            // use new shodown's regexp engine to conditionally parse codeblocks
            var left  = '<pre><code\\\\b[^>]*>',
                right = '</code></pre>',
                flags = 'g',
                replacement = function (wholeMatch, match, left, right) {
                // unescape match to prevent double escaping
                match = htmlunencode(match);
                var lang = (left.match(/class=\\\"([^ \\\"]+)/) || [])[1];
                    left = left.slice(0, 18) + left.slice(18);
                    if (lang && hljs.getLanguage(lang)) {
                    return left + hljs.highlight(lang, match).value + right;
                    } else {
                    return left + hljs.highlightAuto(match).value + right;
                    }
                };
            return showdown.helper.replaceRecursiveRegExp(text, replacement, left, right, flags);
        }
        }
    ];
    });
    </script>
    <script>
    showdown.setFlavor('github');
    var c= document.getElementById("content").innerHTML;
    var converter = new showdown.Converter({metadata: true,extensions:['codehighlight']});

    document.getElementById("content").innerHTML=converter.makeHtml(c);
    </script>
    """
    )
    return x


@util.lrucache(50)
def lookup(module, args):
    resource_path = [i.replace("\\", "\\\\").replace("/", "\\/") for i in args]
    m = _pages_by_module_resource[module]

    if "/".join(resource_path) in m:
        return _pages_by_module_resource[module]["/".join(resource_path)]

    if "/".join(resource_path + ["__index__"]) in m:
        return _pages_by_module_resource[module]["/".join(resource_path + ["__index__"])]

    while resource_path:
        resource_path.pop()
        if "/".join(resource_path) in m:
            return _pages_by_module_resource[module]["/".join(resource_path)]

        if "/".join(resource_path + ["__index__"]) in m:
            return _pages_by_module_resource[module]["/".join(resource_path + ["__index__"])]

        if "/".join(resource_path + ["__default__"]) in m:
            return m["/".join(resource_path + ["__default__"])]
    return None


def url_for_resource(module, resource):
    s = f"/pages/{module}/{resource}"
    return s


class CompiledPageAPIObject:
    def __init__(self, p):
        self.page = p
        self.url = url_for_resource(p.module, p.resourceName)

    # def setContent(self, c):
    #     """This allows self-modifying pages, as many things
    #       are best edited directly.  The intended use is for
    #       replacing the contents of custom html-elements with
    #       a simple regex.

    #     One must be careful to use elements that actually
    #     can be replaced like that, which only have one instance.

    #     """

    #     pages.require("system_admin")
    #     pages.postOnly()

    #     if not isinstance(c, str):
    #         raise RuntimeError("Content must be a string")
    #     modules_state.modulesHaveChanged()

    #     self.page.resource["body"] = c
    #     self.page.refreshFromResource()

    #     modules_state.saveResource(self.page.module, self.page.resourceName, self.page.resource)

    # def getContent(self):
    #     return self.page.resource["body"]


class CompiledPage:
    def __init__(self, resource, m="unknown", r="unknown"):
        self.errors = []
        self.printoutput = ""

        self.resource = resource
        self.module = m
        self.name: str
        self.resourceName = r
        self.useJinja = False
        self.alt_top_banner: str | None
        self.code_obj: types.CodeType | None
        self.template: str | None | object
        self.scope: dict
        self.text: str
        self.mime: str
        self.xss: bool
        self.streaming: bool
        self.permissions: list[str]
        self.origins: list[str]
        self.methods: list[str]
        self.theme: str

        # This API is available as 'page' from within
        # Mako template code.   It's main use is for self modifying pages

        self.localAPI = CompiledPageAPIObject(self)
        from kaithem.src import kaithemobj

        self.kaithemobj = kaithemobj

        def refreshFromResource():
            # For compatibility with older versions, we provide defaults
            # In case some attributes are missing
            if "require_permissions" in resource:
                self.permissions = resource["require_permissions"]
            else:
                self.permissions = []

            self.theme = resource.get("theme_css_url", "")
            self.alt_top_banner = resource.get("alt_top_banner", "")

            if "allow_xss" in resource:
                self.xss = resource["allow_xss"]
            else:
                self.xss = False

            if "allow_origins" in resource:
                self.origins = resource["allow_origins"]
            else:
                self.origins = []

            if resource["resource_type"] == "page":
                template = resource["body"]

                code_header = ""

                self.streaming = resource.get("streaming-response", False)

                self.mime = resource.get("mimetype", "text/html") or "text/html"
                if "require_method" in resource:
                    self.methods = resource["require_method"]
                else:
                    self.methods = ["POST", "GET"]

                # Yes, I know this logic is ugly.
                if "no_navheader" in resource:
                    if resource["no_navheader"]:
                        header = util.readfile(
                            os.path.join(
                                directories.htmldir,
                                "makocomponents",
                                "pageheader_nonav.html",
                            )
                        )
                    else:
                        header = util.readfile(os.path.join(directories.htmldir, "makocomponents", "pageheader.html"))
                else:
                    header = util.readfile(os.path.join(directories.htmldir, "makocomponents", "pageheader.html"))

                if "no_header" in resource:
                    if resource["no_header"]:
                        header = ""

                if "no_header" not in resource or not (resource["no_header"]):
                    footer = util.readfile(os.path.join(directories.htmldir, "makocomponents", "pagefooter.html"))
                else:
                    footer = ""

                self.scope = {
                    "kaithem": self.kaithemobj.kaithem,
                    "page": self.localAPI,
                    "print": self.new_print,
                    "_k_alt_top_banner": self.alt_top_banner,
                    "imp0rt": importlib.import_module,
                }
                if m in modules_state.scopes:
                    self.scope["module"] = modules_state.scopes[m]

                if "template_engine" not in resource or resource["template_engine"] == "mako":
                    # Add in the separate code

                    usejson = False

                    if "setupcode" in resource and resource["setupcode"].strip():
                        code_header += f"\n<%!\n{resource['setupcode']}\n%>\n"
                        usejson = True

                    if "code" in resource and resource["code"].strip():
                        code_header += f"\n<%\n{resource['code']}\n%>\n"
                        usejson = True

                    if usejson:
                        header += "\n<%!\nimport json\n%>\n"

                        # Don't embed a script if this *is* already a script
                        if not self.resourceName.endswith(".js"):
                            header += "<script>\n"

                        header += """
                        // Autogenerated by kaithem
                        %if not __jsvars__ == undefined:
                        %for i in __jsvars__:
                        ${i} = ${json.dumps(__jsvars__[i])}
                        %endfor
                        %endif

                        """

                        if not self.resourceName.endswith(".js"):
                            header += "</script>\n"

                            header += """
                            %if not __datalists__ == undefined:
                            %for i in __datalists__:
                            <datalist id="${i}">
                            %for i in __datalists__[i]:
                            <option title="${i.get('title','')}" value="${i['value']}">${i.get('option','')}</option>
                            %endfor
                            </datalist>
                            %endfor
                            %endif

                            """

                    templatesource = code_header + header + template + footer

                    self.template = mako.template.Template(
                        templatesource,
                        uri=f"Template{m}_{r}",
                        lookup=component_lookup,
                    )

                elif resource["template_engine"] == "jinja2":
                    if "setupcode" in resource and resource["setupcode"].strip():
                        exec(resource["setupcode"], self.scope, self.scope)
                    if "code" in resource and resource["code"].strip():
                        self.code_obj = compile(resource["code"], "Jinja2Page", mode="exec")
                    else:
                        self.code_obj = None

                    self.template = env.from_string(template)
                    self.useJinja = True

                elif resource["template_engine"] == "markdown":
                    header = mako.template.Template(header, uri=f"Template{m}_{r}", lookup=component_lookup).render(**self.scope)
                    footer = mako.template.Template(footer, uri=f"Template{m}_{r}", lookup=component_lookup).render(**self.scope)

                    self.text = str(header) + "\r\n" + markdownToSelfRenderingHTML(template, r) + footer
                else:
                    self.text = template

        self.refreshFromResource = refreshFromResource
        self.refreshFromResource()

    def new_print(self, *d):
        try:
            if len(d) == 1:
                self.printoutput += f"{str(d[0])}\n"
            else:
                self.printoutput += str(d)
        except Exception:
            self.printoutput += repr(d)
        self.printoutput = self.printoutput[-2500:]


def getPageErrors(module, resource):
    try:
        return _pages_by_module_resource[module][resource].errors
    except KeyError:
        return (
            0,
            "No Error list available for page that was not compiled or loaded",
            "Page has not been compiled or loaded and does not exist in compiled page list",
        )


def getPageOutput(module, resource):
    try:
        return _pages_by_module_resource[module][resource].printoutput
    except KeyError:
        return (
            0,
            "No Error list available for page that was not compiled or loaded",
            "Page has not been compiled or loaded and does not exist in compiled page list",
        )


def getPageHTMLDoc(m, r):
    try:
        if hasattr(_pages_by_module_resource[m][r].template.module, "__html_doc__"):
            return str(_pages_by_module_resource[m][r].template.module.__html_doc__)
    except Exception:
        pass


def getPageInfo(module, resource):
    # There's enough possible trouble with new kinds of events and users stuffing bizzare things
    # in there that i'm Putting this in a try block.
    try:
        return _pages_by_module_resource[module][resource].template.module.__doc__ or ""
    except Exception:
        return ""


# Delete a event from the cache by module and resource


def removeOnePage(module, resource):
    # Look up the eb
    with _page_list_lock:
        if module in _pages_by_module_resource:
            if resource in _pages_by_module_resource[module]:
                del _pages_by_module_resource[module][resource]
    gc.collect()
    lookup.invalidate_cache()


# Delete all __events in a module from the cache
def removeModulePages(module):
    # There might not be any pages, so we use the if
    if module in _pages_by_module_resource:
        del _pages_by_module_resource[module]
    gc.collect()
    lookup.invalidate_cache()


# This piece of code will update the actual event object based on the event resource definition in the module
# Also can add a new page
def updateOnePage(resource, module, data: modules_state.ResourceDictType):
    # This is one of those places that uses two different locks
    with modules_state.modulesLock:
        if module not in _pages_by_module_resource:
            _pages_by_module_resource[module] = {}

        # Delete the old version if present
        try:
            del _pages_by_module_resource[module][resource]
            gc.collect()
            time.sleep(0.125)
            gc.collect()
        except Exception:
            pass

        enable = True

        # Don't serve file if that's not enabled
        if enable:
            _pages_by_module_resource[module][resource] = CompiledPage(data, module, resource)
        lookup.invalidate_cache()


def makeDummyPage(resource, module):
    if module not in _pages_by_module_resource:
        _pages_by_module_resource[module] = {}

    # Get the page resource in question
    j = {"resource_type": "page", "body": "Content here", "no_navheader": True}
    _pages_by_module_resource[module][resource] = CompiledPage(j, module, resource)


# look in the modules and compile all the event code
def getPagesFromModules():
    with modules_state.modulesLock:
        with _page_list_lock:
            # Set __events to an empty list we can build on
            _pages_by_module_resource.clear()
            for i in modules_state.ActiveModules.copy():
                # For each loaded and active module, we make a subdict in _Pages
                _pages_by_module_resource[i] = {}  # make an empty place for pages in this module
                # now we loop over all the resources o the module to see which ones are pages
                for m in modules_state.ActiveModules[i].copy():
                    j = modules_state.ActiveModules[i][m]
                    if j["resource_type"] == "page":
                        try:
                            _pages_by_module_resource[i][m] = CompiledPage(j, i, m)
                        except Exception:
                            makeDummyPage(m, i)
                            tb = traceback.format_exc(chain=True)
                            # When an error happens, log it and save the time
                            # Note that we are logging to the compiled event object
                            _pages_by_module_resource[i][m].errors.append(
                                [
                                    time.strftime(settings_overrides.get_val("core/strftime_string")),
                                    tb,
                                    "Error while initializing",
                                ]
                            )
                            try:
                                messagebus.post_message(f"system/errors/pages/{i}/{m}", str(tb))
                            except Exception as e:
                                print(e)
                            # Keep only the most recent 25 errors

                            # If this is the first error(high level: transition from ok to not ok)
                            # send a global system messsage that will go to the front page.
                            if len(_pages_by_module_resource[i][m].errors) == 1:
                                messagebus.post_message(
                                    "/system/notifications/errors",
                                    'Page "' + m + '" of module "' + i + '" may need attention',
                                )
                        else:
                            try:
                                del _pages_by_module_resource[i][m]
                            except KeyError:
                                pass

    lookup.invalidate_cache()


def streamGen(e):
    while 1:
        x = e.read(4096)
        if not x:
            return
        yield x


# kaithem.py has come config option that cause this file to use the method dispatcher.
class KaithemPage:
    # Class encapsulating one request to a user-defined page
    exposed = True

    def __init__(self) -> None:
        from ... import kaithemobj

        self.kaithemobj = kaithemobj

    def GET(self, module, *args, **kwargs):
        # Workaround for cherrypy decoding unicode as if it is latin 1
        # Because of some bizzare wsgi thing i think.
        module = module.encode("latin-1").decode("utf-8")
        args = [i.encode("latin-1").decode("utf-8") for i in args]
        return self._serve(module, *args, **kwargs)

    def POST(self, module, *args, **kwargs):
        # Workaround for cherrypy decoding unicode as if it is latin 1
        # Because of some bizzare wsgi thing i think.
        module = module.encode("latin-1").decode("utf-8")
        args = [i.encode("latin-1").decode("utf-8") for i in args]
        return self._serve(module, *args, **kwargs)

    def OPTION(self, module, resource, *args, **kwargs):
        # Workaround for cherrypy decoding unicode as if it is latin 1
        # Because of some bizzare wsgi thing i think.
        module = module.encode("latin-1").decode("utf-8")
        args = [i.encode("latin-1").decode("utf-8") for i in args]
        self._headers(lookup(module, args))
        return ""

    def _headers(self, page):
        x = ""
        for i in page.methods:
            x += f"{i}, "
        x = x[:-2]

        cherrypy.response.headers["Allow"] = f"{x}, HEAD, OPTIONS"
        if page.xss:
            if "Origin" in cherrypy.request.headers:
                if cherrypy.request.headers["Origin"] in page.origins or "*" in page.origins:
                    cherrypy.response.headers["Access-Control-Allow-Origin"] = cherrypy.request.headers["Origin"]
                cherrypy.response.headers["Access-Control-Allow-Methods"] = x

    def _serve(self, module, *args, **kwargs):
        page = lookup(module, args)

        if page is None:
            messagebus.post_message(
                "/system/errors/http/nonexistant",
                f"Someone tried to access a page that did not exist in module {module} with path {args}",
            )
            rn = "/".join(args)
            x = modules_state.ActiveModules[module].get(rn, None)

            if x and x["resource_type"] == "internal_fileref":
                fn = modules_state.fileResourceAbsPaths[module, rn]
                mime = str(x.get("mimetype", "").strip() or mimetypes.guess_type(fn)[0])  # type: ignore
                if x.get("serve", False):
                    pages.require(x.get("require_permissions", []))
                    if "Origin" in cherrypy.request.headers:
                        origins: list[str] = x["allow_origins"]  # type: ignore

                        if not x["allow_xss"]:
                            raise RuntimeError("Refusing XSS")

                        if not (cherrypy.request.headers["Origin"] in origins or "*" in origins):
                            raise RuntimeError("Refusing XSS from this origin: " + cherrypy.request.headers["Origin"])
                        else:
                            cherrypy.response.headers["Access-Control-Allow-Origin"] = cherrypy.request.headers["Origin"]

                    return cherrypy.lib.static.serve_file(
                        fn,
                        mime,
                        os.path.basename(fn),
                    )
            raise cherrypy.NotFound()

        if "Origin" in cherrypy.request.headers:
            if not page.xss:
                raise RuntimeError("Refusing XSS")
            if not (cherrypy.request.headers["Origin"] in page.origins or "*" in page.origins):
                raise RuntimeError("Refusing XSS from this origin: " + cherrypy.request.headers["Origin"])
            else:
                cherrypy.response.headers["Access-Control-Allow-Origin"] = cherrypy.request.headers["Origin"]

        x = ""
        for i in page.methods:
            x += f"{i}, "
        x = x[:-2]
        cherrypy.response.headers["Access-Control-Allow-Methods"] = x

        page.lastaccessed = time.time()
        # Check user permissions
        for i in page.permissions:
            pages.require(i)

        self._headers(page)
        # Check HTTP Method
        if cherrypy.request.method not in page.methods:
            # Raise a redirect the the wrongmethod error page
            raise cherrypy.HTTPRedirect("/errors/wrongmethod")
        try:
            cherrypy.response.headers["Content-Type"] = page.mime

            t = page.theme
            if t in theming.cssthemes:
                t = theming.cssthemes[t].css_url

            if hasattr(page, "template"):
                s = {
                    "kaithem": self.kaithemobj.kaithem,
                    "request": cherrypy.request,
                    "module": modules_state.scopes[module],
                    "path": args,
                    "kwargs": kwargs,
                    "print": page.new_print,
                    "page": page.localAPI,
                    "_k_usr_page_theme": t,
                    "_k_alt_top_banner": page.alt_top_banner,
                }
                if not page.useJinja:
                    return page.template.render(**s).encode("utf-8")
                else:
                    s.update(page.scope)

                    if page.code_obj:
                        exec(page.code_obj, s, s)

                    return page.template.render(**s)

            else:
                return page.text.encode("utf-8")

        except self.kaithemobj.ServeFileInsteadOfRenderingPageException as e:
            if page.streaming and hasattr(e.f_filepath, "read"):
                cherrypy.response.headers["Content-Type"] = e.f_MIME
                cherrypy.response.headers["Content-Disposition"] = f'attachment ; filename = "{e.f_name}"'
                return streamGen(e.f_filepath)

            if hasattr(e.f_filepath, "getvalue"):
                cherrypy.response.headers["Content-Type"] = e.f_MIME
                cherrypy.response.headers["Content-Disposition"] = f'attachment ; filename = "{e.f_name}"'
                return e.f_filepath.getvalue()

            return cherrypy.lib.static.serve_file(e.f_filepath, e.f_MIME, e.f_name)

        except Exception as e:
            # The HTTPRedirect is NOT an error, and should not be handled like one.
            # So we just reraise it unchanged
            if isinstance(e, cherrypy.HTTPRedirect):
                raise e

            # The way we let users securely serve static files is to simply
            # Give them a function that raises this special exception
            if isinstance(e, self.kaithemobj.ServeFileInsteadOfRenderingPageException):
                return cherrypy.lib.static.serve_file(e.f_filepath, e.f_MIME, e.f_name)

            tb = traceback.format_exc(chain=True)
            # tb = tornado.exceptions.text_error_template().render()
            data = (
                "Request from: " + cherrypy.request.remote.ip + "(" + pages.getAcessingUser() + ")\n" + cherrypy.request.request_line + "\n"
            )
            # When an error happens, log it and save the time
            # Note that we are logging to the compiled event object
            page.errors.append([time.strftime(settings_overrides.get_val("core/strftime_string")), tb, data])
            try:
                messagebus.post_message(f"system/errors/pages/{module}/{'/'.join(args)}", str(tb))
            except Exception as e:
                print(e)
            # Keep only the most recent 25 errors

            # If this is the first error(high level: transition from ok to not ok)
            # send a global system messsage that will go to the front page.
            if len(page.errors) == 1:
                messagebus.post_message(
                    "/system/notifications/errors",
                    'Page "' + "/".join(args) + '" of module "' + module + '" may need attention',
                )
            raise (e)


def rsc_from_html(fn: str):
    with open(fn) as f:
        d = f.read()

    # This regex is meant to handle any combination of cr, lf, and trailing whitespaces
    # We don't do anything with more that 3 sections yet, so limit just in case there's ----
    # in a markdown file
    sections = re.split(r"\r?\n?----*\s*\r?\n*", d, 2)

    # Markdown and most html files files start with --- and are delimited by ---
    # The first section is YAML and the second is the page body.
    data = yaml.load(sections[1], Loader=yaml.SafeLoader)
    data["body"] = sections[2]
    data = snake_compat.snakify_dict_keys(data)

    return data


with open(os.path.join(os.path.dirname(__file__), "page_schema.yaml")) as f:
    schema = yaml.load(f, yaml.SafeLoader)


class PageType(modules_state.ResourceType):
    def to_files(
        self,
        name: str,
        resource: modules_state.ResourceDictType,
    ) -> dict[str, str]:
        resource = copy.copy(resource)

        d: str

        name = name.split("/")[-1]

        if resource.get("template_engine", "") == "markdown":
            b = resource["body"]
            del resource["body"]
            d = "---\n" + yaml.dump(resource) + "\n---\n" + b

            return {f"{name}.md": d}
        else:
            b = resource["body"]
            del resource["body"]
            d = "---\n" + yaml.dump(resource) + "\n---\n" + b
            return {f"{name}.html": d}

    def scan_dir(
        self, dir: str
    ) -> dict[str, dict[str, str | list | int | float | bool | dict[str, dict | list | int | float | str | bool | None] | None]]:
        r = {}

        for i in os.listdir(dir):
            if i.split(".", 1)[-1] in ("html", "md"):
                r[i[:-5]] = rsc_from_html(os.path.join(dir, i))

        return r

    def blurb(self, m, r, value):
        return render_jinja_template(
            os.path.join(os.path.dirname(__file__), "html", "page_blurb.j2.html"),
            getPageErrors=getPageErrors,
            getPageInfo=getPageInfo,
            resource=value,
            url_for_resource=url_for_resource,
            modulename=m,
            resourcename=r,
            len=len,
        )

    @beartype.beartype
    def onload(self, module: str, resourcename: str, value: modules_state.ResourceDictType):
        updateOnePage(resourcename, module, value)

    def onmove(self, module, resource, toModule, toResource, resourceobj):
        x = _pages_by_module_resource.pop((module, resource), None)
        if x:
            _pages_by_module_resource[toModule, toResource] = x

    def onupdate(self, module, resource, obj):
        self.onload(module, resource, obj)

    def ondelete(self, module, name, value):
        removeOnePage(module, name)

    def oncreaterequest(self, module, name, kwargs):
        from . import pageresourcetemplates

        template = kwargs["template"]
        return pageresourcetemplates.templates[template](name)

    def onupdaterequest(self, module, resource, resourceobj, kwargs):
        if "tabtospace" in kwargs:
            body = kwargs["body"].replace("\t", "    ")
        else:
            body = kwargs["body"]

        if "tabtospace" in kwargs:
            code = kwargs["code"].replace("\t", "    ")
        else:
            code = kwargs["code"]

        if "tabtospace" in kwargs:
            setupcode = kwargs["setupcode"].replace("\t", "    ")
        else:
            setupcode = kwargs["setupcode"]

        resourceobj["body"] = body
        resourceobj["theme_css_url"] = kwargs["themecss"].strip()
        resourceobj["code"] = code
        resourceobj["setupcode"] = setupcode
        resourceobj["alt_top_banner"] = kwargs["alttopbanner"]

        resourceobj["mimetype"] = kwargs["mimetype"]
        resourceobj["template_engine"] = kwargs["template_engine"]
        resourceobj["no_navheader"] = "nonavheader" in kwargs
        resourceobj["streaming_response"] = "streaming_response" in kwargs

        resourceobj["no_header"] = "no_header" in kwargs
        resourceobj["allow_xss"] = "allow_xss" in kwargs
        resourceobj["allow_origins"] = [i.strip() for i in kwargs["allow_origins"].split(",")]
        # Method checkboxes
        resourceobj["require_method"] = []
        if "allow-GET" in kwargs:
            resourceobj["require_method"].append("GET")
        if "allow-POST" in kwargs:
            resourceobj["require_method"].append("POST")
        # permission checkboxes
        resourceobj["require_permissions"] = []
        for i in kwargs:
            # Since HTTP args don't have namespaces we prefix all the permission
            # checkboxes with permission
            if i[:10] == "Permission":
                if kwargs[i] == "true":
                    resourceobj["require_permissions"].append(i[10:])

        return resourceobj

    def createpage(self, module, path):
        d = SimpleDialog(f"New page in {module}")
        d.text_input("name")
        d.selection("template", options=["default"])

        d.submit_button("Create")
        return d.render(f"/modules/module/{url(module)}/addresourcetarget/{self.type}/{url(path)}")

    def editpage(self, module, resource, resourceinquestion):
        if "require_permissions" in resourceinquestion:
            requiredpermissions = resourceinquestion["require_permissions"]
        else:
            requiredpermissions = []

        return pages.get_template(os.path.join(os.path.dirname(__file__), "html", "page.html")).render(
            module=module,
            name=resource,
            kwargs={},
            page=resourceinquestion,
            requiredpermissions=requiredpermissions,
            split_escape=split_escape,
            url=util.url,
            theming=theming,
            can_edit=pages.canUserDoThis("system_admin"),
            can_view_admin=pages.canUserDoThis("view_admin_info"),
            getPageErrors=getPageErrors,
            getPageOutput=getPageOutput,
            url_for_resource=url_for_resource,
            all_perms=auth.Permissions.keys(),
        )


p = PageType("page", mdi_icon="web", schema=schema)
modules_state.additionalTypes["page"] = p
