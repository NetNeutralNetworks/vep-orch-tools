#!/usr/bin/env python3

import yaml, logging, sys, time, json, glob, os
from logging.handlers import RotatingFileHandler
import requests, netmiko, paramiko
from netmiko import ConnectHandler
import telnetlib

from paramiko import SSHClient
from scp import SCPClient

node_json = {
    "compute_id": "local",
    "custom_adapters": [
      {
        "adapter_number": 0,
        "adapter_type": "e1000"
      },
      {
        "adapter_number": 1,
        "adapter_type": "e1000"
      },
      {
        "adapter_number": 2,
        "adapter_type": "e1000"
      },
      {
        "adapter_number": 3,
        "adapter_type": "e1000"
      },
      {
        "adapter_number": 4,
        "adapter_type": "e1000"
      },
      {
        "adapter_number": 5,
        "adapter_type": "e1000"
      },
      {
        "adapter_number": 6,
        "adapter_type": "e1000"
      },
      {
        "adapter_number": 7,
        "adapter_type": "e1000"
      }
    ],
    "first_port_name": "",
    "label": {
      "rotation": 0,
      "style": "font-family: TypeWriter;font-size: 10.0;font-weight: bold;fill: #000000;fill-opacity: 1.0;",
      "text": sys.argv[1],
      "x": None,
      "y": -25
    },
    "locked": False,
    "name": sys.argv[1],
    "node_type": "qemu",
    "port_name_format": "Ethernet{0}",
    "properties": {
      "adapter_type": "virtio-net-pci",
      "adapters": 8,
      "bios_image": "",
      "bios_image_md5sum": None,
      "boot_priority": "c",
      "cdrom_image": "ubuntu-cloud-init-data.iso",
      "cdrom_image_md5sum": "328469100156ae8dbf262daa319c27ff",
      "cpu_throttling": 0,
      "cpus": 2,
      "create_config_disk": False,
      "hda_disk_image": "ubuntu-20.04-server-cloudimg-amd64.img",
      "hda_disk_image_md5sum": "044bc979b2238192ee3edb44e2bb6405",
      "hda_disk_interface": "virtio",
      "hdb_disk_image": "",
      "hdb_disk_image_md5sum": None,
      "hdb_disk_interface": "none",
      "hdc_disk_image": "",
      "hdc_disk_image_md5sum": None,
      "hdc_disk_interface": "none",
      "hdd_disk_image": "",
      "hdd_disk_image_md5sum": None,
      "hdd_disk_interface": "none",
      "initrd": "",
      "initrd_md5sum": None,
      "kernel_command_line": "",
      "kernel_image": "",
      "kernel_image_md5sum": None,
      "legacy_networking": False,
      "linked_clone": True,
      "on_close": "power_off",
      "options": "",
      "platform": "x86_64",
      "process_priority": "normal",
      "qemu_path": "/usr/bin/qemu-system-x86_64",
      "ram": 2048,
      "replicate_network_connection_state": True,
      "usage": "Username: ubuntu\nPassword: ubuntu"
    },
    "symbol": ":/symbols/classic/qemu_guest.svg",
    "width": 65,
    "x": 1,
    "y": 1,
    "z": 1
 }


def get_ip_from_telnet(host, port, username, password):
  tn = telnetlib.Telnet(host, port=port)
  tn.write(b"\n")
  tn.write(b"\n")
  tn.read_until(b"login: ")
  tn.write(bytes(f'{username}\n', 'utf-8'))
  tn.read_until(b"Password: ")
  tn.write(bytes(f'{password}\n', 'utf-8'))
  tn.read_until(b"$ ")
  tn.write(b"ip -4 -j addr\n")
  ipconfig = tn.read_until(b"$")
  tn.write(b"\n")

  time.sleep(1)
  tn.write(b"\nexit\n")
  tn.write(b"\n")
  tn.close()

  interfaces = json.loads(ipconfig.decode("utf-8").split('\n')[1])

  for interface in interfaces:
      for addr_info in interface.get('addr_info', []):
          ip = addr_info.get('local')
          if ip != '127.0.0.1':
              return ip

def get_switch():
    lab_nodes = requests.get(nodes_url).json()
    for node in lab_nodes:
        if node.get('name') == config.get('switch'):
            return node

def create_link(node1_id, node1_port, node2_id, node2_port, node1_adapter=0, node2_adapter=0):
    link_json = {
        "nodes": [
            {
                "adapter_number": node1_adapter,
                "node_id": node1_id, #get_switch().get('node_id', ''),
                "port_number": node1_port
            },
            {
                "adapter_number": node2_adapter,
                "node_id": node2_id, #create_node.json().get('node_id', ''),
                "port_number": node2_port
            }
        ]
    }
    return requests.post(links_url, json = link_json)

#############################################
######### ======== START ======== ###########
#############################################

# Create logger

logger = logging.getLogger("ncubed-vepdeploy")
logger.setLevel(level=logging.DEBUG)
formatter = logging.Formatter(fmt='%(asctime)s(File:%(name)s,Line:%(lineno)d, %(funcName)s) - %(levelname)s - %(message)s', 
                                datefmt="%m/%d/%Y %H:%M:%S %p")
rothandler = RotatingFileHandler('/var/log/ncubed.vep-deploy.log', maxBytes=100000, backupCount=5)
rothandler.setFormatter(formatter)
logger.addHandler(rothandler)
logger.addHandler(logging.StreamHandler(sys.stdout))

# Read config file

with open('config.yaml') as f:
    config = yaml.load(f, Loader=yaml.FullLoader)


nodes_url = f"http://{config['ip']}/v2/projects/{config['project']}/nodes"

# Create VEP VM
create_node = requests.post(nodes_url, json = node_json)
logger.info(f"created node")


# Linking VM port 0 to first available port on the switch as specified in config file
links_url = f"http://{config['ip']}/v2/projects/{config['project']}/links"
for i in range(0,48):
    link = create_link(
      node1_id=get_switch().get('node_id', ''), 
      node1_port=i, 
      node2_id=create_node.json().get('node_id', ''), 
      node2_port=0)
    if link.status_code==201:
      # Link is successfull
      logger.info(f"conected {create_node.json().get('name', '')} <--> {config.get('switch')}")
      break


# Starting VM
start_node_url = f"http://{config['ip']}/v2/projects/{config['project']}/nodes/{create_node.json().get('node_id', '')}/start"
started = requests.post(start_node_url)
logger.info(f"Starting host")

# Getting IP info from serial
time.sleep(40)
logger.info(f"Connecting to terminal over telnet poort: {create_node.json().get('console', '')}")
connect_ip = get_ip_from_telnet(host = config['ip'], port=create_node.json().get('console', ''), username='ubuntu', password='ubuntu')

# Uploading and installing update
logger.info(f"Connecting over ssh to: {connect_ip}")
try:
  ssh = SSHClient()
  ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
  ssh.connect(hostname=connect_ip, username="ubuntu", password="ubuntu")
  scp = SCPClient(ssh.get_transport())

  updates = os.listdir('/etc/ncubed/vep-orch-tools/opt/ncubed/updates/')
  updates.sort(reverse=True)
  logger.info(f'pushing update: {updates[0]}')

  scp.put('/etc/ncubed/vep-orch-tools/opt/ncubed/updates/'+updates[0], '~/', recursive=True)
  ssh_stdin, ssh_stdout, ssh_stderr = ssh.exec_command(f'~/{updates[0]}/install.sh')

except Exception as e:
  logger.error(f"Encountered error during SSH connection: {e}")

