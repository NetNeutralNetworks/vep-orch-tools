# Client devices
## Vep updates
New updates are published in /opt/ncubed/updates/$date-$time/

## Services
Within the update 4 services are defined:
- ncubed.network
- ncubed.callhome
- ncubed.monitoring
- ncubed.watchdog

These services are installed in bulk with the $update/install.sh script
individual services can be installed using the $update/ncubed/$service/install.sh script

### Network
Network services is used to create the internal network of the VEP.
It sets up the netnamespaces and configures the interfaces to be seperated from eachother

### Callhome
The callhome service is responsible for connecting the device to the known orchestration servers.
In order to connect to the Orch servers this service will make a call to the attestation server which is defined in: `/opt/ncubed/config/orchestration.yaml`
Since 20231031-0000 it is possible to allow simultanious connections to different orch-servers.
It will try to setup these tunnels distributed over the available netns's, only using the ROOT namespace if there is no other namespace available.

### Monitoring
The monitoring service is used to keep an eye on the connection status of the device.
After each check it will update the status file (/opt/ncubed/status.json) which can be read using `n3 orch status`
In the future we might also include SNMP traps in this service

### Watchdog
The watchdog service is responsible for keeping the system in-line with the desired configuration.
It will try to troubleshoot and resolve network disconnects and auto-start vm's

## High-level overview
Script checks network.yaml to map physical interface to netspaces.
Creates bridges and veth interfaces to connect the namespaces together.
Creates VLAN bridges according to vlan_bridges.yaml.
 
 Each device has 3 net namespaces (ns_WAN0, ns_WAN1 and ns_WAN2). The bridges in these networks have ip addresses assigned to them in this order:
 1. Staticly defined in the /opt/ncubed/config/$netns.yaml file
 2. DHCP if available in the network
 3. Using a script scanning for gracious ARP's and graduatly increasing subnet size untill a device is found that can route to the internet (checked by pinging 8.8.8.8)
 
 The last phase of the service tries to call /opt/ncubed/custom_network.py to do some custom changes to the network if defined.

Config used: 
 - /opt/ncubed/config/$netns.yaml
 - /opt/ncubed/config/vlan_bridges.yaml
 - /opt/ncubed/config/network.yaml

## N3 shell
 The n3 shell was created to ease management and to allow logic proccessing within a single command that can also be used programmaticly.
 This progam is made globally available during the installation of an update and can be used interactivly using the `n3` command. Commands entered in the interactive mode have tab-completion
 It can also be used a single line command (ex. n3 show version).
 Planned functionality include: 
 - troubleshooting commands
 - Editing ip config
 - VEP updating

# Server
## Installation
To install the server follow the following steps:
1. execute the `install.py` file which installs the required apt packages
2. execute `server/install.sh` which copies the services to /opt/ncubed/ and links them to de systemd services
3. The required config will opened, edit this now or you will need to restart your services later. These configs are located in /etc/ncubed/config/

## Ansible playbooks
credentials need to be loaded into the environment variables
    export ANSIBLE_USER=<username>
    export ANSIBLE_PASSWORD=<password>
To make updating devices easier and automatable Ansible-Playbooks have been created. The default inventory used is located in: /opt/ncubed/ansible/inventories

### nc-update_known_hosts.yaml
 This playbook is used to connect to devices and save the SSH fingerprint of the device.
### nc-update_opt_ncubed.yaml
 This playbook is used to update the VEP software on known devices. It copies the version specified in the playbook to the device and runes the <update>/install.sh script
 

