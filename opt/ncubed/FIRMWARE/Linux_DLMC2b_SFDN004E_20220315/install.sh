#!/bin/bash
# elevate
[ "$UID" -eq 0 ] || exec sudo bash "$0" "$@"

cd $(dirname $0)
chmod a+r .
chmod a+x .
chmod a+r BIN DLMC2
chmod a+x BIN DLMC2

CURRENT_FIRMWARE=$(hdparm -I /dev/sda | grep -i firmware)
printf "\n$CURRENT_FIRMWARE\n\n"
if $(echo $CURRENT_FIRMWARE | grep -q SFDN004E)
then
echo "Firmware allready installed, exiting..."
else
printf "/dev/sda\n" | ./DLMC2
fi