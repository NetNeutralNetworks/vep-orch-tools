#!/bin/python3
import os
import subprocess

installer_rootpath=os.path.dirname(__file__)

if os.getuid() != 0:
    #subprocess.run(f'sudo python3 {__file__}', shell=True) # this will try to run script directly with sudo
    print("Installer needs elevated privileges.")
    exit()

print('Installing packages...')
subprocess.run(f'''
               apt update
               xargs apt -y install < {installer_rootpath}/packages.txt
               ''',
               shell=True)

# subprocess.run(f'''
#                pip3 install -r requirements.txt               
#                ''',
#                stdout=subprocess.PIPE, shell=True).stdout.decode()

print('Installing orchestration services...')
subprocess.run(f'{installer_rootpath}/server/install.sh')