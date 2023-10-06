#!/bin/bash
##################################################################################
# elevate
##################################################################################
[ "$UID" -eq 0 ] || exec sudo bash "$0" "$@"

SCRIPTPATH=$(dirname $(realpath $0))

cp -p -r $SCRIPTPATH/* /opt

basedir=/opt/ncubed
configdir=/etc/ncubed/config
configfile=orchestration.yaml

mkdir -p $configdir
if [ ! -f $configdir/$configfile ]; then
  cp $basedir/config/$configfile.example $configdir/$configfile
  nano $configdir/$configfile
fi

systemctl daemon-reload
systemctl restart ncubed-attestation-sync.service
watch -n1 systemctl status ncubed-attestation-sync.service
