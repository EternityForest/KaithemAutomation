# Copyright Daniel Dunn 2013
# This file is part of Kaithem Automation.

# Kaithem Automation is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, version 3.

# Kaithem Automation is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with Kaithem Automation.  If not, see <http://www.gnu.org/licenses/>.


# This file handles the display of user-created pages
import time
import os
import threading
import traceback
import gc
import mimetypes

from attr import has
from . import util, pages, directories, messagebus, systasks, modules_state, theming
import mako
import cherrypy
import tornado
import sys
import importlib
import jinja2

from .config import config

from mako.lookup import TemplateLookup


_jl = jinja2.FileSystemLoader([directories.htmldir, os.path.join(
    directories.htmldir, "jinjatemplates")], encoding='utf-8', followlinks=False)

env = jinja2.Environment(
    loader=_jl,
    autoescape=False
)


errors = {}

# Used for including builtin components
component_lookup = TemplateLookup(directories=[
                                  directories.htmldir, os.path.join(directories.htmldir, "makocomponents")])


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
    m = _Pages[module]
    if "/".join(resource_path) in m:
        return _Pages[module]["/".join(resource_path)]

    if "/".join(resource_path + ["__index__"]) in m:
        return _Pages[module]["/".join(resource_path + ["__index__"])]

    while resource_path:
        resource_path.pop()
        if "/".join(resource_path) in m:
            return _Pages[module]["/".join(resource_path)]

        if "/".join(resource_path + ["__index__"]) in m:
            return _Pages[module]["/".join(resource_path + ["__index__"])]

        if "/".join(resource_path + ["__default__"]) in m:
            return m["/".join(resource_path + ["__default__"])]
    return None


def url_for_resource(module, resource):
    s = "/pages/"
    s += util.url(module)
    s += "/"
    s += "/".join([util.url(i) for i in util.split_escape(resource, "/")])
    return s


class CompiledPageAPIObject:
    def __init__(self, p):
        self.page = p
        self.url = url_for_resource(p.module, p.resourceName)

    def setContent(self, c):
        """This allows self-modifying pages, as many things are best edited directly.  The intended use is for replacing the contents of custom html-elements with a simple regex.
        One must be careful to use elements that actually can be replaced like that, which only have one instance.

        """

        pages.require("system_admin")
        pages.postOnly()

        if not isinstance(c, str):
            raise RuntimeError("Content must be a string")
        modules_state.modulesHaveChanged()

        self.page.resource["body"] = c
        self.page.refreshFromResource()

        modules_state.saveResource(
            self.page.module, self.page.resourceName, self.page.resource
        )

    def getContent(self):
        return self.page.resource["body"]


class CompiledPage:
    def __init__(self, resource, m="unknown", r="unknown"):
        self.errors = []
        self.printoutput = ""

        self.resource = resource
        self.module = m
        self.resourceName = r
        self.useJinja = False

        # This API is available as 'page' from within
        # Mako template code.   It's main use is for self modifying pages, mostly just for implementing
        # FreeBoard.

        self.localAPI = CompiledPageAPIObject(self)
        from . import kaithemobj

        self.kaithemobj = kaithemobj

        def refreshFromResource():
            # For compatibility with older versions, we provide defaults
            # In case some attributes are missing
            if "require-permissions" in resource:
                self.permissions = resource["require-permissions"]
            else:
                self.permissions = []

            self.theme = resource.get("theme-css-url", "")
            self.alt_top_banner = resource.get("alt-top-banner", "")

            if "allow-xss" in resource:
                self.xss = resource["allow-xss"]
            else:
                self.xss = False

            if "allow-origins" in resource:
                self.origins = resource["allow-origins"]
            else:
                self.origins = []

            self.directServeFile = None

            if resource["resource-type"] == "page":
                template = resource["body"]

                code_header = ""

                self.streaming = resource.get("streaming-response", False)

                self.mime = resource.get(
                    "mimetype", "text/html") or "text/html"
                if "require-method" in resource:
                    self.methods = resource["require-method"]
                else:
                    self.methods = ["POST", "GET"]

                # Yes, I know this logic is ugly.
                if "no-navheader" in resource:
                    if resource["no-navheader"]:
                        header = util.readfile(
                            os.path.join(directories.htmldir, 'makocomponents',
                                         "pageheader_nonav.html")
                        )
                    else:
                        header = util.readfile(
                            os.path.join(directories.htmldir, 'makocomponents',
                                         "pageheader.html")
                        )
                else:
                    header = util.readfile(
                        os.path.join(directories.htmldir,
                                     'makocomponents', "pageheader.html")
                    )

                if "no-header" in resource:
                    if resource["no-header"]:
                        header = ""

                if "auto-reload" in resource:
                    if resource["auto-reload"]:
                        header += (
                            '<meta http-equiv="refresh" content="%d">'
                            % resource["auto-reload-interval"]
                        )

                if not ("no-header" in resource) or not (resource["no-header"]):
                    footer = util.readfile(
                        os.path.join(directories.htmldir,
                                     'makocomponents', "pagefooter.html")
                    )
                else:
                    footer = ""

                self.scope = {
                    "kaithem": self.kaithemobj.kaithem,
                    "page": self.localAPI,
                    "print": self.new_print,
                    "_k_alt_top_banner": self.alt_top_banner,
                    "imp0rt": importlib.import_module
                }
                if m in modules_state.scopes:
                    self.scope["module"] = modules_state.scopes[m]

                if (
                    not "template-engine" in resource
                    or resource["template-engine"] == "mako"
                ):
                    # Add in the separate code

                    usejson = False

                    if "setupcode" in resource and resource["setupcode"].strip():
                        code_header += "\n<%!\n" + \
                            resource["setupcode"] + "\n%>\n"
                        usejson = True

                    if "code" in resource and resource["code"].strip():
                        code_header += "\n<%\n" + resource["code"] + "\n%>\n"
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
                        templatesource, uri="Template" + m + "_" + r, lookup=component_lookup)

                elif resource['template-engine'] == 'jinja2':
                    if "setupcode" in resource and resource["setupcode"].strip():
                        exec(resource['setupcode'], None, self.scope)
                    if "code" in resource and resource["code"].strip():
                        self.code_obj = compile(resource['code'],"Jinja2Page", mode="exec")
                    else:
                        self.code_obj = None

                    self.template = env.from_string(template)
                    self.useJinja = True

                elif resource["template-engine"] == "markdown":
                    header = mako.template.Template(
                        header, uri="Template" + m + "_" + r, lookup=component_lookup).render(**self.scope)
                    footer = mako.template.Template(
                        footer, uri="Template" + m + "_" + r, lookup=component_lookup).render(**self.scope)

                    self.text = (
                        header
                        + "\r\n"
                        + markdownToSelfRenderingHTML(template, r)
                        + footer
                    )
                else:
                    self.text = template

            elif resource["resource-type"] == "internal-fileref":
                self.methods = ["GET"]
                self.name = os.path.basename(
                    modules_state.fileResourceAbsPaths[m, r])

                self.directServeFile = modules_state.fileResourceAbsPaths[m, r]
                self.mime = self.mime = resource.get(
                    "mimetype", ''
                ).strip() or mimetypes.guess_type(self.name)[0]

        self.refreshFromResource = refreshFromResource
        self.refreshFromResource()

    def new_print(self, *d):
        try:
            if len(d) == 1:
                self.printoutput += str(d[0]) + "\n"
            else:
                self.printoutput += str(d)
        except:
            self.printoutput += repr(d)
        self.printoutput = self.printoutput[-2500:]


def getPageErrors(module, resource):
    try:
        return _Pages[module][resource].errors
    except KeyError:
        return (
            0,
            "No Error list available for page that was not compiled or loaded",
            "Page has not been compiled or loaded and does not exist in compiled page list",
        )


def getPageOutput(module, resource):
    try:
        return _Pages[module][resource].printoutput
    except KeyError:
        return (
            0,
            "No Error list available for page that was not compiled or loaded",
            "Page has not been compiled or loaded and does not exist in compiled page list",
        )


_Pages = {}
_page_list_lock = threading.Lock()


def getPageHTMLDoc(m, r):
    try:
        if hasattr(_Pages[m][r].template.module, "__html_doc__"):
            return str(_Pages[m][r].template.module.__html_doc__)
    except:
        pass


def getPageInfo(module, resource):
    # There's enough possible trouble with new kinds of events and users stuffing bizzare things
    # in there that i'm Putting this in a try block.
    try:
        return _Pages[module][resource].template.module.__doc__ or ""
    except:
        return ""


# Delete a event from the cache by module and resource


def removeOnePage(module, resource):
    # Look up the eb
    with _page_list_lock:
        if module in _Pages:
            if resource in _Pages[module]:
                del _Pages[module][resource]
    gc.collect()
    lookup.invalidate_cache()


# Delete all __events in a module from the cache
def removeModulePages(module):
    # There might not be any pages, so we use the if
    if module in _Pages:
        del _Pages[module]
    gc.collect()
    lookup.invalidate_cache()


# This piece of code will update the actual event object based on the event resource definition in the module
# Also can add a new page
def updateOnePage(resource, module):
    # This is one of those places that uses two different locks
    with modules_state.modulesLock:
        if module not in _Pages:
            _Pages[module] = {}

        # Delete the old version if present
        try:
            del _Pages[module][resource]
            gc.collect()
            time.sleep(0.125)
            gc.collect()
        except:
            pass

        enable = True
        # Get the page resource in question
        j = modules_state.ActiveModules[module][resource]

        # Don't serve file if that's not enabled
        if j["resource-type"] == "internal-fileref":
            if not j.get('serve', False):
                enable = False
        if enable:
            _Pages[module][resource] = CompiledPage(j, module, resource)
        lookup.invalidate_cache()


def makeDummyPage(resource, module):
    if module not in _Pages:
        _Pages[module] = {}

    # Get the page resource in question
    j = {"resource-type": "page", "body": "Content here", "no-navheader": True}
    _Pages[module][resource] = CompiledPage(j, module, resource)


# look in the modules and compile all the event code
def getPagesFromModules():
    global _Pages
    with modules_state.modulesLock:
        with _page_list_lock:
            # Set __events to an empty list we can build on
            _Pages = {}
            for i in modules_state.ActiveModules.copy():
                # For each loaded and active module, we make a subdict in _Pages
                _Pages[i] = {}  # make an empty place for pages in this module
                # now we loop over all the resources o the module to see which ones are pages
                for m in modules_state.ActiveModules[i].copy():
                    j = modules_state.ActiveModules[i][m]
                    if j["resource-type"] == "page":
                        try:
                            _Pages[i][m] = CompiledPage(j, i, m)
                        except Exception as e:
                            makeDummyPage(m, i)
                            tb = traceback.format_exc(chain=True)
                            # When an error happens, log it and save the time
                            # Note that we are logging to the compiled event object
                            _Pages[i][m].errors.append(
                                [
                                    time.strftime(config["time-format"]),
                                    tb,
                                    "Error while initializing",
                                ]
                            )
                            try:
                                messagebus.post_message(
                                    "system/errors/pages/" +
                                    i + "/" + m, str(tb)
                                )
                            except Exception as e:
                                print(e)
                            # Keep only the most recent 25 errors

                            # If this is the first error(high level: transition from ok to not ok)
                            # send a global system messsage that will go to the front page.
                            if len(_Pages[i][m].errors) == 1:
                                messagebus.post_message(
                                    "/system/notifications/errors",
                                    'Page "'
                                    + m
                                    + '" of module "'
                                    + i
                                    + '" may need attention',
                                )
                    elif j["resource-type"] in "internal-fileref":
                        if j.get("serve", False):
                            try:
                                _Pages[i][m] = CompiledPage(j, i, m)
                            except Exception as e:
                                makeDummyPage(m, i)
                                tb = traceback.format_exc(chain=True)
                                # When an error happens, log it and save the time
                                # Note that we are logging to the compiled event object
                                _Pages[i][m].errors.append(
                                    [
                                        time.strftime(config["time-format"]),
                                        tb,
                                        "Error while initializing",
                                    ]
                                )
                                try:
                                    messagebus.post_message(
                                        "system/errors/pages/" +
                                        i + "/" + m, str(tb)
                                    )
                                except Exception as e:
                                    print(e)
                                # Keep only the most recent 25 errors

                                # If this is the first error(high level: transition from ok to not ok)
                                # send a global system messsage that will go to the front page.
                                if len(_Pages[i][m].errors) == 1:
                                    messagebus.post_message(
                                        "/system/notifications/errors",
                                        'Page "'
                                        + m
                                        + '" of module "'
                                        + i
                                        + '" may need attention',
                                    )
                        else:
                            try:
                                del _Pages[i][m]
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
        from . import kaithemobj

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
            x += i + ", "
        x = x[:-2]

        cherrypy.response.headers["Allow"] = x + ", HEAD, OPTIONS"
        if page.xss:
            if "Origin" in cherrypy.request.headers:
                if (
                    cherrypy.request.headers["Origin"] in page.origins
                    or "*" in page.origins
                ):
                    cherrypy.response.headers[
                        "Access-Control-Allow-Origin"
                    ] = cherrypy.request.headers["Origin"]
                cherrypy.response.headers["Access-Control-Allow-Methods"] = x

    def _serve(self, module, *args, **kwargs):
        page = lookup(module, args)
        if None == page:
            messagebus.post_message(
                "/system/errors/http/nonexistant",
                "Someone tried to access a page that did not exist in module %s with path %s"
                % (module, args),
            )
            raise cherrypy.NotFound()

        if "Origin" in cherrypy.request.headers:
            if not (
                cherrypy.request.headers["Origin"] in page.origins
                or "*" in page.origins
            ):
                raise RuntimeError(
                    "Refusing XSS from this origin: "
                    + cherrypy.request.headers["Origin"]
                )
            else:
                cherrypy.response.headers[
                    "Access-Control-Allow-Origin"
                ] = cherrypy.request.headers["Origin"]

        x = ""
        for i in page.methods:
            x += i + ", "
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

            if page.directServeFile:
                return cherrypy.lib.static.serve_file(
                    page.directServeFile,
                    page.mime,
                    os.path.basename(page.directServeFile),
                )

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
                    return page.template.render(
                        **s
                    ).encode("utf-8")
                else:
                    s.update(page.scope)
                    
                    if page.code_obj:
                        exec(page.code_obj, s, s)

                    return page.template.render(
                        **s
                    )

            else:
                return page.text.encode("utf-8")

        except self.kaithemobj.ServeFileInsteadOfRenderingPageException as e:
            if page.streaming and hasattr(e.f_filepath, "read"):
                cherrypy.response.headers["Content-Type"] = e.f_MIME
                cherrypy.response.headers["Content-Disposition"] = (
                    'attachment ; filename = "' + e.f_name + '"'
                )
                return streamGen(e.f_filepath)

            if hasattr(e.f_filepath, "getvalue"):
                cherrypy.response.headers["Content-Type"] = e.f_MIME
                cherrypy.response.headers["Content-Disposition"] = (
                    'attachment ; filename = "' + e.f_name + '"'
                )
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

            # tb = traceback.format_exc(chain=True)
            tb = tornado.exceptions.text_error_template().render()
            data = (
                "Request from: "
                + cherrypy.request.remote.ip
                + "("
                + pages.getAcessingUser()
                + ")\n"
                + cherrypy.request.request_line
                + "\n"
            )
            # When an error happens, log it and save the time
            # Note that we are logging to the compiled event object
            page.errors.append(
                [time.strftime(config["time-format"]), tb, data])
            try:
                messagebus.post_message(
                    "system/errors/pages/" + module +
                    "/" + "/".join(args), str(tb)
                )
            except Exception as e:
                print(e)
            # Keep only the most recent 25 errors

            # If this is the first error(high level: transition from ok to not ok)
            # send a global system messsage that will go to the front page.
            if len(page.errors) == 1:
                messagebus.post_message(
                    "/system/notifications/errors",
                    'Page "'
                    + "/".join(args)
                    + '" of module "'
                    + module
                    + '" may need attention',
                )
            raise (e)
