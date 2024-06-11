# Kaithem MIDI input support

All connected MIDI devices that RtMidi can see will be linked to the message bus and tag points by name.


You can see a list of all these names on the about page.

## Tag Points

Midi messages from MyController will make the following tags

## /midi/MyController/1.cc[0]

Channel 1 Control change 0 value.

## /midi/MyController/1.pitch

ch1 pitch wheel


## /midi/MyController/1.note

Last active note event. Annotation is velocity.  noteOff represents a 0.

You cannot use this for polyphonic input as noteOff just sets everything to 0 and doesn't tell you what note specifically it was.

It only exists for convenient use of keyboards to trigger lighting groups and the like.



## Message Bus

The topic is /midi/MyController, the messages are:

('noteon', ch, pitch, vel)
('noteoff', ch, pitch)
('cc', ch, number, val)
('pitch', ch, val)


Note: the new fluidsynth plugin uses the message bus, NOT jack. This is because a2jmidid was causing too many problems on some systems.

It does not pay attention to tag point values.