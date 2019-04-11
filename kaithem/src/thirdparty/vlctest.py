import vlc
instance = vlc.Instance()


class VLCPlayer():
    def __init__(self,f):
        self.player = self.Instance.media_player_new()
        self.player.set_media(self.Media)
        
        
        
        

import vlc
import time
print("k")
p = instance.media_player_new()

p.set_media(instance.media_new("foo.wav"))
device = p.audio_output_device_enum()
while device:
    print ("playing on...")
    print (device.contents.device)
    print (device.contents.description)

    p.audio_output_device_set(None, device.contents.device)
    time.sleep(3)

    device = device.contents.next

p.stop()
