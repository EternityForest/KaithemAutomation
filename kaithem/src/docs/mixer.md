# JACK/Mixing Board


Kaithem includes an audio mixer that is enabled when you configure the use of the JACK server(Set the JACK mode to "manage"). It only works on Linux.

The mixing board is based on channel strips, which should be familiar if you have used a physical mixing board.

## WARNING

This is beta functionality. It may crash. It may segfault. etc.

## Dependancies

 For the mixer and the JACK subsystem to work correctly, you will need several dependancies that are not included.
 They are included in the kaithem .deb package recommended section, and you can install on debian with:

 ` sudo apt install python3-jack-client python3-gst-1.0 jack-tools
   sudo apt install jackd2 gstreamer1.0-plugins-good gstreamer1.0-plugins-bad a2jmidid
   sudo apt install swh-plugins tap-plugins caps gstreamer1.0-plugins-ugly
`

## Channel Strips

Every strip creates two JACK clients. <name>_in and <name>_out.  You can configure these to automatically connect to a client or port.  Connnecting clients to ports or vice versa works as expected, mono is split to stereo or combined as needed.

The connections are maintained even if the other end dissapears and returns, so you don't have to worry about briefly unplugging a
sound card taking out your show.

Generally, you leave the input blank and target it with kaithem.sound.play, or you connect it to a microphone input.

To create a master channel, you just need to create a channel that outputs to the soundcard, and connect the other channels to the input of that.

Channels have a list of effects, and a fader. Audio comes in the input and is processed through them, finally reaching the output.

### Tagpoint control
Every channel fader is a tagpoint named /jackmixer/channels/CHANNEL/fader.  Moving the slider simply sets the default claim at priority
50, but you can set this claim(Usually the way to go) or even completely override the fader and lock out manual control.

## Presets

The state of the entire board can be saved as a named preset. The preset called "default" is loaded at boot.

## Soundcards

When kaithem is managing JACK, it will create a jack client for every additional soundcard. These have generated persistent names based on what USB or PCI port they are plugged into. They will stay the same regardless of what order they are detected in.

It will also use a2jmidid to bring all avbailable MIDI devices into JACK.  Since that program does not allow control of names,
we assign aliases.

### Name Assignment

Names are assigned through a fairly nontrival algorithm much like a customized hash, optimized for low(usually zero) possibility of collision on common setups.

There is a chance that names can collide if you have deep chains of hubs. In this case whichever was detected second is assigned a new name. This will still be consistent as long as the same cards are in the same ports.


Names look like "USB_coloratlas1446o" and "USB_coloratlas1446i" for output and input respectively.

For USB cards, the first word is derived from the USB controller the card is on pllus which port of that controller it's on, the second is derived from the USB port path.  This means two cards on the same hub will have the same first word.

If you move a hub between root-level ports, cards on it will keep their second word and change the first.

For PCI or other devices, the first word is derived from the address and the second from the name.

