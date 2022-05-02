#!/bin/bash
export ANSIBLE_INVENTORY=/opt/ncubed/ansible/inventories

[ -z "$TMUX"  ] && { tmux attach || exec tmux new-session && exit;}

printf "To show dynamic motd run: cat /var/run/motd.dynamic"

printf "\n"

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

printf "\e[1m
                   _               _
                  | |             | |
 ____   ____ _   _| |__  _____  __| |
|  _ \ / ___) | | |  _ \| ___ |/ _  |
| | | ( (___| |_| | |_) ) ____( (_| |
|_| |_|\____)____/|____/|_____)\____|
\e[0m
"

