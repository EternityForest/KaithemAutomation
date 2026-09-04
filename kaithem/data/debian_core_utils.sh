#!/bin/bash

# These minimal utils are present in all the kaithem runtime images
# To allow running the setup utils, and also for some extremely basic
# debugging

apt-get install -y \
    tzdata ca-certificates curl wget \
    iputils-ping make nano busybox