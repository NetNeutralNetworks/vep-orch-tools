#!/bin/bash
##################################################################################
# elevate
##################################################################################
[ "$UID" -eq 0 ] || exec sudo bash "$0" "$@"

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" &> /dev/null && pwd)
ROOTDIR="/opt/ncubed"

systemctl disable firewalld
systemctl stop firewalld
systemctl mask firewalld

mkdir -p $ROOTDIR
rm $ROOTDIR/*
rm -r $ROOTDIR/*.service
cp -p -r $SCRIPT_DIR/ncubed/* $ROOTDIR
systemctl daemon-reload
chmod +x $ROOTDIR/oneshot.service/install
$ROOTDIR/oneshot.service/install

chmod +x $ROOTDIR/callhome.service/install
$ROOTDIR/callhome.service/install

cp -p -r $ROOTDIR/etc/* /etc/

# add cli to globally available tools
ln -sfn $ROOTDIR/bin/n3.py /usr/local/bin/n3