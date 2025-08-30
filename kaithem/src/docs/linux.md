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