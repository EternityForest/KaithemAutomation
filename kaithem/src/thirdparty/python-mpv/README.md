# python-mpv

Control mpv from Python using JSON IPC.

## About

*mpv.py* allows you to start an instance of the [mpv](http://mpv.io) video
player and control it using mpv's [JSON IPC API](http://mpv.io/manual/master/#json-ipc).

At the moment, think of it more as a toolbox to write your own customized
controller. There is no high-level API (yet). Instead, *mpv.py* offers
everything you should require to implement the commands you need and to receive
events.

*mpv.py* requires Python >= 3.2.

## License

Copyright(c) 2015, Lars Gustäbel <lars@gustaebel.de>

It is distributed under the MIT License.
