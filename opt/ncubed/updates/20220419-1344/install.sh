#!/bin/bash
##################################################################################
# elevate
##################################################################################
[ "$UID" -eq 0 ] || exec sudo bash "$0" "$@"

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" &> /dev/null && pwd)

rm -r /opt/ncubed/*.service
cp -r $SCRIPT_DIR/ncubed/* /opt/ncubed
systemctl daemon-reload
chmod +x /opt/ncubed/oneshot.service/install
/opt/ncubed/oneshot.service/install

cp -r /opt/ncubed/etc/* /etc/
