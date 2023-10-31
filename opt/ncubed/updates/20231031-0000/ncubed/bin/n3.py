#!/bin/python3
import subprocess
import yaml, json
import cmd
import sys
import glob
from os.path import exists

class test(cmd.Cmd):
    prompt = "ncubed test >>> "
    def complete_upgradeable(self, text, line, start_index, end_index):
        paths = glob.glob('/opt/ncubed/updates/*')
        l = line.split()
        if len(l) == 1:
            return [ t for t in paths if text in t]
        else:
            options = [ t.replace('/'.join(l[1].split('/')[:-1])+'/','') for t in paths if l[1] in t]
            return [o for o in options if o != l[1].split('/')[-1]]
            
    def do_upgradeable(self,sourcefolder):
        try:
            with open('/opt/ncubed/meta.yaml','r') as f:
                old = yaml.safe_load(f)

            with open(f'{sourcefolder}/ncubed/meta.yaml','r') as f:
                new = yaml.safe_load(f)

            if int(new.get('lowest_previous_version').replace('-','')) <= int(old.get('version').replace('-','')):
                print('True')
            else:
                print('False')
        except:
            print('False')
    
    def do_exit(self, args):
        return True

class show(cmd.Cmd):
    prompt = "ncubed show >>> "
    def do_system(self, args):
        self.do_platform(args)
        self.do_serial(args)
        self.do_version(args)
        
    def do_cluster(self, args):
        system_config_file = '/opt/ncubed/config/local/system.yaml'
        if exists(system_config_file):
            with open(system_config_file,'r') as f:
                data = yaml.safe_load(f)
                cluster = data.get('cluster',{})
                print(f"Cluster name: {cluster.get('name','')}\nNode ID: {cluster.get('member','misconfigured')}\nMembers: {cluster.get('size','misconfigured')}")

    def do_serial(self, args):
        asset_tag=subprocess.run(f"cat /sys/devices/virtual/dmi/id/board_asset_tag", stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True).stdout.decode().strip()
        print (f"Asset tag: {asset_tag}")
        
    def do_platform(self, args):
        product_name=subprocess.run(f"cat /sys/devices/virtual/dmi/id/product_name", stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True).stdout.decode().strip()
        print (f"Platform: {product_name}")

    def do_version(self, args):
        
        with open('/opt/ncubed/meta.yaml','r') as f:
            data = yaml.safe_load(f)

        print (f"Version: {data.get('version')}")

    def do_netns(self, args):
        NETNAMESPACES = subprocess.run(f"ls /run/netns/", stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True).stdout.decode().split()
        for NETNS in NETNAMESPACES:
            print(f"\n{50*'#'} {NETNS} {50*'#'}")
            subprocess.run(f'''
                sudo ip -n {NETNS} -br -c addr
                ''', shell=True)
    
    def do_orchestration(self, args):
        
        with open('/opt/ncubed/config/local/orch_info.yaml','r') as f:
            data = yaml.safe_load(f)

        print (f"{data}")

    def do_connection(self, args):
        
        with open('/opt/ncubed/status.json','r') as f:
            data = json.load(f)
        conn_status = "Connection status:\n"
        if data['orch_status'] == 'FULL':
            conn_status += "\033[32m" + data['orch_status'] + "\033[0m\n"
        elif data['orch_status'] == 'PARTIAL':
            conn_status += "\033[33m" + data['orch_status'] + "\033[0m\n"
        else:
            conn_status += "\033[31m" + data['orch_status'] + "\033[0m\n"
        orchestration = "Orchestration servers:\n"
        for server, status in data['orchestration_servers'].items():
            if status == 1:
                orchestration += "\033[32m" + server + "\033[0m\n"
            else:
                orchestration += "\033[31m" + server + "\033[0m\n"

        ns = "Namespaces with networkaccess:\n"
        for namespace in data['active_namespaces']:
            ns += namespace + "\n"
        print (f"{conn_status}\n{orchestration}\n{ns}")
    
    def do_exit(self, args):
        return True

class cli(cmd.Cmd):
    """Accepts commands via the normal interactive prompt or on the command line."""
    prompt = "ncubed >>> "
    def __init__(self):
        cmd.Cmd.__init__(self)

    def do_show(self, args):
        if len(args) > 1:
            show().onecmd(args)
        else:
            show().cmdloop()

    def complete_show(self, text, line, start_index, end_index):
        return [ t for t in show().completenames('') if text in t]
    
    def do_test(self, args):
        if len(args) > 1:
            test().onecmd(args)
        else:
            test().cmdloop()
        
    def complete_test(self, text, line, start_index, end_index):
        return [ t for t in test().completenames('') if text in t]

    def do_exit(self, args):
        return True
    
    def do_connect_USB0(self, args):
        input("""
                Connecting to /dev/ttyUSB0 with baud rate 115200
                to exit screen use: CTRL-A k
                Press any key to continue
        """)
        subprocess.run(f'''
                       sudo python3 /opt/ncubed/bin/reset_usb.py CP210x
                       sudo screen /dev/ttyUSB0 115200
                       ''', shell=True)


if __name__ == '__main__':
    if len(sys.argv) > 1:
        cli().onecmd(' '.join(sys.argv[1:]))
    else:
        cli().cmdloop()
