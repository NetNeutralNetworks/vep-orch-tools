#!/bin/python3
import sys, json, subprocess, multiprocessing, yaml, time
import systemd.daemon
from pathlib import Path
from logging.handlers import RotatingFileHandler
import logging
#from systemd.journal import JournalHandler

logger = logging.getLogger("ncubed network daemon")
logger.setLevel(level=logging.DEBUG)
formatter = logging.Formatter(fmt='%(asctime)s(File:%(name)s, Line:%(lineno)d, %(funcName)s) - %(levelname)s - %(process)s: %(message)s',
                                datefmt="%m/%d/%Y %H:%M:%S %p")
rothandler = RotatingFileHandler('/var/log/ncubed.networkd.log', maxBytes=100000, backupCount=5)
rothandler.setFormatter(formatter)
logger.addHandler(rothandler)

#journald_handler = JournalHandler()
#journald_handler.setFormatter(formatter)
#logger.addHandler(journald_handler)

logger.addHandler(logging.StreamHandler(sys.stdout))


configfolder = Path("/etc/ncubed/config")
configfolder.mkdir(exist_ok=True)
configfile = configfolder.joinpath("network.yaml")

# get config
def get_config():
    with open(configfile, 'r') as f:
        return yaml.safe_load(f)

def get_netns():
    return json.loads(subprocess.run(f'''ip -j netns''',stdout=subprocess.PIPE, shell=True).stdout.decode())

def monitor_interface(NETNS, intf):
    with subprocess.Popen(f"ip -o -n {NETNS} monitor link", shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, bufsize=1, universal_newlines=True) as p:
        for line in p.stdout:
            config = get_config()
            if "UP,LOWER_UP" in line:
                logger.info(f"interface {intf.get('name')} in {NETNS} went up")

                
                logger.info(f"flushing ip info for {intf.get('name')} in {NETNS}")
                subprocess.run(f'''
                ip -n {NETNS} addr flush dev {intf.get("name")}
                ''', stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True)

                logger.info(f"flushing route table in {NETNS}")
                subprocess.run(f'''
                    ip -n {NETNS} route flush table main
                    ''', stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True)

                logger.info(f"adding ip address {intf.get('ip')} to {intf.get('name')}")
                subprocess.run(f'''
                ip -n {NETNS} addr add {intf.get("ip")} dev {intf.get("name")}
                ''', stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True)

                for route in intf.get("routes"):
                    logger.info(f"adding route to {route.get('to')} via {route.get('via')}")
                    subprocess.run(f'''
                    ip -n {NETNS} route add {route.get("to")} via {route.get("via")}
                    ''', stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True)

                
            else:
                logger.info(f"interface {intf.get('name')} in {NETNS} went down")


#netnamespaces:
#- name: 'UNTRUST'
#  interfaces:
#  - name: 'ens6'
#    ip: '192.168.15.201/20'
#    routes:
#      - to: '0.0.0.0/0'
#        via: '192.168.0.1'


if __name__ == '__main__':
    config = get_config()
    while True:
        try:
            
            for netns in config.get('netnamespaces'):
                NETNS=netns.get('name')
                if netns not in [netns.get('name')for netns in get_netns()]:
                    subprocess.run(f"ip netns add {NETNS}", shell=True)

                for intf in netns.get("interfaces"):
                    INTF=intf.get('name')
                    subprocess.run(f"ip link set {INTF} netns {NETNS}", shell=True)

                    process = multiprocessing.Process(name=f"Monitor {INTF} in {NETNS}", target=monitor_interface, args=(NETNS, intf))
                    process.start()

                    time.sleep(1)

                    subprocess.run(f"ip netns exec {NETNS} ip link set up dev {INTF}", shell=True)

            # notify systemd daemon is ready
            systemd.daemon.notify('READY=1')
            break
        except:
            # Keep trying untill no errors occur
            time.sleep(1)
            pass
        

