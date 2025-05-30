#!/bin/python3
import os
from glob import glob
import yaml
import subprocess
import libvirt
import shutil
import define_vm

from argparse import ArgumentParser, ArgumentTypeError

ROOT="/opt/ncubed"
VM="ION"
IMAGEPATH=f"{ROOT}/images"

def file_name(file):
    if os.path.isfile(file):
        return file
    else:
        raise ArgumentTypeError(f"""readable_file:{file} is not a valid file
examples:
{glob(IMAGEPATH+'/*')}
""")

parser = ArgumentParser(epilog="""
Deploy ION
""")
parser.add_argument('-c',"--vcpus", required=True, type=int, help="specify number vcpu's, integers only")
parser.add_argument('-m',"--memory", required=True, type=int, help="specify memory in gigabytes, integers only")
parser.add_argument('-f',"--imagefile", required=True, type=file_name, help="specify absolute filename")

args = parser.parse_args()

CPU=args.vcpus
MEM=args.memory
IMAGE=args.imagefile


def get_config():
    with open(f"{ROOT}/config/local/network.yaml") as f:
        PORT_CONFIG = yaml.load(f, Loader=yaml.FullLoader)

    DEV_FAMILIY=subprocess.run(f"dmidecode -s system-family", stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True).stdout.decode().strip()
    return [C for C in PORT_CONFIG if DEV_FAMILIY == C.get('family')][0]

def display_config(CONFIG):
    print (f'''
    VM intf    usecase                  host intf
    -----------------------------------------------------------------------------------
    1           MGMT                    {CONFIG['portconfig']['MGMT'][0]}
    2           WAN0 natted             {CONFIG['portconfig']['WAN'][0]}
    3           WAN1 natted             {CONFIG['portconfig']['WAN'][1]}
    4           WAN2 natted             {CONFIG['portconfig']['WAN'][2]}
    5           WAN0 direct             {CONFIG['portconfig']['WAN'][0]}
    6           WAN1 direct             {CONFIG['portconfig']['WAN'][1]}
    7           WAN2 direct             {CONFIG['portconfig']['WAN'][2]}
    8           INTERCONNECT            bond a/p ({', '.join(CONFIG['portconfig']['BONDS'][0]['interfaces'])})
    9           LAN                     bond a/p ({', '.join(CONFIG['portconfig']['BONDS'][1]['interfaces'])})

    ''')

if __name__ == '__main__':
    kvm = libvirt.open()

    print (f"Deploying {VM}, please wait")
    try:
        CONFIG = get_config()
        display_config(CONFIG)
    except Exception as e:
        pass

    shutil.copyfile(IMAGE, f'/var/lib/libvirt/images/{VM}.qcow2')
    kvm.defineXML(define_vm.render_xml(VM, CPU, MEM))
    vm = kvm.lookupByName(VM)
    vm.setAutostart(1)

    print (f"{VM} deployed.\n")

    RESPONSE = input("Start VM now? [y/N]")
    if RESPONSE.lower() in ['yes','y']:
        vm.create()
        print (f"{VM} started, connect to console using 'virsh console {VM}'")
    else:
        print (f"{VM} will be started on nex boot.")
