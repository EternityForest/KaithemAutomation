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



class DiscoveryMixin():
     

    def makeDiscoveryPage(self):

        # Discovery Page

        screen = Screen(name='Discovery')
        self.discoveryScreen = screen

        layout = BoxLayout(orientation='vertical', spacing=10)
        screen.add_widget(layout)

       
        label = Label(size_hint=(1, None), halign="center",
                      text='Browsing your local network.\nWarning: anyone on your network\ncan advertise a site with any title they want.')


        layout.add_widget(self.makeBackButton())

        layout.add_widget(label)

        self.discoveryScroll = ScrollView(size_hint=(1, 1))

        self.discoveryListbox = BoxLayout(
            orientation='vertical', size_hint=(1, None))
        self.discoveryListbox.bind(
            minimum_height=self.discoveryListbox.setter('height'))

        self.discoveryScroll.add_widget(self.discoveryListbox)
        layout.add_widget(self.discoveryScroll)

        return screen

    def goToDiscovery(self, *a):
        "Go to the local network discovery page"
        self.discoveryListbox.clear_widgets()

        try:
            hardline.discoveryPeer.search('', n=5)
            time.sleep(0.5)
            for i in hardline.getAllDiscoveries():
                for j in self.makeButtonForPeer(i):
                    self.discoveryListbox.add_widget(j)

        except Exception:
            logging.info(traceback.format_exc())

        self.screenManager.current = "Discovery"

    def makeButtonForPeer(self, info):
        "Make a button that, when pressed, opens a link to the service denoted by the hash"

        btn = Button(text=str(info['title']),
                     font_size="26sp")

        def f(*a):
            self.openInBrowser("http://"+info['hash']+".localhost:7009")
        btn.bind(on_press=f)

        return(btn, Label(text="Hosted By: "+info.get("from_ip", ""), size_hint=(1, None)),

               Label(text="ID: "+info['hash'], size_hint=(1, None)))