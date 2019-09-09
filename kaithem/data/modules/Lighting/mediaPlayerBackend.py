## Code outside the data string, and the setup and action blocks is ignored
## If manually editing, you must reload the code through the web UI
__data__="""
continual: false
enable: true
once: true
priority: interactive
rate-limit: 0.0
resource-timestamp: 1566264981226445
resource-type: event
versions:
  __draft__:
    action: pass
    continual: false
    enable: true
    once: true
    priority: interactive
    rate-limit: 0.0
    resource-type: event
    setup: "#This code runs once when the event loads. It also runs when you save\\
      \\ the event during the test compile\\r\\n#and may run multiple times when kaithem\\
      \\ boots due to dependancy resolution\\r\\n__doc__=''\\r\\n\\r\\nimport os,time, threading\\r\\
      \\n\\r\\nmodule.mediaAPI = kaithem.widget.APIWidget()\\r\\nmodule.mediaAPI.require(\\"\\
      /lights/lightboard.admin\\")\\r\\n\\r\\nallPlayers = {}\\r\\n\\r\\nlock = threading.lock()\\r\\
      \\n\\r\\n\\r\\nclass MediaPlayer():\\r\\n    def __init__(self, name):\\r\\n        self.name=name\\r\\
      \\n        #Entries are UUID, filename\\r\\n        self.playlist = []\\r\\n    \\
      \\    self.currentSong = ''\\r\\n        self.handleName = \\"chandlerplayer_\\"\\
      +name\\r\\n        self.playing = False\\r\\n        with lock:\\r\\n            allPlayers[name]=self\\r\\
      \\n        \\r\\n\\r\\n    def _getPointer(self):\\r\\n        if not self.playlist:\\r\\
      \\n            return\\r\\n        if not self.currentSong:\\r\\n            return\\
      \\ self.playlist[0]\\r\\n        for i in range(len(playlist)):\\r\\n           \\
      \\ if playlist[i][0]==self.currentSong:\\r\\n                return i\\r\\n\\r\\n \\
      \\   def nextSong(self):\\r\\n        with lock:\\r\\n            p= self._getPointer()\\r\\
      \\n            kaithem.sound.stop(self.handleName)\\r\\n\\r\\n            if not\\
      \\ p:\\r\\n                return\\r\\n\\r\\n            if p>=len(self.playlist):\\r\\
      \\n                self.handleEndOfPlaylist()\\r\\n                return\\r\\n \\
      \\           self.currentSong = self.playlist[p+1][0]\\r\\n\\r\\n            kaithem.sound.play(self.playlist[p+1][1],handle=self.handleName,\\
      \\ extraPaths=kaithem.registry.get(\\"lighting/soundfolders\\"))\\r\\n\\r\\n    def\\
      \\ check(self):\\r\\n        if kaithem.sound.isPlaying(self.handleName):\\r\\n \\
      \\           return\\r\\n        \\r\\n        if not self.playing:\\r\\n         \\
      \\   return\\r\\n        \\r\\n        p= self._getPointer()\\r\\n        if p>=len(self.playlist):\\r\\
      \\n            self.handleEndOfPlaylist()\\r\\n            return\\r\\n        \\r\\
      \\n        self.nextSong()\\r\\n\\r\\n    def handleEndOfPlaylist(self):\\r\\n    \\
      \\    self.playing=False\\r\\n        self.currentSong=''\\r\\n\\r\\n\\r\\n\\r\\ndef listMedia():\\r\\
      \\n    global mediaList\\r\\n    folders = kaithem.registry.get(\\"lighting/soundfolders\\"\\
      )\\r\\n    filenames=[]\\r\\n    for i in folders:\\r\\n        for top, dirs,files\\
      \\ in os.path.walk(i):\\r\\n            for k in files:\\r\\n                filenames.append(os.path.basename(k))\\r\\
      \\n    mediaList = filenames\\r\\n    return mediaList\\r\\n\\r\\ndef f(user, msg):\\r\\
      \\n    if msg[0]==\\"listMedia\\":\\r\\n        module.mediaAPI.send([\\"mediaFiles\\"\\
      , listMedia])\\r\\n    \\r\\n    if msg[0]==\\"listPlayers\\":\\r\\n        with lock:\\r\\
      \\n            module.mediaAPI.send([\\"mediaFiles\\", [allPlayers.keys()])\\r\\n\\
      \\r\\n    if msg[0]==\\"getPlayer\\":\\r\\n        module.mediaAPI.send([\\"playerData\\"\\
      , allPlayers[msg[1]].toDict()])\\r\\n\\r\\n\\r\\n\\r\\nmodule.mediaAPI.attach(f)"
    trigger: 'False'

"""

__trigger__='False'

if __name__=='__setup__':
    #This code runs once when the event loads. It also runs when you save the event during the test compile
    #and may run multiple times when kaithem boots due to dependancy resolution
    __doc__=''
    
    import os,time
    
    module.mediaAPI = kaithem.widget.APIWidget()
    module.mediaAPI.require("/lights/lightboard.admin")
    
    
    def listMedia():
        global mediaList
        folders = kaithem.registry.get("lighting/soundfolders")
        filenames=[]
        for i in folders:
            for top, dirs,files in os.path.walk(i):
                for k in files:
                    filenames.append(os.path.basename(k))
        mediaList = filenames
        return mediaList
    
    def f(user, msg):
        if msg[0]=="listMedia":
            module.mediaAPI.send(["mediaFiles", listMedia])
    
    module.mediaAPI.attach(f)
    

def eventAction():
    pass
    
