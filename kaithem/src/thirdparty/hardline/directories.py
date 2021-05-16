import os, shutil, sys,traceback,logging
try:
    from android.storage import app_storage_path
    settings_path = app_storage_path()
except:
    settings_path = os.path.expanduser('~/.hardlinep2p/')
    drayerDB_root = os.path.expanduser('~/.hardlinep2p/drayerdb')
    
assetLibPath = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'assets')


externalStorageDir = None
try:
    from jnius import autoclass, cast
    PythonActivity = autoclass('org.kivy.android.PythonActivity')

    if PythonActivity and PythonActivity.mActivity:
        context = cast('android.content.Context', PythonActivity.mActivity)
    else:
        PythonActivity = autoclass('org.kivy.android.PythonService')
        context = cast('android.content.Context', PythonActivity.mService)

    Environment = autoclass('android.os.Environment')

    internalDir = context.getExternalFilesDir(None).getAbsolutePath()
    logging.info("Internal App Dir", internalDir)
    r = internalDir

    for i in context.getExternalFilesDirs(None):
        logging.info("Found storage dir:",i)
        p = i.getAbsolutePath()
        if p.startswith("/sdcard") or p.startswith("/storage/sdcard0/") or (p.startswith("/storage/") and not p.startswith("/storage/emulated/")):
            logging.info("Found External SD")
            r= p
            externalStorageDir= p
            break

    user_services_dir = os.path.join(r, "services")
    proxy_cache_root = os.path.join(r, "proxycache")
    drayerDB_root = os.path.join(r, "drayerdb")
    builtinServicesRoot = os.path.join(r, "builtinservices")

    #First time copy-over to new SD card from internal storage.
    import shutil
    if not os.path.exists(proxy_cache_root) and os.path.exists(os.path.join(internalDir, "proxycache")):
        logging.info("Copying proxy cache to external SD")
        shutil.copytree(os.path.join(internalDir, "proxycache"), proxy_cache_root)

    if not os.path.exists(user_services_dir) and os.path.exists(os.path.join(internalDir, "services")):
        logging.info("Copying service files to external SD")
        shutil.copytree(os.path.join(internalDir, "services"), user_services_dir)

    if not os.path.exists(drayerDB_root) and os.path.exists(os.path.join(internalDir, "drayerdb")):
        logging.info("Copying service files to external SD")
        shutil.copytree(os.path.join(internalDir, "drayerdb"), drayerDB_root)

    if not os.path.exists(builtinServicesRoot) and os.path.exists(os.path.join(internalDir, "builtinservices")):
        logging.info("Copying service files to external SD")
        shutil.copytree(os.path.join(internalDir, "builtinservices"), builtinServicesRoot)

except:
    logging.info(traceback.format_exc())
    user_services_dir = os.path.expanduser('~/.hardlinep2p/services/')
    proxy_cache_root = os.path.expanduser('~/.hardlinep2p/proxycache/')
    builtinServicesRoot =  os.path.expanduser('~/.hardlinep2p/builtinservices/')




try:
    os.makedirs(os.path.expanduser(settings_path))
except Exception:
    pass

DB_PATH = os.path.join(os.path.expanduser(settings_path), "peers.db")
