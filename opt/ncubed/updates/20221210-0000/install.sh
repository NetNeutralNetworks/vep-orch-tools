#!/bin/bash
##################################################################################
# elevate
##################################################################################
[ "$UID" -eq 0 ] || exec sudo bash "$0" "$@"

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" &> /dev/null && pwd)
ROOTDIR="/opt/ncubed"

mkdir -p $ROOTDIR
find $ROOTDIR -maxdepth 1 -type f -delete \( ! -iname "meta.yaml" ! -iname "system.yaml" \)
rm -r $ROOTDIR/*.service

########################################################
# install update
########################################################
# update config
mkdir -p $ROOTDIR/config/local
find $ROOTDIR/config -maxdepth 1 -type f -name '*' -exec mv -n {} $ROOTDIR/config/local \;

cp -p -r $SCRIPT_DIR/ncubed/* $ROOTDIR

# clean netplan
rm /etc/netplan/*
NETPLAN_CONFIG_FILE=$ROOTDIR/config/local/netplan-config.yaml
if [ -f $NETPLAN_CONFIG_FILE ]
then
  printf "$NETPLAN_CONFIG_FILE exists, using that."
else
  printf "using default example file"
  cp  $ROOTDIR/config/local/netplan-config.yaml.example $NETPLAN_CONFIG_FILE
fi

ln -s $ROOTDIR/config/local/netplan-config.yaml /etc/netplan/config.yaml
netplan apply


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

# FIX: sudo unable to resolve hostname
sed -i '/::1/d' /etc/hosts
echo ::1 $(hostname) >> /etc/hosts

# just a hack
printf -- "---
platform: $(sudo /usr/sbin/dmidecode -s system-product-name)
serial: $(sudo /usr/sbin/dmidecode -s system-serial-number)
" > /opt/ncubed/system.yaml

######################################
# Tweak cloudinit
######################################
# make hostname changes persistent
echo "preserve_hostname: true" > /etc/cloud/cloud.cfg.d/99_hostname.cfg

# disable cloudinit networking
echo "network: {config: disabled}" > /etc/cloud/cloud.cfg.d/99-custom-networking.cfg
