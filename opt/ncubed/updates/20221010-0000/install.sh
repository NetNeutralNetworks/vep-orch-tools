#!/bin/bash
##################################################################################
# elevate
##################################################################################
[ "$UID" -eq 0 ] || exec sudo bash "$0" "$@"

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" &> /dev/null && pwd)
ROOTDIR="/opt/ncubed"

# cleanup original setup
systemctl disable firewalld
systemctl stop firewalld
systemctl mask firewalld
apt remove firewalld

mkdir -p $ROOTDIR
rm $ROOTDIR/*
rm -r $ROOTDIR/*.service

########################################################
# install update
########################################################
cp -p -r $SCRIPT_DIR/ncubed/* $ROOTDIR

# clean netplan
rm /etc/netplan/*
cp  $ROOTDIR/config/netplan-config.yaml /etc/netplan/config.yaml
netplan apply
systemctl restart network-manager.service

# update etc files
cp -p -r $ROOTDIR/etc/* /etc/

# make sure bin dir is executiable
chmod +x $ROOTDIR/bin/*

# add cli to globally available tools
ln $ROOTDIR/bin/n3.py /usr/local/bin/n3

# install services
chmod +x $ROOTDIR/network.service/install
$ROOTDIR/network.service/install

chmod +x $ROOTDIR/callhome.service/install
$ROOTDIR/callhome.service/install

# FIX: sudo unable to reolve hostname
echo ::1 $(hostname) >> /etc/hosts