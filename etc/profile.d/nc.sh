#!/bin/bash
export ANSIBLE_INVENTORY=/opt/ncubed/ansible/inventories

# this will create a tmux session and will reattatch if it allready exists
[ -z "$TMUX"  ] && { tmux attach || exec tmux new-session && exit; }

print_service_state () {
  state=$(systemctl is-active $1)
  case $state in
    active)
      color="\e[32m"
    ;;
    *)
      color="\e[31m"
    ;;
  esac
  printf "\e[1m$1: $color\t$state\e[0m\n"
}

printf "
To show dynamic motd run: cat /var/run/motd.dynamic

ansible inventory: /opt/ncubed/ansible/inventories
the inventory and ssh known hosts are automaticly updated by the attestation sync service
"

printf "\n"
print_service_state "ncubed-attestation-sync"

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
