# vep-orch-tools
tools deployed on the orchestration servers

credentials need to e loaded into the environment variables
export ANSIBLE_USER=<username>
export ANSIBLE_PASSWORD=<password>

# Vep updates
New updates are published in /opt/ncubed/updates/$date-$time/

# Services
Within the update 3 services are defined:
- ncubed.oneshot
- ncubed.network
- ncubed.callhome

These services are installed in bulk with the $update/install.sh script
individual services can be installed using the $update/ncubed/$service/install.sh script

## Oneshot
Not used anymore?!?

## Network
Network services is used to create the internal network of the VEP.
It sets up the netnamespaces and configures the interfaces to be seperated from eachother

### High-level overview
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
 
 
## Callhome
The callhome service uses the assettag to sign up with the DeviceAttestationServer (DAS).
Sets up the wireguard VPN to the orchestration server received from the DAS.
This service changes the LED color to indicate the different phases of the connection.
Purple color means the connection to the Orchestration service is set up and the device can be accessed via the IPv6 address assigned by the DAS.
 
# Ansible playbooks
 To make updating devices easier and automatable Ansible-Playbooks have been created. The default inventory used is located in: /opt/ncubed/ansible/inventories

 ## nc-update_known_hosts.yaml
 This playbook is used to connect to devices and save the SSH fingerprint of the device.
 ## nc-update_opt_ncubed.yaml
 This playbook is used to update the VEP software on known devices. It copies the version specified in the playbook to the device and runes the <update>/install.sh script
