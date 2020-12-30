#This is the kivy android app.
#IT DOESN'T WORK ON NON-ANDROID!!!! Use kaithem.py

from kivy.app import App
from kivy.lang import Builder
from kivy.utils import platform
from kivy.uix.button import Button
from kivy.uix.label import Label

from kivy.uix.boxlayout import BoxLayout
import threading
from kivy.uix.screenmanager import ScreenManager, Screen

import time,sys

class ServiceApp(App):

    def stop_service(self,foo=None):
        if self.service:
            self.service.stop()
            self.service = None
        else:
            sys.exit()

    def start_service(self,foo=None):
        if self.service:
            self.service.stop()
            self.service = None

        if platform == 'android':
                from android import AndroidService
                service = AndroidService('KaithemAutomation', 'running')
                service.start('service started')
                self.service = service
        else:
            def f():
                from src import main            
            t = threading.Thread(target=f,daemon=True)
            t.start()

    def build(self):
        self.service=None

        self.start_service()

        # Create the manager
        sm = ScreenManager()
        sm.add_widget(self.makeMainScreen())

        self.screenManager = sm
        return sm

    

    def makeMainScreen(self):
        mainScreen = Screen(name='Main')

    
        layout = BoxLayout(orientation='vertical')
        mainScreen.add_widget(layout)
        label = Label(text='KaithemAutomation Service Controller')
        layout.add_widget(label)
        
        
        btn2 = Button(text='Go to the GUI')
        btn2.bind(on_press=self.gotoGui)

        btn3 = Button(text='Stop the service')
        btn3.bind(on_press=self.stop_service)

        btn4 = Button(text='Start or restart.')
        btn4.bind(on_press=self.start_service)

        layout.add_widget(btn2)
        layout.add_widget(btn3)
        layout.add_widget(btn4)

        return mainScreen



    
    def gotoGui(self):
        self.openInBrowser("http://localhost:8002")


    def openInBrowser(self,link):
        "Opens a link in the browser"
        if platform == 'android':
            from jnius import autoclass
            # import the needed Java class
            PythonActivity = autoclass('org.renpy.android.PythonActivity')
            Intent = autoclass('android.content.Intent')
            Uri = autoclass('android.net.Uri')

            # create the intent
            intent = Intent()
            intent.setAction(Intent.ACTION_VIEW)
            intent.setData(Uri.parse(link))

            # PythonActivity.mActivity is the instance of the current Activity
            # BUT, startActivity is a method from the Activity class, not from our
            # PythonActivity.
            # We need to cast our class into an activity and use it
            currentActivity = cast('android.app.Activity', PythonActivity.mActivity)
            currentActivity.startActivity(intent)
        else:
            import webbrowser
            webbrowser.open(link)


if __name__ == '__main__':
    ServiceApp().run()
