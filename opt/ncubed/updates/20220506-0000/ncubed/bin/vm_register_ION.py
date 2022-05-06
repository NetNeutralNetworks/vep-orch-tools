#!/bin/python3
import os
import logging
import libvirt
import tty
import termios
import atexit
import time
from argparse import ArgumentParser
from typing import Optional  # noqa F401


def reset_term() -> None:
    termios.tcsetattr(0, termios.TCSADRAIN, attrs)


def error_handler(unused, error) -> None:
    # The console stream errors on VM shutdown; we don't care
    if error[0] == libvirt.VIR_ERR_RPC and error[1] == libvirt.VIR_FROM_STREAMS:
        return
    logging.warn(error)


class Console(object):
    def __init__(self, uri: str, uuid: str) -> None:
        self.uri = uri
        self.uuid = uuid
        self.connection = libvirt.open(uri)
        self.domain = self.connection.lookupByUUIDString(uuid)
        self.state = self.domain.state(0)
        self.connection.domainEventRegister(lifecycle_callback, self)
        self.stream = None  # type: Optional[libvirt.virStream]
        self.run_console = True
        self.stdin_watch = -1
        self.text= ''
        logging.info("%s initial state %d, reason %d",
                     self.uuid, self.state[0], self.state[1])


def check_console(console: Console) -> bool:
    if (console.state[0] == libvirt.VIR_DOMAIN_RUNNING or console.state[0] == libvirt.VIR_DOMAIN_PAUSED):
        if console.stream is None:
            console.stream = console.connection.newStream(libvirt.VIR_STREAM_NONBLOCK)
            console.domain.openConsole(None, console.stream, 0)
            console.stream.eventAddCallback(libvirt.VIR_STREAM_EVENT_READABLE, stream_callback, console)
    else:
        if console.stream:
            console.stream.eventRemoveCallback()
            console.stream = None

    return console.run_console


def stdin_callback(watch: int, fd: int, events: int, console: Console) -> None:
    readbuf = os.read(fd, 1024)
    print(readbuf)
    if readbuf.startswith(b""):
        console.run_console = False
        return
    if console.stream:
        console.stream.send(readbuf)


def stream_callback(stream: libvirt.virStream, events: int, console: Console) -> None:
    try:
        assert console.stream
        received_data = console.stream.recv(1024)
        console.text += received_data.decode()
    except Exception:
        return
    os.write(0, received_data)


def lifecycle_callback(connection: libvirt.virConnect, domain: libvirt.virDomain, event: int, detail: int, console: Console) -> None:
    console.state = console.domain.state(0)
    logging.info("%s transitioned to state %d, reason %d",
                 console.uuid, console.state[0], console.state[1])


uri = 'qemu:///system'
connection = libvirt.open(uri)
vm = connection.lookupByName('ION')
uuid = vm.UUIDString()

print("Escape character is ^]")
logging.basicConfig(filename='msg.log', level=logging.DEBUG)
logging.info("URI: %s", uri)
logging.info("UUID: %s", uuid)

libvirt.virEventRegisterDefaultImpl()
libvirt.registerErrorHandler(error_handler, None)

atexit.register(reset_term)
attrs = termios.tcgetattr(0)
tty.setraw(0)

console = Console(uri, uuid)
console.stdin_watch = libvirt.virEventAddHandle(0, libvirt.VIR_EVENT_HANDLE_READABLE, stdin_callback, console)

console.stream = console.connection.newStream(libvirt.VIR_STREAM_NONBLOCK)
console.domain.openConsole(None, console.stream, 0)
console.stream.eventAddCallback(libvirt.VIR_STREAM_EVENT_READABLE, stream_callback, console)
# while check_console(console):
def send_command(command='',waitfor='(Q)uit'):
    command = f"{command}\r".encode()
    console.text = '\n'
    console.stream.send(command)
    while waitfor not in console.text:
        libvirt.virEventRunDefaultImpl()
    
    print(f"\n\n\n\n\nThis is the end result: {console.text}")
    time.sleep(0.1)

# main
parser = ArgumentParser(epilog="Example: %(prog)s 'ION key' 'secret key'")
parser.add_argument("ION_KEY")
parser.add_argument("SECRET_KEY")
args = parser.parse_args()

send_command()
if "Select an item to modify, or submit config:" in console.text:
    send_command(command='1')
send_command(command='1')
send_command(command='2', waitfor="Enter ION Key[")
send_command(command=args.ION_KEY)
send_command(command='3', waitfor="Enter ION secret[")
send_command(command=args.SECRET_KEY)
send_command(command='14', waitfor='Submit these changes now?[N]:')
send_command(command='Y', waitfor='login:')

