#!/bin/bash
# elevate
[ "$UID" -eq 0 ] || exec sudo bash "$0" "$@"

cd $(dirname $0)
chmod a+r .
chmod a+x .
chmod a+r BIN DLMC2
chmod a+x BIN DLMC2

CURRENT_FIRMWARE=$(hdparm -I /dev/sda)
printf "
$(printf "$CURRENT_FIRMWARE"| grep Firmware)
$(printf "$CURRENT_FIRMWARE"| grep Model)
\n"
if $(printf "$CURRENT_FIRMWARE" | grep -q -i "256GB SATA Flash Drive")
then
    if $(printf "$CURRENT_FIRMWARE" | grep -q -i "SFDN004E")
    then
        echo "Firmware allready installed, exiting..."
    else
        printf "/dev/sda\n" | ./DLMC2
    fi
else
    echo "This is not the model you're looking for"
fi