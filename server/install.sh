#!/bin/bash
##################################################################################
# elevate
##################################################################################
[ "$UID" -eq 0 ] || exec sudo bash "$0" "$@"

SCRIPTPATH=$(dirname $(realpath $0))

cp -p -r $SCRIPTPATH/* /opt/ncubed/

basedir=/opt/ncubed
configdir=/etc/ncubed/config
configfile=orchestration.yaml

mkdir -p $configdir
if [ ! -f $configdir/$configfile ]; then
  cp $basedir/config/$configfile.example $configdir/$configfile
  nano $configdir/$configfile
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
