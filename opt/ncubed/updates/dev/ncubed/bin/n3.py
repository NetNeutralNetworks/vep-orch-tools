#!/bin/python3
import subprocess
import yaml
import cmd
import sys

class show(cmd.Cmd):
    def do_system(self, args):
        self.do_platform(args)
        self.do_serial(args)
        self.do_version(args)

    def do_serial(self, args):

        with open('/opt/ncubed/system.yaml','r') as f:
            data = yaml.safe_load(f)

        print (f"Serial: {data.get('serial')}")

    def do_platform(self, args):

        with open('/opt/ncubed/system.yaml','r') as f:
            data = yaml.safe_load(f)

        print (f"Platform: {data.get('platform')}")

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

    def complete_show(self, text, line, start_index, end_index):
        return [ t for t in show().completenames('') if text in t]

    def do_exit(self, args):
        return True

if __name__ == '__main__':
    if len(sys.argv) > 1:
        cli().onecmd(' '.join(sys.argv[1:]))
    else:
        cli().cmdloop()
