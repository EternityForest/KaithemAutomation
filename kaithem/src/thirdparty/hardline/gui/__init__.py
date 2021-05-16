# This is the kivy android app.  Maybe ignore it on ither platforms, the code the support them is only for testing.


from kivy.config import Config

Config.set('graphics', 'maxfps', '48')


from kivy.uix.layout import Layout
from . import tools, servicesUI, discovery, tables, posts, streams, uihelpers
from kivymd.uix.textfield import MDTextFieldRect, MDTextField
from kivy.clock import mainthread, Clock
from kivy.logger import Logger, LOG_LEVELS
from hardline.cidict import CaseInsensitiveDict
import datetime
from kivymd.uix.picker import MDDatePicker
from .. import drayerdb, cidict
from .. daemonconfig import makeUserDatabase
import re
import sys
import os
import traceback
import time
from kivy.uix.screenmanager import ScreenManager, Screen
import threading
from kivymd.uix.stacklayout import MDStackLayout as StackLayout

from kivymd.uix.boxlayout import MDBoxLayout as BoxLayout
from kivymd.uix.card import MDCard
from kivymd.uix.toolbar import MDToolbar
from kivy.uix.textinput import TextInput
from kivy.uix.scrollview import ScrollView
from kivymd.uix.label import MDLabel as Label
from kivymd.uix.button import MDFlatButton
from kivymd.uix.button import MDFillRoundFlatButton as Button, MDRoundFlatButton
from kivy.utils import platform
from kivymd.app import MDApp
from typing import Sized, Text
from .. import hardline
from kivy.uix.widget import Widget
from kivy.uix.image import Image
from .. import simpleeval
from .. import directories
import base64
import configparser
from kivy.logger import Logger
import logging

from hardline import daemonconfig
logging.Logger.manager.root = Logger










# Terrible Hacc, because otherwise we cannot iumport hardline on android.


Logger.setLevel(LOG_LEVELS["info"])



# In this mode, we are just acting as a viewer for a file
oneFileMode = False


class ServiceApp(MDApp, uihelpers.AppHelpers, tools.ToolsAndSettingsMixin, servicesUI.ServicesMixin, discovery.DiscoveryMixin, tables.TablesMixin, posts.PostsMixin, streams.StreamsMixin):

    def stop_service(self, foo=None):
        if self.service:
            self.service.stop()
            self.service = None
        else:
            hardline.stop()

    def onDrayerRecordChange(self,db,record,sig):
        if self.currentPageNewRecordHandler:
            self.currentPageNewRecordHandler(db,record,sig)
        
        #Only deleting or changing as data row can affect this
        if record['type'] in ('null','row'):
            self.clearSpreadsheetCache()

    def start_service(self, foo=None):
        
        try:
            self.service.stop()
            self.service = None
        except:
            logging.exception("Likely no need to stop nonexistent service")

        if platform == 'android':
            from android import AndroidService
            logging.info("About to start Android service")
            service = AndroidService('HardlineP2P Service', 'running')
            service.start('service started')
            self.service = service
            # On android the service that will actually be handling these databases is in the background in a totally separate
            # process.  So we open an SECOND drayer database object for each, with the same physical storage, using the first as the server.
            # just for use in the foreground app.

            # Because of this, two connections to the same DB file is a completetely supported use case that drayerDB has optimizations for.
            daemonconfig.loadUserDatabases(None, forceProxy='localhost:7004',callbackFunction=self.onDrayerRecordChange)
        else:
            def f():
                # Ensure stopped
                hardline.stop()

                loadedServices = daemonconfig.loadUserServices(
                    None)

                daemonconfig.loadDrayerServerConfig()
                self.currentPageNewRecordHandler=None
                db = daemonconfig.loadUserDatabases(
                    None,callbackFunction=self.onDrayerRecordChange)
                hardline.start(7009)
                # Unload them at exit because we will be loading them again on restart
                for i in loadedServices:
                    loadedServices[i].close()
            t = threading.Thread(target=f, daemon=True)
            t.start()

    def build(self):
        self.service = None

        self.start_service()

        # Create the manager
        sm = ScreenManager()
        self.currentPageNewRecordHandler=None
        sm.add_widget(self.makeMainScreen())
        sm.add_widget(self.makeDiscoveryPage())
        sm.add_widget(self.makeSettingsPage())

        sm.add_widget(self.makeLocalServiceEditPage())
        sm.add_widget(self.makeLocalServicesPage())
        sm.add_widget(self.makeGlobalSettingsPage())
        sm.add_widget(self.makeStreamsPage())
        sm.add_widget(self.makeStreamEditPage())
        sm.add_widget(self.makeLogsPage())
        sm.add_widget(self.makePostMetaDataPage())
        from kivy.base import EventLoop
        EventLoop.window.bind(on_keyboard=self.hook_keyboard)
        import kivymd
        self.theme_cls.colors=kivymd.color_definitions.colors

        import kivy.clock
        kivy.clock.Clock.max_iteration = 10

        #Horid hacks for material design
        self.theme_cls.colors['Brown']['900']='050200'
        self.theme_cls.colors['Green']['600']='83A16C'
        self.theme_cls.colors['Light']['Background']='E3DFDA'
        self.theme_cls.primary_palette = "Green"
        self.theme_cls.theme_style = "Light"
        self.theme_cls.primary_hue='600'
        self.theme_cls.accent_hue='900'
        self.theme_cls.accent_palette='Brown'


        self.backStack = []

        # Call this to save whatever unsaved data. Also acts as a flag.
        self.unsavedDataCallback = None

        self.screenManager = sm


        Clock.schedule_interval(self.flushUnsaved, 60*5)
        self.gotoMainScreen()

        return sm

    # Here is our autosave
    def on_pause(self):
        self.flushUnsaved()
        return True

    def on_stop(self):
        self.flushUnsaved()

    def on_destroy(self):
        self.flushUnsaved()

    def flushUnsaved(self, *a):
        if self.unsavedDataCallback:
            self.unsavedDataCallback()
            self.unsavedDataCallback = None

    def makeMainScreen(self):
        mainScreen = Screen(name='Main')

        mainscroll = ScrollView(size_hint=(1, 1))

        self.mainScreenlayout = BoxLayout(orientation='vertical',
                           spacing=10, size_hint=(1, 1),adaptive_height=True)

        mainscroll.add_widget(self.mainScreenlayout)
        mainScreen.add_widget(mainscroll)
        return mainScreen


    def gotoMainScreen(self):
        self.mainScreenlayout.clear_widgets()
        layout=self.mainScreenlayout

    
        label = MDToolbar(title="Drayer Journal")
        label.icon=os.path.join(os.path.dirname(os.path.abspath("__file__")),'assets','icons',"Craftpix.net",'medival','cart.jpg')
        layout.add_widget(label)

        stack = StackLayout(size_hint=(1,None),adaptive_height=True,spacing=5)

      
        l = self.saneLabel("Notice: streams may be stored on the SD card. Some other apps may be able to read them",layout)
        layout.add_widget(l)
            
        btn1 = Button(text='My Streams')

        stack.add_widget(btn1)

        btn1.bind(on_press=self.goToStreams)

        btn1 = Button(text='Discover Services')
     

        btn1.bind(on_press=self.goToDiscovery)
        stack.add_widget(btn1)

        btn5 = Button(text='Settings+Tools')

        btn5.bind(on_press=self.goToSettings)

        stack.add_widget(btn5)


        btn6 = Button(text='Help')

        btn6.bind(on_press=self.goToHelp)

        stack.add_widget(btn6)

        layout.add_widget(stack)

        label = MDToolbar(title="Bookmarks")
        layout.add_widget(label)

        for i in sorted(list(daemonconfig.getBookmarks().keys())):
            bw =BoxLayout(orientation='horizontal',
                           spacing=10, size_hint=(1, None),adaptive_height=True)
            b = Button(text=i[:32])
            bd = Button(text="Del")


            def dlbm(*a,i=i):
                def f(a):
                    if a:
                        daemonconfig.setBookmark(a,None,None)
                        self.gotoMainScreen()
                self.askQuestion("Delete Bookmark?",i,f)
            bd.bind(on_press=dlbm)

            def bm(*a,i=i):
                self.gotoBookmark(i)
            b.bind(on_press=bm)
            bw.add_widget(b)
            bw.add_widget(bd)
            layout.add_widget(bw)

        self.screenManager.current = "Main"





    def goBack(self,*a):
        def f(d):
            try:
                self.openFM.close()
            except:
                pass
            if d:
                self.currentPageNewRecordHandler=None
                self.unsavedDataCallback = False
                # Get rid of the first one representing the current page
                if self.backStack:
                    self.backStack.pop()

                # Go to the previous page, if that page left an instruction for how to get back to it
                if self.backStack:
                    self.backStack.pop()()
                else:
                    self.gotoMainScreen()

        # If they have an unsaved post, ask them if they really want to leave.
        if self.unsavedDataCallback:
            self.askQuestion("Discard unsaved data?", 'yes', cb=f)
        else:
            f(True)

    def makeBackButton(self,width=1):
        btn1 = Button(text='Back')

        btn1.bind(on_press=self.goBack)
        return btn1
    
    def hook_keyboard(self, window, key, *largs):
        if key == 27:
            self.goBack()
            return True 

    def goToHelp(self,*a):
        dn = "builtin:help"
        if not dn in daemonconfig.userDatabases:
            daemonconfig.loadUserDatabase(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),'Drayer Documentation.toml'),dn)
        self.editStream(dn)

    def getPermission(self, type='all'):
        """
        Since API 23, Android requires permission to be requested at runtime.
        This function requests permission and handles the response via a
        callback.
        The request will produce a popup if permissions have not already been
        been granted, otherwise it will do nothing.
        """
        if platform == "android":
            from android.permissions import request_permissions, Permission

            if type == 'all':
                plist = [Permission.ACCESS_COARSE_LOCATION,
                         Permission.ACCESS_FINE_LOCATION, Permission.MANAGE_EXTERNAL_STORAGE]
            if type == 'location':
                plist = [Permission.ACCESS_COARSE_LOCATION,
                         Permission.ACCESS_FINE_LOCATION]
            if type == 'files':
                plist = [Permission.MANAGE_EXTERNAL_STORAGE]

            def callback(permissions, results):
                """
                Defines the callback to be fired when runtime permission
                has been granted or denied. This is not strictly required,
                but added for the sake of completeness.
                """
                if all([res for res in results]):
                    print("callback. All permissions granted.")
                else:
                    print("callback. Some permissions refused.")

            request_permissions(plist, callback)


ServiceApp().run()
