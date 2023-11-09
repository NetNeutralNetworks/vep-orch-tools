#!/bin/bash
###############################################################################>
# elevate
###############################################################################>
[ "$UID" -eq 0 ] || exec sudo bash "$0" "$@"

apt update
apt upgrade
apt dist-upgrade
apt autoremove
apt install update-manager-core
do-release-upgrade -d
