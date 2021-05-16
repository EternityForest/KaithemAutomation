

import configparser
import logging
import datetime

from kivy.uix.image import Image
from kivy.uix.widget import Widget

from typing import Sized, Text
from kivy.utils import platform
from kivymd.uix.button import MDFillRoundFlatButton as Button, MDRoundFlatButton
from kivymd.uix.button import MDFlatButton
from kivymd.uix.textfield import MDTextFieldRect, MDTextField
from kivymd.uix.label import MDLabel as Label
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput
from kivymd.uix.toolbar import MDToolbar
from kivymd.uix.card import MDCard
from kivymd.uix.boxlayout import MDBoxLayout as BoxLayout
from kivy.uix.screenmanager import ScreenManager, Screen


class BarcodesMixin():
    def makeZbarPage(self):
        sc = Screen(name="zbarcam")
        self.zparpagelayout = lo = BoxLayout(orientation="vertical")

        sc.add_widget(lo)
        return sc

    def gotoZbarcam(self, *a):
        from kivy_garden.zbarcam import ZBarCam
        self.zbarcam = zbc = ZBarCam()
        lo = self.zparpagelayout
        lo.clear_widgets()
        lo.add_widget(zbc)
        lo.add_widget(self.makeBackButton())

        self.backup_screenmanager = self.screenManager.current
        self.screenManager.current = 'zbarcam'

    def exitZbarcam(self, *a):
        lo.clear_widgets()
        self.screenManager.current = self.backup_screenmanager

    def onSymbolsChange(self, *a):
        if hasattr(self, "onBarcodeCallback"):
            if self.onBarcodeCallback:
                self.onBarcodeCallback(self.zbarcam.symbols)
        self.exitZbarcam()
