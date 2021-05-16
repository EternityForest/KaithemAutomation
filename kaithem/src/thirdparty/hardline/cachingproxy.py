# A simple HTTP proxy which does caching of requests.
# Inspired by: https://gist.github.com/bxt/5195500
# but updated for Python 3 and some additional sanity improvements:
# - shutil is used to serve files in a streaming manner, so the entire data is not loaded into memory.
# - the http request is written to a temp file and renamed on success
# - forward headers

from datetime import datetime
import logging
import os
import traceback
import shutil
import time
import threading
import random

import urllib.request
import socketserver
import http.server
import requests
import hashlib
import json


def countDirSize(d):
    total_size = 0
    for path, dirs, files in os.walk(d):
        for f in files:
            fp = os.path.join(path, f)
            total_size += os.path.getsize(fp)
    return total_size


def deleteOldFiles(d, maxSize):
    "Delete the oldest in D until the whole cache is smaller than maxSize*0.75"
    total_size = countDirSize(d)
    if total_size < (maxSize):
        return

    listing = []

    for path, dirs, files in os.walk(d):
        for f in files:
            fp = os.path.join(path, f)
            stat = os.stat(fp)

            cacheMetric = max(stat.st_mtime, stat.st_atime)

            # Very small files are treated as if they were an extra month older,
            # because we won't reclaim as much space anyway
            if stat.st_size < 128*1024:
                cacheMetric += 30*24*256

            # Either atime or mtime marks a file as recently used.
            listing.append((cacheMetric, fp))

    listing.sort()

    for i in listing:
        # These are not cached files they are fully manual.
        if '@mako' in i[1] or '@data' in i[1]:
            continue
        total_size -= os.path.getsize(i[1])
        os.remove(i[1])

        # Use some hysteresis
        if total_size < (maxSize*0.75):
            break

    # Cleanup empty
    for path, dirs, files in os.walk(d):
        if not dirs or files:
            os.remove(path)

    return total_size


cached_headers = ["Content-Type", 'Access-Control-Allow-Origin', 'Cross-Origin-Resource-Policy',
                  'Date', 'Content-Security-Policy', 'Referrer-Policy', 'Server', 'Feature-Policy', 'Content-Disposition', 'Location', 'Content-Range', ]


def convertExternalResources(html):
    "Convert external resources into special cache URLs"
    from bs4 import BeautifulSoup

    def find_list_resources(tag, attribute, soup):
        list = []
        for x in soup.findAll(tag):
            try:
                list.append((x[attribute], x))
            except KeyError:
                pass
        return(list)

    soup = BeautifulSoup(html,features='lxml')
    t = ['img', 'script', 'video', 'audio']

    l = []

    for i in t:
        l.extend(find_list_resources(i, "src", soup))
    l.extend(find_list_resources('link', "href", soup))

    for i in l:
        if i[0].startswith("http://") or i[0].startswith("https://") or i[0].startswith("//"):
            i[1]['src'] = "/cache_external_resource/" + \
                urllib.parse.quote(i[0].split("//")[-1], safe='/')
    return str(soup)


class CachingProxy():
    "Return an object that can be used as either a caching proxy or a plain static file server."

    def __init__(self, site, directory, maxAge=7*24*3600, downloadRateLimit=1200, maxSize=1024*1024*256, allowListing=False, dynamicContent=False):

        # Convert to int because we have to expect that the params will be supplied directly from an ini file parser.
        # And the user may have supplied blanks.

        # Calculate in 128kb blocks
        maxRequestsPerHour = int(downloadRateLimit or 1200)*8

        timePerBlock = 3600/maxRequestsPerHour

        maxAge = int(maxAge or 7*24*3600)
        maxSize = int(maxSize or 1024*1024*256)

        downloadQuotaHolder = [maxRequestsPerHour]
        downloadQuotaTimestamp = [time.time()]
        self.port = None

        if not "://" in site:
            site = "https://"+site

        try:
            from mako.lookup import TemplateLookup
            templateLookup = TemplateLookup([directory])
            self.templateLookup = templateLookup
        except ImportError as e:
            logging.info("No mako support for dynamic content in cache files.")

        def makeListPage(p):
            s = "<html><body><ul>"

            for i in os.listdir(os.path.join(directory, p)):
                s += '<li><a href="'+i+"</a></li>"
            s += "</ul></body></html>"
            return s.encode()

        try:
            os.makedirs(directory)
        except:
            pass

        totalSize = [countDirSize(directory)]

        class CacheHandler(http.server.SimpleHTTPRequestHandler):
            def do_GET(self):

                reqHeaders = {}
                targetURL = site + self.path

                if self.path.startswith("/cache_external_resource/"):
                    original = self.path[len('/cache_external_resource/'):]
                    #TODO should we support standard http external resources?
                    targetURL = 'https://'+urllib.parse.unquote(original)

                cache_filename = self.path

                if cache_filename.startswith("/"):
                    cache_filename = cache_filename[1:]
                unquoted = cache_filename

                cache_filename = urllib.parse.quote(cache_filename)

                # Defensive programming because we may depend on @ files for special purposes.
                if '@' in cache_filename:
                    raise RuntimeError("This should not happen")

                if len(cache_filename) > 192:
                    cache_filename = hashlib.md5(
                        cache_filename.encode()).hexdigest()

                # Very lightweight dynamic content support in the form of Mako templates.
                # Just enough for a tiny bit of custom stuff on top of a cached site to compensate
                # for the non-dynamicness.
                if dynamicContent:
                    makoName = unquoted.split("#")[0].split("?")[0]
                    makoName = makoName+"@mako"
                    if os.path.exists(os.path.join(directory, makoName)):
                        t = templateLookup.get_template(
                            makoName).render(path=self.path, __file__=makoName)
                        self.send_response(200)
                        self.end_headers()
                        self.wfile.write(t.encode())
                        return

                cache_filename = os.path.join(directory, cache_filename)
                header_filename = None

                if not os.path.isfile(cache_filename):
                    # HTTP lets you access a dir and a file the same way.  Filesystems do not,
                    # So retrieved files need the special postfix to be sure they never collide with dirs.

                    # However, we also need to be compatible with manually-created directory structures which
                    # The user wants to serve exactly as-is.   To accomodate that we only do the posfixing IF the
                    # original one does not exist.
                    cache_filename = cache_filename+"@http"
                    header_filename = cache_filename+".headers"

                useCache = True
                # Approximately calculate how many download blocks are left in the quota

                def doQuotaCalc():
                    # Accumulate quota units up to the maximum allowed
                    downloadQuotaHolder[0] += min(((time.time()-downloadQuotaTimestamp[0])/3600)
                                                  * maxRequestsPerHour+maxRequestsPerHour, maxRequestsPerHour)
                    downloadQuotaTimestamp[0] = time.time()
                    return downloadQuotaHolder[0]

                if not os.path.exists(cache_filename):
                    useCache = False

                else:
                    t = os.stat(cache_filename).st_mtime
                    age = time.time()-t
                    if age > maxAge:
                        # If totally empty, we are in high load conditions,
                        # Use cache even if it is old, to prioritize getting stuff we don't have already.
                        if doQuotaCalc():
                            useCache = False
                        reqHeaders['If-Modified-Since'] = time.strftime(
                            '%a, %d %b %Y %H:%M:%S GMT', time.gmtime(t))

                doQuotaCalc()

                if not useCache:
                    if site:
                        try:
                            os.makedirs(os.path.dirname(cache_filename))
                        except:
                            pass

                         # Stream=True only if requested as such.
                        if self.headers.get('Transfer-Encoding', self.headers.get('transfer-encoding', '')).lower() == 'chunked':
                            stream = True
                        else:
                            stream = False

                        if not stream:
                            try:
                                with requests.get(targetURL, headers=reqHeaders) as resp:
                                    # Use cache if the server says we have the latest version.
                                    if resp.status_code == 304:
                                        if os.path.isfile(cache_filename):
                                            with open(cache_filename, "rb") as cached:
                                                self.send_response(200)
                                                if header_filename and os.path.isfile(header_filename):
                                                    with open(header_filename) as f:
                                                        h = json.loads(
                                                            f.read())
                                                    for i in h:
                                                        self.send_header(
                                                            i, h[i])

                                                self.send_header('Content-Length',
                                                                 os.path.getsize(cache_filename))

                                                self.end_headers()
                                                shutil.copyfileobj(
                                                    cached, self.wfile)
                                            return

                                    accumMode = False
                                    if "Content-Length" in resp.headers and int(resp.headers["Content-Length"]) < 1000000:
                                        if "Content-Type" in resp.headers and (resp.headers["Content-Type"].startswith('text/html') or self.path.endswith(".html")):
                                            if not stream and not resp.headers.get('Transfer-Encoding', '') == 'chunked':
                                                accumMode = True
                                                accum = b''

                                    with open(cache_filename + ".temp", "wb") as output:
                                        # copy request headers
                                        # for k in self.headers:
                                        #     if k not in ["Host"]:
                                        #         req.add_header(k, self.headers[k])
                                        logging.info(
                                            "Making HTTP request to :"+(targetURL))

                                        h2 = {}
                                        self.send_response(resp.status_code)
                                        for i in cached_headers:
                                            if i in resp.headers or (i == "Content-Length" and not accumMode):
                                                h2[i] = resp.headers[i]
                                                self.send_header(
                                                    i, resp.headers[i])

                                        with open(header_filename + ".temp", "w") as hfile:
                                            hfile.write(json.dumps(h2))

                                        if not accumMode:
                                            self.end_headers()

                                        for i in resp.iter_content(128*1024):
                                            # Partial blocks count for one whole block.
                                            d = i
                                            if not d:
                                                break

                                            totalSize[0] += len(d)

                                            downloadQuotaHolder[0] -= 1
                                            for i in range(1000):
                                                if doQuotaCalc():
                                                    break
                                                time.sleep(0.1)

                                            if not downloadQuotaHolder[0]:
                                                time.sleep(timePerBlock)
                                            # No write the too big
                                            # TODO avoid this in the first place.
                                            if totalSize[0] > maxSize:
                                                continue

                                            if not accumMode:
                                                output.write(d)
                                                self.wfile.write(d)
                                            else:
                                                accum += d

                                        if accumMode:
                                            self.send_header(
                                                "Content-Length", len(accum))
                                            self.end_headers()
                                            if resp.headers.get('Content-Disposition', 'inline') == 'inline':
                                                d = convertExternalResources(
                                                    accum).encode()
                                            output.write(d)
                                            self.wfile.write(d)

                                        os.rename(cache_filename +
                                                  ".temp", cache_filename)

                                        os.rename(header_filename +
                                                  ".temp", header_filename)
                                        if totalSize[0] > maxSize:
                                            totalSize[0] = deleteOldFiles(
                                                directory, maxSize)

                            except:
                                logging.exception("err")
                                self.send_response(500)
                                self.end_headers()
                                return
                        else:
                            with requests.get(targetURL) as resp:

                                logging.info(
                                    "Making streaming HTTP request to :"+(targetURL))
                                h = resp.headers

                                self.send_response(resp.status_code)
                                for i in cached_headers:
                                    if i in h or (i == "Content-Length"):
                                        self.send_header(i, h[i])

                                self.end_headers()

                                for i in resp.iter_content(128*1024):
                                    # Partial blocks count for one whole block.
                                    d = i
                                    if not d:
                                        break

                                    totalSize[0] += len(d)

                                    downloadQuotaHolder[0] -= 1
                                    for i in range(1000):
                                        if doQuotaCalc():
                                            break
                                        time.sleep(0.1)

                                    if not downloadQuotaHolder[0]:
                                        time.sleep(timePerBlock)

                                    self.wfile.write(d)
                    else:
                        self.send_response(404)
                        self.end_headers()
                        return
                else:
                    if os.path.isfile(cache_filename):
                        with open(cache_filename, "rb") as cached:

                            # If the access time is more than a week ago, update it's metadata
                            # to indicate that it is still being used, and potentially save it from being GCed
                            # as an old file
                            stat = os.stat(cache_filename)
                            if stat.st_atime < time.time()-(3600*24*7):
                                os.utime(cache_filename,
                                         (time.time(), stat.st_mtime))

                            self.send_response(200)
                            if header_filename and os.path.isfile(header_filename):
                                with open(header_filename) as f:
                                    h = json.loads(f.read())
                                for i in h:
                                    self.send_header(i, h[i])

                            self.send_header('Content-Length',
                                             os.path.getsize(cache_filename))

                            self.end_headers()
                            shutil.copyfileobj(cached, self.wfile)
                    else:
                        self.send_response(200)
                        self.end_headers()
                        self.wfile.write(makeListPage(cache_filename))

        def f():
            for i in range(128):
                p = 50000 + int(random.random()*8192)
                try:
                    with socketserver.TCPServer(("localhost", p), CacheHandler) as httpd:
                        self.port = p
                        self.server = httpd
                        httpd.serve_forever()
                except:
                    logging.info(traceback.format_exc())

            self.port = None

        self.thread = threading.Thread(target=f, daemon=True)
        self.thread.start()
