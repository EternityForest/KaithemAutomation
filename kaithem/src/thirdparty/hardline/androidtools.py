def getLocksForBackgroundOperation():
    from jnius import autoclass, cast
    PythonActivity = autoclass('org.kivy.android.PythonActivity')
    Context = autoclass('android.content.Context')

    if PythonActivity and PythonActivity.mActivity:
        activity=PythonActivity.mActivity
    else:
        PythonActivity = autoclass('org.kivy.android.PythonService')
        activity=PythonActivity.mService

    WifiManager = autoclass('android.net.wifi.WifiManager')
    service = activity.getApplicationContext().getSystemService(Context.WIFI_SERVICE)

    if service:
        wlock = service.createWifiLock(WifiManager.WIFI_MODE_FULL_HIGH_PERF , "hlp2p")
        wlock.acquire()
        mlock = service.createMulticastLock("Hardlinep2p")
        mlock.acquire()


    PowerManager = autoclass('android.os.PowerManager')
    pm = activity.getApplicationContext().getSystemService(Context.POWER_SERVICE)
    wl = pm.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, 'Hardlinep2p')

    wl.acquire()