#!/bin/bash
PATH=$PATH:/opt/ncubed/bin

stty cols 200 rows 50

alias _ip='ip -br -c addr'
alias _ip4='ip -4 -br -c addr'
alias _ip6='ip -6 -br -c addr'
alias _eth='ip -br -c link'
alias _bridge='bridge -color link'
alias _vlan='bridge -color vlan'
alias _fdb='bridge -color fdb'
alias _dhcpleases='cat /var/lib/misc/dnsmasq.leases'

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

printf "\n"
print_service_state "ncubed-callhome"
print_service_state "ncubed-network"

printf "\e[1m
                   _               _
                  | |             | |
 ____   ____ _   _| |__  _____  __| |
|  _ \ / ___) | | |  _ \| ___ |/ _  |
| | | ( (___| |_| | |_) ) ____( (_| |
|_| |_|\____)____/|____/|_____)\____|
\e[0m
"

printf "\e[1m"
n3 show version
printf "\e[0m\n"