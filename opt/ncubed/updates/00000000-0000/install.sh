#!/bin/bash
##################################################################################
# elevate
##################################################################################
[ "$UID" -eq 0 ] || exec sudo bash "$0" "$@"

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" &> /dev/null && pwd)
ROOTDIR="/opt/ncubed"

# cleanup original setup
for pkg in firewalld docker.io docker-compose
do
	if [ $(dpkg-query -W -f='${Status}' $pkg 2>/dev/null | grep -c "ok installed") -eq 1 ];
    then echo remove; 
		echo Removing: $pkg
        systemctl disable $pkg
        systemctl stop $pkg
        systemctl mask $pkg
        apt -y remove $pkg
	else
		echo not installed: $pkg 
    fi
done

apt -y autoremove

for svc in ncubed-oneshot ncubed-startup
do
	if $(systemctl status ncubed-* | grep -q ncubed-oneshot)
	then
		echo Removing: $svc
		systemctl stop $svc
		systemctl disable $svc
	else
		echo not installed: $svc 
	fi
done

mkdir -p $ROOTDIR
find $ROOTDIR -maxdepth 1 -type f -delete \( ! -iname "meta.yaml" ! -iname "system.yaml" \)
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

chmod +x /etc/libvirt/hooks/qemu
systemctl restart libvirtd
touch /var/log/ncubed.libvirt.log

# FIX: sudo unable to reolve hostname
echo ::1 $(hostname) >> /etc/hosts

# just a hack
printf -- "---
platform: $(sudo /usr/sbin/dmidecode -s system-family)
serial: $(sudo /usr/sbin/dmidecode -s system-serial-number)
" > /opt/ncubed/system.yaml