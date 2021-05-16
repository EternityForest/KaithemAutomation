"""
Contains tools relevant to running as a standalone daemon or app
"""

from .hardline import *
# "User Services" are configurable services stored in files, asw opposed to those defined in code
import os
import configparser
from . import drayerdb

from .cidict import CaseInsensitiveDict


def loadUserServices(serviceDir, only=None):
    serviceDir = serviceDir or directories.user_services_dir

    "Load services from a configuration directory.  Only to  only reload one, by giving it the filename minus .ini"
    try:
        os.makedirs(serviceDir)
    except:
        pass

    logger.info("Loading Services from "+serviceDir)

    if os.path.exists(serviceDir):
        x = os.listdir(serviceDir)
        for i in x:
            if not i.endswith(".ini"):
                continue
            if only:
                if not i == only+".ini":
                    continue
            try:
                config = configparser.RawConfigParser(
                    dict_type=CaseInsensitiveDict)
                config.read(os.path.join(serviceDir, i))

                if "Info" in config.sections():
                    title = config['Info'].get("title", 'untitled')
                else:
                    title = 'untitled'

                if "Cache" in config.sections():
                    cache = config['Cache']
                else:
                    cache = {}

                if "Access" in config.sections():
                    access = config['Access']
                else:
                    access = {}

                service = config['Service']

                # Close any existing service by that same friendly local name
                closeServices(i[:-4])

                certFile = os.path.join(serviceDir, i+".cert")
                if service.get('certfile', ''):
                    certFile = service['certfile']
                logger.info("Loading Service")

                useDHT = (access.get("useDHT", 'yes') or 'yes').lower() in (
                    'yes', 'true', 'enable', 'on')

                # Take friendly name from filename
                s = Service(certFile, service['service'], int(
                    service.get('port', '80') or 80), {'title': title}, friendlyName=i[:-4], cacheSettings=cache, useDHT=useDHT)
                logger.info("Serving a service from "+service['service'])

                userServices[i] = s
            except:
                logger.info(traceback.format_exc())


def makeUserService(dir, name, *, title="A service", service="localhost", port='80', cacheInfo={}, noStart=False, useDHT='yes'):
    dir = dir or directories.user_services_dir

    try:
        if not os.path.exists(dir):
            os.makedirs(dir)
    except:
        logger.info(traceback.format_exception())
    c = configparser.RawConfigParser(dict_type=CaseInsensitiveDict)
    c.add_section("Service")
    c.add_section("Info")
    c.add_section("Cache")
    c.add_section("Access")

    file = os.path.join(dir, name+'.ini')

    sinfo = c['Service']
    sinfo['port'] = str(port)
    sinfo['service'] = service
    # Default gets used
    sinfo['certfile'] = ""

    info = c['Info']
    info['title'] = title

    c['Access']['useDHT'] = useDHT

    for i in cacheInfo:
        c['Cache'][i] = cacheInfo[i]

    with open(file, "w") as f:
        c.write(f)

    if not noStart:
        loadUserServices(dir, name)


def delUserService(dir, name):
    dir = dir or directories.user_services_dir

    file = os.path.join(dir, name+'.ini')

    if os.path.exists(dir):
        for n in os.listdir(dir):
            i = os.path.join(dir, n)
            if file and i.startswith(file):
                os.remove(i)
    closeServices(name)


def listServices(serviceDir):
    serviceDir = serviceDir or directories.user_services_dir
    try:
        os.makedirs(serviceDir)
    except:
        pass

    services = {}
    if os.path.exists(serviceDir):
        for i in os.listdir(serviceDir):
            if not i.endswith(".ini"):
                continue
            try:
                config = configparser.RawConfigParser(
                    dict_type=CaseInsensitiveDict)
                config.read(os.path.join(serviceDir, i))
                services[i[:-4]] = config
            except:
                logger.info(traceback.format_exc())

    return services


userDatabases = {}


def delDatabase(dir, name):
    dir = dir or directories.drayerDB_root

    file = os.path.join(dir, name+'.db')

    if os.path.exists(dir):
        for n in os.listdir(dir):
            i = os.path.join(dir, n)
            if i==file or n.startswith(file+'.'):
                os.remove(i)
    try:
        userDatabases[name].close()
    except:
        pass
    del userDatabases[name]


defaultDBClass = drayerdb.DocumentDatabase


lastnotehorizon = 0
notesremaining = 12


class defaultDBClass(drayerdb.DocumentDatabase):
    def onRecordChange(self, record, signature):
        
        global lastnotehorizon, notesremaining
        elapsed = time.time()-lastnotehorizon
        notesremaining = min(12, notesremaining + elapsed/10)
        if notesremaining >= 1:
            if record.get("type") in ['post', 'notification']:
                if 'Application' in self.config:
                    if self.config["Application"].get("notifications", 'no').lower() in ('yes', 'true', 'on', 'enable'):
                        try:
                            from plyer import notification
                            notification.notify(title=record.get('title', 'Untitled')[
                                                :48], message="New post in "+os.path.basename(self.filename), ticker='')
                        except:
                            logger.exception("Could not do the notification")
                        notesremaining -= 1

        return super().onRecordChange(record, signature)

    


def loadUserDatabases(serviceDir, only=None, forceProxy=None, callbackFunction=None):
    serviceDir = serviceDir or directories.drayerDB_root

    "Load services from a configuration directory.  Only to  only reload one."
    try:
        os.makedirs(serviceDir)
    except:
        pass

    logger.info("Loading Databases from " + serviceDir)
    r = []


    if os.path.exists(serviceDir):
        x = os.listdir(serviceDir)
        for i in x:
            r.append(i)
            logger.info("File"+i)
            if not i.endswith(".db"):
                continue
            if only:
                if not i == only+".db":
                    continue
            name = i[:-3]
            try:
                userDatabases[name].close()
            except KeyError:
                pass
            try:
                userDatabases[name] = defaultDBClass(
                    os.path.join(serviceDir, i), forceProxy=forceProxy)
                
                userDatabases[name].dataCallback = callbackFunction
            except:
                logger.exception(traceback.format_exc())
    return r




def loadUserDatabase(file, dn):
    "Mostly used for the document viewing feature"
    try:
        userDatabases[dn] = defaultDBClass(file)
    except:
        logger.exception(traceback.format_exc())


def closeUserDatabase(dn):
    "Mostly used for the document viewing feature"
    try:
        userDatabases[dn].close()
        del userDatabases[dn]
        
    except:
        logger.exception(traceback.format_exc())
    return r


def makeUserDatabase(dir, name):
    dir = dir or directories.drayerDB_root

    "Load services from a configuration directory.  Only to  only reload one."
    try:
        os.makedirs(dir)
    except:
        pass
    if not name in userDatabases:
        userDatabases[name] = defaultDBClass(
            os.path.join(dir, name+'.db'))


def closeServices(only=None):
    "Only lets us only close one,  by it's friendly name"
    for i in list(services.values()):
        try:
            if only:
                if not i.friendlyName == only:
                    continue
            i.close()
        except:
            logger.info(traceback.format_exc())


userServices = {}


ddbservice = [0]


def loadDrayerServerConfig():
    "Get drayer server config from the global config file."
    drayerdb.stopServer()
    if ddbservice[0]:
        ddbservice[0].close()

    import toml
    if os.path.exists(globalSettingsPath):
        with open(globalSettingsPath) as f:
            globalConfig=toml.load(f)
    else:
        globalConfig={}
    if not "DrayerDB" in globalConfig:
        globalConfig["DrayerDB"]={}

    title = globalConfig['DrayerDB'].get('serverName', '').strip()

    import getpass

    # Start the drayerDB server on a random port.
    # Only expose to localhost unless we expose with a service
    for i in range(0, 1000):
        r = 7004+i
        try:
            drayerdb.startServer(r+i, bindTo='127.0.0.1')
            drayerServerPort = r
            break
        except:
            logging.exception(
                "Can't start drayer server on this port, may retry")

    if title:
        try:
            os.makedirs(directories.builtinServicesRoot)
        except:
            pass

        ddbservice[0] = Service(os.path.join(directories.builtinServicesRoot,
                                             "drayerDB.cert"), 'localhost', drayerServerPort, info={'title': title})

import urllib.parse

import logging
def getBookmarks():
    "Get drayer server config from the global config file."
    import toml
    if os.path.exists(globalSettingsPath):
        with open(globalSettingsPath) as f:
            globalConfig=toml.load(f)
    else:
        globalConfig={}

    if not "Bookmarks" in globalConfig:
        globalConfig["Bookmarks"]={}

    x =globalConfig['Bookmarks']
    r ={}

    for i in x:
        try:
            r[i]=  urllib.parse.unquote(x[i].split(':')[0]),urllib.parse.unquote(x[i].split(':')[1])
        except:
            logging.exception("Bad Bookmark!!")
    
    return r


def setBookmark(name, file, index):
    "Get drayer server config from the global config file."
    import toml
    with open(globalSettingsPath) as f:
        globalConfig=toml.load(f)

    if not "Bookmarks" in globalConfig:
        globalConfig["Bookmarks"]={}


    bmstring = urllib.parse.quote(str(file))+":"+str(index)

    if not file:
        try:
            del globalConfig['Bookmarks'][name]
        except:
            pass
    else:
        if name in globalConfig['Bookmarks']:
            if globalConfig['Bookmarks']==bmstring:
                return
            name=name+"2"

        globalConfig['Bookmarks'][name]=bmstring

    with open(globalSettingsPath, "w") as f:
        toml.dump(globalConfig,f)
