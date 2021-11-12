import configparser
from hardline import daemonconfig
from .. import daemonconfig, hardline


import configparser,logging

from kivy.uix.image import Image
from kivy.uix.widget import Widget

from typing import Sized, Text
from kivy.utils import platform
from kivymd.uix.button import MDFillRoundFlatButton as Button, MDRoundFlatButton
from kivymd.uix.button import MDFlatButton
from kivymd.uix.textfield import MDTextFieldRect,MDTextField
from kivymd.uix.label import MDLabel as Label
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput
from kivymd.uix.toolbar import MDToolbar
from kivymd.uix.card import MDCard
from kivymd.uix.boxlayout import MDBoxLayout as BoxLayout
from kivy.uix.screenmanager import ScreenManager, Screen

import time
import traceback

# Terrible Hacc, because otherwise we cannot iumport hardline on android.
import os
import sys
import re
from .. daemonconfig import makeUserDatabase
from .. import  drayerdb, cidict

from kivymd.uix.picker import MDDatePicker


class ServicesMixin():
    def makeLocalServiceEditPage(self):

        screen = Screen(name='EditLocalService')
        self.servicesScreen = screen

        layout = BoxLayout(orientation='vertical', spacing=10)
        screen.add_widget(layout)
        self.localServiceEditorName = Label(size_hint=(
            1, None), halign="center", text="??????????")

        layout.add_widget(self.makeBackButton())

        self.localServiceEditPanelScroll = ScrollView(size_hint=(1, 1))

        self.localServiceEditPanel = BoxLayout(
            orientation='vertical', size_hint=(1, None))
        self.localServiceEditPanel.bind(
            minimum_height=self.localServiceEditPanel.setter('height'))

        self.localServiceEditPanelScroll.add_widget(self.localServiceEditPanel)

        layout.add_widget(self.localServiceEditPanelScroll)

        return screen

    def editLocalService(self, name, c=None):
        if not c:
            c = configparser.RawConfigParser(dict_type=cidict.CaseInsensitiveDict)

        try:
            c.add_section("Service")
        except:
            pass
        try:
            c.add_section("Info")
        except:
            pass

        self.localServiceEditPanel.clear_widgets()

        self.localServiceEditorName.text = name

        def save(*a):
            logging.info("SAVE BUTTON WAS PRESSED")
            # On android this is the bg service's job
            daemonconfig.makeUserService(None, name, title=c['Info'].get("title", 'Untitled'), service=c['Service'].get("service", ""),
                                     port=c['Service'].get("port", ""), cacheInfo=c['Cache'], noStart=(platform == 'android'), useDHT=c['Access'].get("useDHT", "yes"))
            if platform == 'android':
                self.stop_service()
                self.start_service()

            self.goToLocalServices()

        def delete(*a):
            def f(n):
                if n and n == name:
                    daemonconfig.delUserService(None, n)
                    if platform == 'android':
                        self.stop_service()
                        self.start_service()
                    self.goToLocalServices()

            self.askQuestion("Really delete?", name, f)

        self.localServiceEditPanel.add_widget(Label(size_hint=(1, None), halign="center",
                                                    text='Service'))

        self.localServiceEditPanel.add_widget(
            self.settingButton(c, "Service", "service"))
        self.localServiceEditPanel.add_widget(
            self.settingButton(c, "Service", "port"))
        self.localServiceEditPanel.add_widget(
            self.settingButton(c, "Info", "title"))

        self.localServiceEditPanel.add_widget(Label(size_hint=(1, None), halign="center",
                                                    text='Cache'))
        self.localServiceEditPanel.add_widget(Label(size_hint=(1, None),
                                                    text='Cache mode only works for static content'))

        self.localServiceEditPanel.add_widget(
            self.settingButton(c, "Cache", "directory"))

        self.localServiceEditPanel.add_widget(
            self.settingButton(c, "Cache", "maxAge"))

        self.localServiceEditPanel.add_widget(Label(size_hint=(1, None), 
                                                    text='Try to refresh after maxAge seconds(default 1 week)'))

        self.localServiceEditPanel.add_widget(
            self.settingButton(c, "Cache", "maxSize", '256'))

        self.localServiceEditPanel.add_widget(Label(size_hint=(1, None),  
                                                    text='Max size to use for the cache in MB'))

        self.localServiceEditPanel.add_widget(
            self.settingButton(c, "Cache", "downloadRateLimit", '1200'))

        self.localServiceEditPanel.add_widget(Label(size_hint=(1, None),  
                                                    text='Max MB per hour to download'))

        self.localServiceEditPanel.add_widget(
            self.settingButton(c, "Cache", "dynamicContent", 'no'))

        self.localServiceEditPanel.add_widget(Label(size_hint=(1, None),  
                                                    text='Allow executing code in protected @mako files in the cache dir. yes to enable. Do not use with untrusted @mako'))

        self.localServiceEditPanel.add_widget(
            self.settingButton(c, "Cache", "allowListing", 'no'))

        self.localServiceEditPanel.add_widget(Label(size_hint=(1, None), 
                                                    text='Allow directory listing of cached content'))

        self.localServiceEditPanel.add_widget(Label(size_hint=(1, None), 
                                                    text='Directory names are subfolders within the HardlineP2P cache folder,\nand can also be used to share\nstatic files by leaving the service blank.'))

        self.localServiceEditPanel.add_widget(Label(size_hint=(1, None), halign="center",
                                                    text='Access Settings'))
        self.localServiceEditPanel.add_widget(Label(size_hint=(1, None), 
                                                    text='Cache mode only works for static content'))

        self.localServiceEditPanel.add_widget(
            self.settingButton(c, "Access", "useDHT", 'yes'))

        self.localServiceEditPanel.add_widget(Label(size_hint=(1, None),
                                                    text='DHT Discovery uses a proxy server on Android. \nDisabling this saves bandwidth but makes access from outside your network\nunreliable.'))

        btn1 = Button(text='Save Changes')

        btn1.bind(on_press=save)
        self.localServiceEditPanel.add_widget(btn1)

        btn2 = Button(text='Delete this service')

        btn2.bind(on_press=delete)
        self.localServiceEditPanel.add_widget(btn2)

        self.screenManager.current = "EditLocalService"

    def makeButtonForLocalService(self, name, c=None):
        "Make a button that, when pressed, edits the local service in the title"

        btn = Button(text=name)

        def f(*a):
            self.editLocalService(name, c)
        btn.bind(on_press=f)

        return btn


    def makeLocalServicesPage(self):

        screen = Screen(name='LocalServices')
        self.servicesScreen = screen

        layout = BoxLayout(orientation='vertical', spacing=10)
        screen.add_widget(layout)

      

        label = Label(size_hint=(1, None), halign="center",
                      text='WARNING: Running a local service may use a lot of data and battery.\nChanges may require service restart.')

        labelw = Label(size_hint=(1, None), halign="center",
                       text='WARNING 2: This app currently prefers the external SD card for almost everything including the keys.')

        layout.add_widget(self.makeBackButton())

        layout.add_widget(label)
        layout.add_widget(labelw)

        btn2 = Button(text='Create a service')

        btn2.bind(on_press=self.promptAddService)
        layout.add_widget(btn2)

        self.localServicesListBoxScroll = ScrollView(size_hint=(1, 1))

        self.localServicesListBox = BoxLayout(
            orientation='vertical', size_hint=(1, None), spacing=10)
        self.localServicesListBox.bind(
            minimum_height=self.localServicesListBox.setter('height'))

        self.localServicesListBoxScroll.add_widget(self.localServicesListBox)

        layout.add_widget(self.localServicesListBoxScroll)

        return screen

    def promptAddService(self, *a, **k):

        def f(v):
            if v:
                self.editLocalService(v)
        self.askQuestion("New Service filename?", cb=f)

    def goToLocalServices(self, *a):
        "Go to a page wherein we can list user-modifiable services."
        self.localServicesListBox.clear_widgets()

        try:
            s = daemonconfig.listServices(None)
            time.sleep(0.5)
            for i in s:
                self.localServicesListBox.add_widget(
                    self.makeButtonForLocalService(i, s[i]))

        except Exception:
            logging.info(traceback.format_exc())

        self.screenManager.current = "LocalServices"
