#!/bin/bash
export ANSIBLE_INVENTORY=/opt/ncubed/ansible/inventories

[ -z "$TMUX"  ] && { tmux attach || exec tmux new-session && exit; }

printf "
To show dynamic motd run: cat /var/run/motd.dynamic

ansible inventory: /opt/ncubed/ansible/inventories
the inventory and ssh known hosts are automaticly updated by the attestation sync service
"


state=$(systemctl is-active ncubed-attestation-sync)
case $state in
active)
printf "\e[32m
ncubed-attestation-sync: $(systemctl is-active ncubed-attestation-sync)
\e[0m
"
;;
*)
printf "\e[31m
ncubed-attestation-sync: $(systemctl is-active ncubed-attestation-sync)
\e[0m
"
;;
esac
#systemctl status ncubed-attestation-sync.service
if [[ -z "${ANSIBLE_USER}" ]]; then
  printf "\e[31m
        ANSIBLE_USER not set
        \e[0m"
fi

if [[ -z "${ANSIBLE_PASSWORD}" ]]; then
  printf "\e[31m
        ANSIBLE_PASSWORD not set
        \e[0m"
fi

cd ~/vep-orch-tools

printf "\e[1m
                   _               _
                  | |             | |
 ____   ____ _   _| |__  _____  __| |
|  _ \ / ___) | | |  _ \| ___ |/ _  |
| | | ( (___| |_| | |_) ) ____( (_| |
|_| |_|\____)____/|____/|_____)\____|
\e[0m
"
