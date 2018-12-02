tinytag 
=======

tinytag is a library for reading music meta data of MP3, OGG, OPUS, MP4, M4A, FLAC, WMA and Wave files with python

[![Build Status](https://travis-ci.org/devsnd/tinytag.png?branch=master)](https://travis-ci.org/devsnd/tinytag)
[![Coverage Status](https://coveralls.io/repos/devsnd/tinytag/badge.png)](https://coveralls.io/r/devsnd/tinytag)

Features:

  * Read tags, length and IDv3 cover images of music files
  * supported formats
    * MP3 (ID3 v1, v1.1, v2.2, v2.3+)
    * Wave
    * OGG
    * OPUS
    * FLAC
    * WMA
    * MP4/M4A
  * pure python
  * supports python 2.6+ and 3.2+
  * is tested 
  * Just a few hundred lines of code (just include it in your project!) 

tinytag only provides the minimum needed for _reading_ MP3, OGG, OPUS, MP4, M4A, FLAC, WMA and Wave meta-data.
It can determine track number, total tracks, title, artist, album, year, duration and more.

    from tinytag import TinyTag
    tag = TinyTag.get('/some/music.mp3')
    print('This track is by %s.' % tag.artist)
    print('It is %f seconds long.' % tag.duration)

List of possible attributes you can get with TinyTag:

    tag.album         # album as string
    tag.albumartist   # album artist as string
    tag.artist        # artist name as string
    tag.audio_offset  # number of bytes before audio data begins
    tag.bitrate       # bitrate in kBits/s
    tag.disc          # disc number
    tag.disc_total    # the total number of discs
    tag.duration      # duration of the song in seconds
    tag.filesize      # file size in bytes
    tag.genre         # genre as string
    tag.samplerate    # samples per second
    tag.title         # title of the song
    tag.track         # track number as string
    tag.track_total   # total number of tracks as string
    tag.year          # year or data as string

Additionally you can also get cover images from ID3 tags:

    tag = TinyTag.get('/some/music.mp3', image=True)
    image_data = tag.get_image()

supported python versions:

 * 2.6+
 * 3.2+
 * pypy

and possibly more.

Changelog:

 * 0.19.0 (2018/02/11): fixed corrupted images for some mp3s (#45)
 * 0.18.0 (2017/04/29): fixed wrong bitrate and crash when parsing xing header
 * 0.17.0 (2016/10/02): supporting ID3v2.2 images
 * 0.16.0 (2016/08/06): MP4 cover image support
 * 0.15.2 (2016/08/06): fixed crash for malformed MP4 files (#34)
 * 0.15.0 (2016/08/06): fixed decoding of UTF-16LE ID3v2 Tags, improved overall stability
 * 0.14.0 (2016/06/05): MP4/M4A and Opus support
