# vep-orch-tools
tools deployed on the orchestration servers

credentials need to e loaded into the environment variables
export ANSIBLE_USER=<username>
export ANSIBLE_PASSWORD=<password>

# Vep updates
New updates are published in /opt/ncubed/updates/<date>-<time>/

# Services
Within the update 3 services are defined:
- ncubed.oneshot
- ncubed.network
- ncubed.callhome

These services are installed in bulk with the <update>/install.sh script
individual services can be installed using the <update>/ncubed/<service>/install.sh script

## Oneshot
Not used anymore?!?

## Network
Network services is used to create the internal network of the VEP.
It sets up the netnamespaces and configures the interfaces to be seperated from eachother

### High-level overview
Script checks network.yaml
 -> Todo fill in more

Config used: 
 - /opt/ncubed/config/<netns>.yaml
 - /opt/ncubed/config/vlan_bridges.yaml
 - /opt/ncubed/config/network.yaml
 
 
## Callhome
