#!/bin/bash
##################################################################################
# elevate
##################################################################################
[ "$UID" -eq 0 ] || exec sudo bash "$0" "$@"


SCRIPTPATH=$(dirname $(realpath $0))

cp -p -r $SCRIPTPATH/* /opt

systemctl daemon-reload
systemctl restart ncubed-attestation-sync.service
watch -n1 systemctl status ncubed-attestation-sync.service