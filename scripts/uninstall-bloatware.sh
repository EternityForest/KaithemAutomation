#!/bin/bash

#    ___ _                              
#   / __\ | ___  __ _ _ __  _   _ _ __  
#  / /  | |/ _ \/ _` | '_ \| | | | '_ \ 
# / /___| |  __/ (_| | | | | |_| | |_) |
# \____/|_|\___|\__,_|_| |_|\__,_| .__/ 
#                                |_|    

## Get rid of really big packages we don't need that are mostly nonfree
####################################################################################################################

# Move most of the deletion up front. Otherwise  it will get in the way and slow down the whole build.
! apt purge -y libpam-chksshpwd
! apt purge -y valgrind

! apt purge -y wolfram-engine wolframscript
! apt purge -y sonic-pi-samples
#apt-get -y install libreoffice-draw libreoffice-writer libreoffice-calc
! apt purge -y nuscratch
! apt purge -y scratch2
! apt purge -y scratch3
! apt purge -y scratch
! apt purge -y minecraft-pi
! apt purge -y python-minecraftpi
! apt purge -y realvnc-vnc-viewer
! apt purge -y gpicview
! apt purge -y oracle-java8-jdk
! apt purge -y oracle-java7-jdk
! apt purge -y tcsh
! apt purge -y smartsim
! apt purge -y kicad

# I would like to get rid of this but people seem to like it so much it will stir up trouble... leave it on distros that have it
# ! apt-get -y purge firefox


# Old versions
! apt purge -y gcc-7
! apt purge -y gcc-8
! apt purge -y gcc-9

! apt purge -y ^dillo$  ^idle3$  ^smartsim$ ^sonic-pi$  ^epiphany-browser$  ^python-minecraftpi$ ^bluej$ 
! apt purge -y ^greenfoot$  ^greenfoot-unbundled$  ^claws-mail$ ^claws-mail-i18n$

! apt purge -y code-the-classics
! apt purge -y openjdk-11-jdk
! apt purge -y openjdk-11-jdk-headless
! apt purge -y bluej

# Might need to use this if you get chrome file chooser crashes.
# ! apt purge -y xdg-desktop-portal

! apt purge -y mu-editor

! rm -r /opt/Wolfram
! rm -r /usr/share/code-the-classics
! rm -r /home/$(id -nu $KAITHEM_UID)/MagPi/*.pdf
! rm -r /home/$(id -nu $KAITHEM_UID)/Bookshelf/Beginners*.pdf


apt autoremove -y --purge
