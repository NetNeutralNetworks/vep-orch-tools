#!/bin/python3
import os
import subprocess

if os.getuid() != 0:
    #subprocess.run(f'sudo python3 {__file__}', shell=True) # this will try to run script directly with sudo
    print("Installer needs elevated privileges.")
    exit()

print('Installing packages...')
subprocess.run(f'''
               apt update
               apt -y install < packages.txt
               ''',
               stdout=subprocess.PIPE, shell=True).stdout.decode()

# subprocess.run(f'''
#                pip3 install -r requirements.txt               
#                ''',
#                stdout=subprocess.PIPE, shell=True).stdout.decode()