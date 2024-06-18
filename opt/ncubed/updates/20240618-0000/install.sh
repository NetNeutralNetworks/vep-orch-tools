#!/bin/bash
function usage {
printf "
Please read the documentation for hidden commands

"
}
while [ $# -gt 0 ]; do
  case $1 in
    -h | --help)
      usage
      exit 0
      ;;
    --skip_version_check)
      skip_version_check=true
      ;;
    *)
      echo "Invalid option: $1" >&2
      usage
      exit 1
      ;;
  esac
  shift
done

##################################################################################
# elevate
##################################################################################
[ "$UID" -eq 0 ] || exec sudo bash "$0" "$@"

#SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" &> /dev/null && pwd)
ROOTDIR="/opt/ncubed"

SCRIPT_DIR=$( dirname -- "$0"; )

test_upgradeable=$(python3 $SCRIPT_DIR/ncubed/bin/n3.py test upgradeable $SCRIPT_DIR)

if [ $test_upgradeable = 'False' ] && [ -z "$skip_version_check" ]; then
  printf "\n\nUnable to upgrade to this version directly\n\n"
  exit 0
fi

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
  printf "\n$NETPLAN_CONFIG_FILE exists, using that.\n\n"
else
  printf "\nusing default example netplan file\n\n"
  cp  $ROOTDIR/config/local/netplan-config.yaml.example $NETPLAN_CONFIG_FILE
fi

ln -s $ROOTDIR/config/local/netplan-config.yaml /etc/netplan/config.yaml
netplan apply


# update etc files
cp -p -r $ROOTDIR/etc/* /etc/

# make sure bin dir is executiable
chmod +x $ROOTDIR/bin/*

# add cli to globally available tools
ln -b $ROOTDIR/bin/n3.py /usr/local/bin/n3

# migrate config files etc. from previous version to the current
python3 $SCRIPT_DIR/ncubed/migrate.py

# install services
chmod +x $ROOTDIR/network.service/install
$ROOTDIR/network.service/install

chmod +x $ROOTDIR/callhome.service/install
$ROOTDIR/callhome.service/install

chmod +x $ROOTDIR/watchdog.service/install
$ROOTDIR/watchdog.service/install

chmod +x $ROOTDIR/monitoring.service/install
$ROOTDIR/monitoring.service/install

chmod +x /etc/libvirt/hooks/qemu
systemctl restart libvirtd
touch /var/log/ncubed.libvirt.log

# FIX: sudo unable to resolve hostname
sed -i '/::1/d' /etc/hosts
echo ::1 $(hostname) >> /etc/hosts

systemctl stop network-manager.service
systemctl mask network-manager.service

# disable wait for network on boot
systemctl disable systemd-networkd-wait-online.service
systemctl mask systemd-networkd-wait-online.service

# set boot device
boot_os=$(efibootmgr | grep ubuntu | grep -Eo '[0-9]{1,4}')
efibootmgr -o $boot_os

######################################
# Tweak cloudinit
######################################
# make hostname changes persistent
echo "preserve_hostname: true" > /etc/cloud/cloud.cfg.d/99_hostname.cfg

# disable cloudinit networking
echo "network: {config: disabled}" > /etc/cloud/cloud.cfg.d/99-custom-networking.cfg

