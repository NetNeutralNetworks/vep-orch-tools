#!/bin/python3
import subprocess
from typing import Any
import yaml, json
import cmd
import sys
import glob
from os.path import exists

RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
COLOR_RESET = "\033[0m\n"

class N3cli(cmd.Cmd):
    def default(self, line: str) -> None:
        cmd = line.split(' ')
        possible_completions = [ t for t in self.completenames('') if t.startswith(cmd[0])]
        if len(possible_completions) == 1:
            self.onecmd(possible_completions[0] + " " + ' '.join(cmd[1:]))
        else:
            return super().default(line)
        
    def completenames(self, text, *ignored):
        dotext = 'do_'+text
        possible_options = [a[3:] for a in self.get_names() if a.startswith(dotext)]
        if len(possible_options) == 1:
            # Only one option, so we add a space to auto complete next command
            return [possible_options[0] + " "]
        return possible_options
    
    def do_help(self, arg: str):
        '''Shows this help page'''
        data = []
        for function in self.get_names():
            if function.startswith('do_'):
                doc=getattr(self, function).__doc__
                data.append([''.join(function[3:]), str(doc) if doc else ""])
        widths = [max(map(len, col)) for col in zip(*data)]
        for row in data:
            help_text = row[1].replace('\n', '\n'+' '*widths[0])
            print(f"{row[0].ljust(widths[0])}   {help_text}")
        print()
        
    def do_exit(self, args): 
        '''Exists the n3 shell'''
        return True
    


class test(N3cli):
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

class debug(N3cli):
    prompt = "ncubed debug >>> "
    def do_run(self,args):
        '''Runs basic diagnostic of the network connections in all the namespaces'''
        subprocess.run(f'''
        sudo python3 /opt/ncubed/watchdog.service/debug_connection.py
        ''', shell=True)

class show(N3cli):
    prompt = "ncubed show >>> "
    def do_system(self, args):
        '''Shows platform, serialnumber and version of this device'''
        self.do_platform(args)
        self.do_serial(args)
        self.do_version(args)

    def do_EOF(self, args):
        '''Use Ctrl+D to go back to n3 base shell'''
        print('')
        cli().cmdloop()
        
    def do_cluster(self, args):
        '''Shows the cluster configuration'''
        system_config_file = '/opt/ncubed/config/local/system.yaml'
        if exists(system_config_file):
            with open(system_config_file,'r') as f:
                data = yaml.safe_load(f)
                cluster = data.get('cluster',{})
                print(f"Cluster name: {cluster.get('name','')}\nNode ID: {cluster.get('member','misconfigured')}\nMembers: {cluster.get('size','misconfigured')}")

    def do_serial(self, args):
        '''Shows the serialnumber of this device'''
        asset_tag=subprocess.run(f"cat /sys/devices/virtual/dmi/id/board_asset_tag", stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True).stdout.decode().strip()
        print (f"Asset tag: {asset_tag}")
        
    def do_platform(self, args):
        '''Shows the platform of this device'''
        product_name=subprocess.run(f"cat /sys/devices/virtual/dmi/id/product_name", stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True).stdout.decode().strip()
        print (f"Platform: {product_name}")

    def do_version(self, args):
        '''Shows the current version of ncubed software'''
        with open('/opt/ncubed/meta.yaml','r') as f:
            data = yaml.safe_load(f)

        print (f"Version: {data.get('version')}")

    def do_netns(self, args):
        '''Shows all the ip's in the different net namespaces'''
        NETNAMESPACES = subprocess.run(f"ls /run/netns/", stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True).stdout.decode().split()
        for NETNS in NETNAMESPACES:
            print(f"\n{50*'#'} {NETNS} {50*'#'}")
            subprocess.run(f'''
                sudo ip -n {NETNS} -br -c addr
                ''', shell=True)
    
    
class orchestration(N3cli):
    prompt = "ncubed orchestration >>> "

    def do_EOF(self, args):
        '''Use Ctrl+D to go back to n3 base shell'''
        print('')
        cli().cmdloop()
  
    def do_info(self, args):
        '''Shows the current orchestration info as it was last received from the Attestation server'''
        with open('/opt/ncubed/config/local/orch_info.yaml','r') as f:
            data = yaml.safe_load(f)

        print (f"{json.dumps(data, indent=2)}")

    def do_status(self, args):
        '''Shows the current status of connections to orchestration servers
        use -w flag to show a live version'''
        if '-w' in args:
            try:
                subprocess.run(f'''
                watch -n0.5 -c n3 orchestration status
                ''', shell=True)
            except KeyboardInterrupt:
                return False
        else:
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
        
    def do_refresh(self, args):
        '''Does a new callhome to the attestation server and replaces the current orch_info file if the response is correct'''
        subprocess.run(f'''
                sudo python3 /opt/ncubed/callhome.service/force_attestation.py
                ''', shell=True)
        
    
    
class cli(N3cli):
    """Accepts commands via the normal interactive prompt or on the command line."""
    prompt = "ncubed >>> "
    def __init__(self):
        cmd.Cmd.__init__(self)

    def completenames(self, text, *ignored):
        dotext = 'do_'+text
        possible_options = [a[3:] for a in self.get_names() if a.startswith(dotext)]
        if len(possible_options) == 1:
            # Only one option, so we add a space to auto complete next command
            return [possible_options[0] + " "]
        return possible_options

    def do_show(self, args):
        '''Enter show CLI to display system values'''
        if len(args) > 1:
            show().onecmd(args)
        else:
            show().cmdloop()
    
    def complete_show(self, text, line, start_index, end_index):
        return [ t for t in show().completenames('') if text in t]

    def do_orchestration(self, args):
        '''Enter orchestration CLI to display/configure orchestration servers'''
        if len(args) > 1:
            orchestration().onecmd(args)
        else:
            orchestration().cmdloop()

    def complete_orchestration(self, text, line, start_index, end_index):
        results = [ t for t in orchestration().completenames('') if text in t]
        if len(results) == 1:
            return [results[0] + " "]
        return [ t for t in orchestration().completenames('') if text in t]
    
    def do_debug(self, args):
        '''Enter debug CLI to debug connections'''
        if len(args) > 1:
            debug().onecmd(args)
        else:
            debug().cmdloop()

    def complete_debug(self, text, line, start_index, end_index):
        results = [ t for t in debug().completenames('') if text in t]
        if len(results) == 1:
            return [results[0] + " "]
        return [ t for t in debug().completenames('') if text in t]
    
    def do_test(self, args):
        '''Enter CLI to do tests'''
        if len(args) > 1:
            test().onecmd(args)
        else:
            test().cmdloop()
        
    def complete_test(self, text, line, start_index, end_index):
        return [ t for t in test().completenames('') if text in t]

    
    def do_connect(self, device):
        '''Connects to specified (USB) device
        Tab completes usb devices'''
        input("""
                Connecting to /dev/ttyUSB0 with baud rate 115200
                to exit screen use: CTRL-A k
                Press any key to continue
        """)
        print(f"connecting to: {device}")
        # subprocess.run(f'''
        #                sudo python3 /opt/ncubed/bin/reset_usb.py CP210x
        #                sudo screen {device} 115200
        #                ''', shell=True)
        
    def complete_connect(self, text, line, start_index, end_index):
        devices = subprocess.run(f"ls /dev/", stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True).stdout.decode().split()
        usb_devices = [f"/dev/{x}" for x in devices if 'USB' in x]
        import readline
        readline.set_completer_delims(' \t\n')
        return [ t for t in usb_devices if text in t]

        


if __name__ == '__main__':
    if len(sys.argv) > 1:
        cli().onecmd(' '.join(sys.argv[1:]))
    else:
        cli().cmdloop()


    