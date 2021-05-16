import configparser

import toml
from hardline import daemonconfig
from .. import daemonconfig, hardline


import configparser,logging

from kivy.uix.image import Image
from kivy.uix.widget import Widget
from kivymd.uix.stacklayout import MDStackLayout as StackLayout

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
from .. import  drayerdb, cidict, libnacl

from kivymd.uix.picker import MDDatePicker


class StreamsMixin():


    #Reuse the same panel for editStream, the main hub for accessing the stream,
    #and it's core settings
    def editStream(self, name):
        if not  name in daemonconfig.userDatabases:
            self.goToStreams()
        db = daemonconfig.userDatabases[name]
        c = db.config
        try:
            c.add_section("Service")
        except:
            pass
        try:
            c.add_section("Info")
        except:
            pass

        self.streamEditPanel.clear_widgets()
        topbar = BoxLayout(size_hint=(1,None),adaptive_height=True,spacing=5)

        stack = StackLayout(size_hint=(1,None),adaptive_height=True,spacing=5)


        def upOne(*a):
            self.goToStreams()

        btn1 = Button(text='Up')

        btn1.bind(on_press=upOne)

        topbar.add_widget(btn1)


        topbar.add_widget(self.makeBackButton())

        self.streamEditPanel.add_widget(topbar)
        self.streamEditPanel.add_widget(MDToolbar(title=name))


        def goHere():
            self.editStream( name)
        self.backStack.append(goHere)
        self.backStack = self.backStack[-50:]



        btn2 = Button(text='Notebook View')
        def goPosts(*a):
            self.gotoStreamPosts(name)
        btn2.bind(on_press=goPosts)
        stack.add_widget(btn2)



        btn2 = Button(text='Stream Settings')
        def goSettings(*a):
            self.editStreamSettings(name)
        btn2.bind(on_press=goSettings)
        stack.add_widget(btn2)


        if name.startswith('file:'):
            btn2 = Button(text='Close Stream')
            def close(*a):
                daemonconfig.closeUserDatabase(name)
                self.goToStreams()
            btn2.bind(on_press=close)
            stack.add_widget(btn2)



        importData = Button( text="Import Data File")

        def promptSet(*a):
            try:
                #Needed for android
                self.getPermission('files')
            except:
                logging.exception("cant ask permission")

            def f(selection):
                if selection:
                    def f2(x):
                        if x:
                            with  daemonconfig.userDatabases[name]:
                                with open(selection) as f:
                                    daemonconfig.userDatabases[name].importFromToml(f.read())
                            daemonconfig.userDatabases[name].commit()
                    self.askQuestion("Really import?","yes",cb=f2)
                self.openFM.close()

            from .kivymdfmfork import MDFileManager
            from . import directories
            self.openFM= MDFileManager(select_path=f)

            
            if os.path.exists("/storage/emulated/0/Documents") and os.access("/storage/emulated/0/Documents",os.W_OK):
                self.openFM.show("/storage/emulated/0/Documents")
            elif os.path.exists(os.path.expanduser("~/Documents")) and os.access(os.path.expanduser("~/Documents"),os.W_OK):
                self.openFM.show(os.path.expanduser("~/Documents"))
            else:
                self.openFM.show(directories.externalStorageDir or directories.settings_path)
            
            
        importData.bind(on_release=promptSet)
        stack.add_widget(importData)



        export = Button( text="Export All Posts")

        def promptSet(*a):
            from .kivymdfmfork import MDFileManager
            from .. import directories
            try:
                #Needed for android
                self.getPermission('files')
            except:
                logging.exception("cant ask permission")

            def f(selection):
                if selection:
                    if not selection.endswith(".toml"):
                        selection=selection+".toml"
                
                    def g(a):
                        if a=='yes':

                            r = daemonconfig.userDatabases[name].getDocumentsByType('post',parent='')
                            data = daemonconfig.userDatabases[name].exportRecordSetToTOML([i['id'] for i in r])

                            logging.info("Exporting data to:"+selection)
                            with open(selection,'w') as f:
                                f.write(data)
                        self.openFM.close()
                    
                    if os.path.exists(selection):
                        self.askQuestion("Overwrite?",'yes',g)
                    else:
                        g('yes')

             #Autocorrect had some fun with the kivymd devs
            self.openFM= MDFileManager(select_path=f,save_mode=(name+'.toml'))

            if os.path.exists("/storage/emulated/0/Documents") and os.access("/storage/emulated/0/Documents",os.W_OK):
                self.openFM.show("/storage/emulated/0/Documents")
            elif os.path.exists(os.path.expanduser("~/Documents")) and os.access(os.path.expanduser("~/Documents"),os.W_OK):
                self.openFM.show(os.path.expanduser("~/Documents"))
            else:
                self.openFM.show(directories.externalStorageDir or directories.settings_path)

        export.bind(on_release=promptSet)


        stack.add_widget(export)



        self.streamEditPanel.add_widget(stack)


        #Show recent changes no matter where they are in the tree.
        #TODO needs to be hideable for anti-spoiler purposes in fiction.
        self.streamEditPanel.add_widget(MDToolbar(title="Recent Changes:"))

        for i in daemonconfig.userDatabases[name].getDocumentsByType('post',orderBy='arrival DESC',limit=5):
            x =self.makePostWidget(name,i)
            self.streamEditPanel.add_widget(x)


        self.screenManager.current = "EditStream"

    
    def showSharingCode(self,name,c,wp=True):
        if daemonconfig.ddbservice[0]:
            try:
                localServer = daemonconfig.ddbservice[0].getSharableURL()
            except:
                logging.exception("wtf")
        else:
            localServer=''

        d = {
            'sv':c['Sync'].get('server','') or localServer,
            'vk':c['Sync'].get("syncKey",''),
            'n':name[:24]

        }
        if wp:
            d['sk']=c['Sync'].get('writePassword','')
        else:
            d['sk']=''

        import json
        d=json.dumps(d,indent=0,separators=(',',':'))
        if wp:
            self.showQR(d, "Stream Code(full access)")
        else:
            self.showQR(d, "Stream Code(readonly)")

    def editStreamSettings(self, name):
        db = daemonconfig.userDatabases[name]
        c = db.config


        self.streamEditPanel.clear_widgets()

        self.streamEditPanel.add_widget(Label(size_hint=(
            1, None), halign="center", text=name))
        self.streamEditPanel.add_widget(Label(size_hint=(
            1, None), halign="center", text="file:"+db.filename))


       
        self.streamEditPanel.add_widget(self.makeBackButton())

      

        def save(*a):
            logging.info("SAVE BUTTON WAS PRESSED")
            # On android this is the bg service's job
            db.saveConfig()

            if platform == 'android':
                self.stop_service()
                self.start_service()

        def delete(*a):
            def f(n):
                if n and n == name:
                    daemonconfig.delDatabase(None, n)
                    if platform == 'android':
                        self.stop_service()
                        self.start_service()
                    self.goToStreams()

            self.askQuestion("Really delete?", name, f)

        self.streamEditPanel.add_widget(Label(size_hint=(1, None), halign="center", font_size="24sp",
                                              text='Sync'))

        self.streamEditPanel.add_widget(
            keyBox :=self.settingButton(c, "Sync", "syncKey"))

        self.streamEditPanel.add_widget(
            pBox :=self.settingButton(c, "Sync", "writePassword"))

        self.streamEditPanel.add_widget(Label(size_hint=(1, None), halign="center", font_size="12sp",
                                              text='Keys have a special format, you must use the generator to change them.'))

        def promptNewKeys(*a,**k):
            def makeKeys(a):
                if a=='yes':
                    
                    vk, sk = libnacl.crypto_sign_keypair()
                    vk= base64.b64encode(vk).decode()
                    sk= base64.b64encode(sk).decode()
                    keyBox.text=vk
                    pBox.text=sk
            self.askQuestion("Overwrite with random keys?",'yes',makeKeys)
        
        keyButton = Button(text='Generate New Keys')
        keyButton.bind(on_press=promptNewKeys)
        self.streamEditPanel.add_widget(keyButton)

        self.streamEditPanel.add_widget(
            serverBox:=self.settingButton(c, "Sync", "server"))

        self.streamEditPanel.add_widget(Label(size_hint=(1, None), halign="center",
                                              text='Do not include the http:// '))

        self.streamEditPanel.add_widget(
            self.settingButton(c, "Sync", "serve",'yes'))


        self.streamEditPanel.add_widget(Label(size_hint=(1, None), halign="center",
                                              text='Set serve=no to forbid clients to sync'))

        self.streamEditPanel.add_widget(Label(size_hint=(1, None), halign="center", font_size="24sp",
                                              text='Application'))

        self.streamEditPanel.add_widget(
            self.settingButton(c, "Application", "notifications",'no'))




        def f(*a):
            def g(a):
                try:
                    import json
                    a = json.loads(a)
                    serverBox.text= c['Sync']['server']= a['sv'] or c['Sync']['server']
                    keyBox.text= c['Sync']['syncKey']= a['vk']
                    pBox.text= c['Sync']['writePassword']= a['sk']

                except:
                    pass
            self.askQuestion("Enter Sharing Code",cb=g,multiline=True)


        keyButton = Button(text='Load from Code')
        keyButton.bind(on_press=f)
        self.streamEditPanel.add_widget(keyButton)



        def f(*a):
            self.showSharingCode(name,c)

        keyButton = Button(text='Show Sharing Code')
        keyButton.bind(on_press=f)
        self.streamEditPanel.add_widget(keyButton)

        def f(*a):
            self.showSharingCode(name,c,wp=False)

        keyButton = Button(text='Readonly Sharing Code')
        keyButton.bind(on_press=f)
        self.streamEditPanel.add_widget(keyButton)

        btn1 = Button(text='Save Changes')

        btn1.bind(on_press=save)
        self.streamEditPanel.add_widget(btn1)

        btn2 = Button(text='Delete this stream')

        btn2.bind(on_press=delete)
        self.streamEditPanel.add_widget(btn2)



        def gotoOrphans(*a,**k):
            self.gotoStreamPosts(name,orphansMode=True)

        oButton = Button(text='Show Unreachable Garbage')
        oButton.bind(on_press=gotoOrphans)
        self.streamEditPanel.add_widget(oButton)

        noSpreadsheet = Button(text="Spreadsheet on/off")

        def promptSet(*a):
            from .kivymdfmfork import MDFileManager
            from .. import directories
            try:
                #Needed for android
                self.getPermission('files')
            except:
                logging.exception("cant ask permission")

            def f(selection):
                if selection=='on':
                    daemonconfig.userDatabases[name].enableSpreadsheetEval = True
                else:
                    daemonconfig.userDatabases[name].enableSpreadsheetEval = False
            
            if hasattr(daemonconfig.userDatabases[name],'enableSpreadsheetEval'):
                esf=daemonconfig.userDatabases[name].enableSpreadsheetEval
            else:
                esf=True
            
            self.askQuestion("Allow Spreadsheet Functions?",'on' if esf else 'off',f)

        noSpreadsheet.bind(on_release=promptSet)
        self.streamEditPanel.add_widget(noSpreadsheet)
        self.streamEditPanel.add_widget(self.saneLabel("Disabling only takes effect for this session. Use this feature if a stream is loading too slowly, to allow you to fix the offending expression.",  self.streamEditPanel))





        self.screenManager.current = "EditStream"


    def makeStreamsPage(self):
        "Prettu much just an empty page filled in by the specific goto functions"

        screen = Screen(name='Streams')
        self.servicesScreen = screen

        self.streamsEditPanelScroll = ScrollView(size_hint=(1, 1))

        self.streamsEditPanel = BoxLayout(
            orientation='vertical',adaptive_height= True, spacing=5,size_hint=(1, None))
        self.streamsEditPanel.bind(
            minimum_height=self.streamsEditPanel.setter('height'))

        self.streamsEditPanelScroll.add_widget(self.streamsEditPanel)

        screen.add_widget(self.streamsEditPanelScroll)

        return screen



    def goToStreams(self,*a):
        
        "Go to a page wherein we can list user-modifiable services."
        self.streamsEditPanel.clear_widgets()

        layout = self.streamsEditPanel       

        bar = BoxLayout( spacing=10,adaptive_height=True,size_hint=(1,None))

        stack = StackLayout( spacing=10,adaptive_height=True,size_hint=(1,None))        
        layout.add_widget(bar)
        layout.add_widget(MDToolbar(title="My Streams"))



        layout.add_widget(stack)



        def upOne(*a):
            self.gotoMainScreen()

        btn1 = Button(text='Up')

        btn1.bind(on_press=upOne)

        bar.add_widget(btn1)
        bar.add_widget(self.makeBackButton())


        btn2 = Button(text='Create a Stream')


        btn2.bind(on_press=self.promptAddStream)
        stack.add_widget(btn2)


        def f(selection):
            if selection:
                dn = 'file:'+os.path.basename(selection)
                while dn in daemonconfig.userDatabases:
                    dn=dn+'2'
                try:
                    daemonconfig.loadUserDatabase(selection,dn)
                    self.editStream(dn)
                except:
                    logging.exception(dn)

            self.openFM.close()

        #This lets us view notebook files that aren't installed.
        def promptOpen(*a):

            try:
                #Needed for android
                self.getPermission('files')
            except:
                logging.exception("cant ask permission")

            from .kivymdfmfork import MDFileManager
            from . import directories
            self.openFM= MDFileManager(select_path=f)

            if os.path.exists("/storage/emulated/0/Documents") and os.access("/storage/emulated/0/Documents",os.W_OK):
                self.openFM.show("/storage/emulated/0/Documents")
            elif os.path.exists(os.path.expanduser("~/Documents")) and os.access(os.path.expanduser("~/Documents"),os.W_OK):
                self.openFM.show(os.path.expanduser("~/Documents"))
            else:
                self.openFM.show(directories.externalStorageDir or directories.settings_path)

            

        btn1 = Button(text='Open Book File')

        btn1.bind(on_press=promptOpen)

        stack.add_widget(btn1)



        def goHere():
            self.screenManager.current = "Streams"
        self.backStack.append(goHere)
        self.backStack=self.backStack[-50:]

        layout.add_widget(MDToolbar(title="Open Streams:"))

        try:
            s = daemonconfig.userDatabases
            time.sleep(0.5)
            for i in s:
                layout.add_widget(
                    self.makeButtonForStream(i))
                try:
                    for j in daemonconfig.userDatabases[i].connectedServers:
                        if daemonconfig.userDatabases[i].connectedServers[j]>(time.time()-(10*60)):
                            w='online'
                        else:
                            w='idle/offline'
                        layout.add_widget(self.saneLabel(j[:28]+": "+w, layout))
                except:
                    logging.exception("Error showing node status")

        except Exception:
            logging.info(traceback.format_exc())

        self.screenManager.current = "Streams"

    def makeButtonForStream(self, name):
        "Make a button that, when pressed, edits the stream in the title"

        btn = Button(text=name)

        def f(*a):
            self.editStream(name)
        btn.bind(on_press=f)
        return btn

    def promptAddStream(self, *a, **k):
        def f(v):
            if v:
                daemonconfig.makeUserDatabase(None, v)
                self.editStream(v)

        self.askQuestion("New Stream Name?", cb=f)



    def makeStreamEditPage(self):
        "Prettu much just an empty page filled in by the specific goto functions"

        screen = Screen(name='EditStream')
        self.servicesScreen = screen

        self.streamEditPanelScroll = ScrollView(size_hint=(1, 1))

        self.streamEditPanel = BoxLayout(
            orientation='vertical',adaptive_height= True, spacing=5,size_hint=(1, None))
        self.streamEditPanel.bind(
            minimum_height=self.streamEditPanel.setter('height'))

        self.streamEditPanelScroll.add_widget(self.streamEditPanel)

        screen.add_widget(self.streamEditPanelScroll)

        return screen

