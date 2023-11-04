class MPlayerWrapper(SoundWrapper):
    backendname = "MPlayer"

    # What this does is it keeps a reference to the sound player process and
    # If the object is destroyed it destroys the process stopping the sound
    # It also abstracts checking if its playing or not.
    class MPlayerSoundContainer(object):
        def __init__(self, filename, vol, start, end, extras, **kw):
            f = open(os.devnull, "w")
            g = open(os.devnull, "w")
            self.paused = False

            cmd = ["mplayer", "-slave", "-quiet",
                   "-softvol", "-ss", str(start)]
            if end:
                cmd.extend(["-endpos", str(end)])

            if "audiooutput" in kw:
                cmd.extend(["-ao", kw['output']])

            if "videooutput" in kw:
                if util.which("X"):
                    cmd.extend(["-display", kw['videooutput']])

            if "fullscreen" in kw and kw['fullscreen']:
                cmd.extend(["-fs"])

            if 'eq' in extras:
                if extras['eq'] == 'party':
                    cmd.extend(
                        ['-af', 'equalizer=0:1.5:2:-7:-10:-5:-10:-10:1:1,volume=3'])

            self.started = time.time()
            cmd.append(filename)
            self.process = subprocess.Popen(
                cmd, stdin=subprocess.PIPE, stdout=f, stderr=g)

        def __del__(self):
            try:
                self.process.terminate()
            except:
                pass

        def is_playing(self):
            self.process.poll()
            return self.process.returncode == None

        def position(self):
            return time.time() - self.started

        def setVol(self, volume):
            if self.is_playing():
                try:
                    self.process.stdin.write(
                        bytes("volume "+str(volume*100)+" 1\n", 'utf8'))
                    self.process.stdin.flush()
                    self.paused = False
                except:
                    pass

        def pause(self):
            try:
                if not self.paused:
                    self.process.stdin.write(bytes("pause \n", "utf8"))
                    self.process.stdin.flush()
                    self.paused = True
            except:
                pass

        def resume(self):
            try:
                if self.paused:
                    self.process.stdin.write(bytes("pause \n", "utf8"))
                    self.process.stdin.flush()
                    self.paused = False
            except:
                pass

    def play_sound(self, filename, handle="PRIMARY", **kwargs):

        if 'volume' in kwargs:
            # odd way of throwing errors on non-numbers
            v = float(kwargs['volume'])
        else:
            v = 1

        if 'start' in kwargs:
            # odd way of throwing errors on non-numbers
            start = float(kwargs['start'])
        else:
            start = 0

        if 'end' in kwargs:
            # odd way of throwing errors on non-numbers
            end = float(kwargs['end'])
        else:
            end = None

        if 'output' in kwargs:
            e = {"output": kwargs['output']}
        else:
            e = {}

        if 'eq' in kwargs:
            extras = {'eq': kwargs['eq']}
        else:
            extras = {}
        # Those old sound handles won't garbage collect themselves
        self.deleteStoppedSounds()
        # Raise an error if the file doesn't exist
        if not os.path.isfile(filename):
            raise ValueError("Specified audio file'" +
                             filename+"' does not exist")

        # Play the sound with a background process and keep a reference to it
        self.runningSounds[handle] = self.MPlayerSoundContainer(
            filename, v, start, end, extras, **e)

    def stopSound(self, handle="PRIMARY"):
        # Delete the sound player reference object and its destructor will stop the sound
        if handle in self.runningSounds:
            # Instead of using a lock lets just catch the error is someone else got there first.
            try:
                del self.runningSounds[handle]
            except KeyError:
                pass

    def is_playing(self, channel="PRIMARY"):
        "Return true if a sound is playing on channel"
        try:
            return self.runningSounds[channel].is_playing()
        except KeyError:
            return False

    def setVolume(self, vol, channel="PRIMARY"):
        "Return true if a sound is playing on channel"
        try:
            return self.runningSounds[channel].setVol(vol)
        except KeyError:
            pass

    def pause(self, channel="PRIMARY"):
        "Return true if a sound is playing on channel"
        try:
            return self.runningSounds[channel].pause()
        except KeyError:
            pass

    def resume(self, channel="PRIMARY"):
        "Return true if a sound is playing on channel"
        try:
            return self.runningSounds[channel].resume()
        except KeyError:
            pass
