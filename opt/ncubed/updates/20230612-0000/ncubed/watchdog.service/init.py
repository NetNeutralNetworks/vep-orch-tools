#!/bin/python3
import libvirt, subprocess
import logging
import sys, os, json, yaml, datetime, traceback
from logging.handlers import RotatingFileHandler
from time import sleep

logger = logging.getLogger("ncubed watchdog daemon")
logger.setLevel(level=logging.DEBUG)
formatter = logging.Formatter(fmt='%(asctime)s(File:%(name)s, Line:%(lineno)d, %(funcName)s) - %(levelname)s - %(process)s: %(message)s',
                                datefmt="%m/%d/%Y %H:%M:%S %p")
rothandler = RotatingFileHandler('/var/log/ncubed.watchdogd.log', maxBytes=100000, backupCount=5)
rothandler.setFormatter(formatter)
logger.addHandler(rothandler)
logger.addHandler(logging.StreamHandler(sys.stdout))

GW_TEST_IP="8.8.8.8"
LOCAL_CONFIG_FOLDER = "/opt/ncubed/config/local"
GLOBAL_CONFIG_FOLDER = "/opt/ncubed/config/global"
ORCHESTRATION_V4_PREFIX = "100.71"
ORCHESTRATION_V6_PREFIX = "fd71::"

def check_vm_states(conn):
    for dom in conn.listAllDomains():
        if all([dom.state()[0] is not libvirt.VIR_DOMAIN_RUNNING, dom.autostart() == 1 ]):
            dom.create()
            logger.debug(f'VM {dom.name()} started')

def get_existing_netnamespaces():
    existing_netnamespaces_json = subprocess.run(f"ip -j netns", stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True).stdout.decode()
    if existing_netnamespaces_json:
        existing_netnamespaces=json.loads(existing_netnamespaces_json)
        return existing_netnamespaces
    else:
        return {}

def get_port_configs():
    try:
        with open(f'{LOCAL_CONFIG_FOLDER}/network.yaml', 'r') as f:
            PORT_CONFIGS = yaml.load(f, Loader=yaml.FullLoader)
        return PORT_CONFIGS
    except Exception as e:
        logger.error(f"Unable to read: {LOCAL_CONFIG_FOLDER}/network.yaml")
        sys.exit(1)

def any_wan_port_connected():
    PORT_CONFIGS = get_port_configs()

    DEV_FAMILIY = subprocess.run(f"dmidecode -s system-family", stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True).stdout.decode().strip()
    DEV_CONFIG = [PORT_CONFIG for PORT_CONFIG in PORT_CONFIGS if PORT_CONFIG.get('family') == DEV_FAMILIY]
    if DEV_CONFIG:
        for ns, port in DEV_CONFIG[0]['portconfig']['WAN'].items():
            port_status = subprocess.run(f"ip netns exec ns_WAN{ns} ip link show {port}", stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True).stdout.decode()
            if 'state UP' in port_status:
                return True
    return False

def check_connection():
    if subprocess.run(f"ping {ORCHESTRATION_V6_PREFIX} -c 3 | grep -q 'bytes from'", stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True).returncode:
        return 0
    else:
        return 1

def debug_connection():
    netns_info = subprocess.run(f"n3 show netns", stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True).stdout.decode()
    route_info = subprocess.run(f"ip route", stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True).stdout.decode()
    dns_masq = subprocess.run(f"cat /var/lib/misc/dnsmasq.leases", stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True).stdout.decode()
    dhcp_leases = subprocess.run(f"cat /var/lib/dhcp/dhclient.leases", stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True).stdout.decode()
    netns_reachability = []
    for NETNS in get_existing_netnamespaces():
        NETNS = NETNS.get('name')
        output = subprocess.run(f"ip netns exec {NETNS} ping -c 1 -W 1 {GW_TEST_IP}",stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True).stdout.decode()
        if "received, 0% packet loss" in output:
            netns_reachability.append(f"{GW_TEST_IP} is reachable from {NETNS}")
        else:
            netns_reachability.append(f"{GW_TEST_IP} is NOT reachable from {NETNS}")
        netns_reachability.append(f"""
ROUTE INFO: {NETNS} 
\/ \/ \/ 
{subprocess.run(f"ip netns exec {NETNS} ip route", stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True).stdout.decode()}
""")
        netns_reachability.append(f"""
DNS INFO: {NETNS}
\/ \/ \/ 
{subprocess.run(f"ip netns exec {NETNS} nslookup google.com", stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True).stdout.decode()}
""")

    with open('/var/log/connection_debug.log', 'w') as connection_debug_file:
        new_line = "\n"
        connection_debug_file.write(f"""
==============
n3 show netns:
{netns_info}
==============
route info:
{route_info}
==============
dnsmasq leases:
{dns_masq}
==============
own dhcp leases:
{dhcp_leases}
==============
netns info:
{new_line.join(f"{item}" for item in netns_reachability)}
==============
        """)
    logger.error("Restarting ncubed-network.service")
    subprocess.run(f"systemctl restart ncubed-network.service",stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True)

if __name__ == '__main__':
    connection_attempt = 0
    file_name = '/var/log/panic_reboot.time'
    while True:
        with libvirt.open() as conn:
            try:
                check_vm_states(conn)
            except Exception as e:
                logger.error(e)
        try:
            if not check_connection():
                connection_attempt += 1
                if connection_attempt > 5:
                        logger.warning("5th attempt to connect failed, starting diagnosing")
                        connection_attempt = 0
                        debug_connection()
                        sleep(10)
                        if any_wan_port_connected() and not check_connection():
                            logger.warning("Restarting ncubed-network.service did not resolve the issue")

                            try:
                                t = os.path.getmtime(file_name)
                                last_rebooted = datetime.datetime.fromtimestamp(t, tz=datetime.timezone.utc)
                            except OSError:
                                last_rebooted = datetime.datetime.fromtimestamp(0, tz=datetime.timezone.utc)

                            now = datetime.datetime.now(tz=datetime.timezone.utc)
                            if (now - last_rebooted).days > 0:
                                logger.warning("Resorting to last option, rebooting platform")
                                subprocess.run(f"touch {file_name}",stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True)
                                subprocess.run(f"init 6",stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True)
        except Exception as e:
                logger.error(e)
                logger.error(f"Fatal error occured during watchdog connection-test: {traceback.format_exc()}")
        sleep(10)
