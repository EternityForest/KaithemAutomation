## Linux Cheat Sheet


## Systemd

## Find what made the boot so slow

`systemd-analyze critical chain`

## Process

### Search the list of processes

`ps -aux | grep <search>`


## Network

## What is using a port?

`netstat -tulpn | grep :<port>`

## What are my IP addresses?

`ip a`

## Copy an entire folder

These kinds of commands tend to care about trailing slashes.

Replace with your host, folder, etc:

`scp -r SourceFolder pi@192.168.21.1:/Destination/Location`


## Arduino

### "hardware" folder in the sketchbook

When manually installing a platform, it should look like:

`
{Sketchbook Folder}/hardware/{VENDOR_NAME}/{ARCHITECTURE}/boards.txt
{Sketchbook Folder}/hardware/{VENDOR_NAME}/{ARCHITECTURE}/variants/
etc
`

Note that there's no feature to have multiple packages or versions under one architecture name,
instead, the package contains multiple boards, so just use the VENDOR_NAME to organize different
projects.
