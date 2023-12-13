#!/bin/bash
##################################################################################
# elevate
##################################################################################
[ "$UID" -eq 0 ] || exec sudo bash "$0" "$@"

SCRIPTPATH=$(dirname $(realpath $0))


basedir=/opt/ncubed
mkdir -p $basedir
cp -p -r $SCRIPTPATH/* $basedir/


configdir=/etc/ncubed/config
orchconfigfile=orchestration.yaml
networkconfigfile=network.yaml


mkdir -p $configdir
if [ ! -f $configdir/$orchconfigfile ]; then
  cp $basedir/config/$orchconfigfile.example $configdir/$orchconfigfile
  nano $configdir/$orchconfigfile
fi

if [ ! -f $configdir/$networkconfigfile ]; then
  cp $basedir/config/$networkconfigfile.example $configdir/$networkconfigfile
  nano $configdir/$networkconfigfile
fi

# Install services
for f in services/*; do
    if [ -d "$f" ]; then
        # install services
        chmod +x $f/install
        $f/install
    fi
done


systemctl daemon-reload
systemctl restart ncubed-network.service
systemctl restart ncubed-attestation-sync.service
watch -n1 systemctl status ncubed-attestation-sync.service
