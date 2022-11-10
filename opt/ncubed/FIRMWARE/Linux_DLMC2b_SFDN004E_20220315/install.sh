#!/bin/bash
# elevate
[ "$UID" -eq 0 ] || exec sudo bash "$0" "$@"

cd $(dirname $0)
chmod a+r .
chmod a+x .
chmod a+r BIN DLMC2
chmod a+x BIN DLMC2

if $(hdparm -I /dev/sda | grep -q SFDN004E)
then
echo "Firmware allready installed"
else
printf "/dev/sda\n" | ./DLMC2
fi