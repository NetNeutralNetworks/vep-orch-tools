#!/bin/python3
def render_xml(VMNAME, CPU, MEM):
    return f'''\
    <domain type='kvm'>
  <name>{VMNAME}</name>
  <memory unit='GiB'>{MEM}</memory>
  <currentMemory unit='GiB'>{MEM}</currentMemory>
  <vcpu placement='static'>{CPU}</vcpu>
  <os>
    <type arch='x86_64' machine='pc-i440fx-focal'>hvm</type>
    <boot dev='hd'/>
  </os>
  <features>
    <acpi/>
    <apic/>
    <vmport state='off'/>
  </features>
  <cpu mode='host-model' check='partial'>
    <topology sockets='{CPU}' cores='1' threads='1'/>
  </cpu>
  <clock offset='utc'>
    <timer name='rtc' tickpolicy='catchup'/>
    <timer name='pit' tickpolicy='delay'/>
    <timer name='hpet' present='no'/>
  </clock>
  <on_poweroff>destroy</on_poweroff>
  <on_reboot>restart</on_reboot>
  <on_crash>destroy</on_crash>
  <pm>
    <suspend-to-mem enabled='no'/>
    <suspend-to-disk enabled='no'/>
  </pm>
  <devices>
    <emulator>/usr/bin/qemu-system-x86_64</emulator>
    <disk type='file' device='disk'>
      <driver name='qemu' type='qcow2'/>
      <source file='/var/lib/libvirt/images/{VMNAME}.qcow2'/>
      <target dev='hda' bus='ide'/>
      <address type='drive' controller='0' bus='0' target='0' unit='0'/>
    </disk>
    <controller type='usb' index='0' model='ich9-ehci1'>
    </controller>
    <controller type='usb' index='0' model='ich9-uhci1'>
      <master startport='0'/>
    </controller>
    <controller type='usb' index='0' model='ich9-uhci2'>
      <master startport='2'/>
    </controller>
    <controller type='usb' index='0' model='ich9-uhci3'>
      <master startport='4'/>
    </controller>
    <controller type='pci' index='0' model='pci-root'/>
    <controller type='ide' index='0'>
    </controller>
    <controller type='virtio-serial' index='0'>
    </controller>
    <interface type='bridge'>
      <source bridge='br-MGMT'/>
      <model type='virtio'/>
      <link state='up'/>
    </interface>
    <interface type='bridge'>
      <source bridge='br-WAN0_nat_i'/>
      <model type='virtio'/>
      <link state='up'/>
    </interface>
    <interface type='bridge'>
      <source bridge='br-WAN1_nat_i'/>
      <model type='virtio'/>
      <link state='up'/>
    </interface>
    <interface type='bridge'>
      <source bridge='br-WAN2_nat_i'/>
      <model type='virtio'/>
      <link state='up'/>
    </interface>
    <interface type='bridge'>
      <source bridge='br-WAN0_l2_i'/>
      <model type='virtio'/>
      <link state='up'/>
    </interface>
    <interface type='bridge'>
      <source bridge='br-WAN0_l2_i'/>
      <model type='virtio'/>
      <link state='up'/>
    </interface>
    <interface type='bridge'>
      <source bridge='br-WAN1_l2_i'/>
      <model type='virtio'/>
      <link state='up'/>
    </interface>
    <interface type='bridge'>
      <source bridge='br-WAN2_l2_i'/>
      <model type='virtio'/>
      <link state='up'/>
    </interface>
    <interface type='bridge'>
      <source bridge='br-trunk34'/>
      <model type='virtio'/>
      <link state='up'/>
    </interface>
    <interface type='bridge'>
      <source bridge='br-trunk56'/>
      <model type='virtio'/>
      <link state='up'/>
    </interface>
    <serial type='pty'>
      <target type='isa-serial' port='0'>
        <model name='isa-serial'/>
      </target>
    </serial>
    <console type='pty'>
      <target type='serial' port='0'/>
    </console>
    <channel type='unix'>
      <target type='virtio' name='org.qemu.guest_agent.0'/>
      <address type='virtio-serial' controller='0' bus='0' port='1'/>
    </channel>
    <channel type='spicevmc'>
      <target type='virtio' name='com.redhat.spice.0'/>
      <address type='virtio-serial' controller='0' bus='0' port='2'/>
    </channel>
    <input type='mouse' bus='ps2'/>
    <input type='keyboard' bus='ps2'/>
    <graphics type='spice' autoport='yes' listen='127.0.0.1'>
      <listen type='address' address='127.0.0.1'/>
      <image compression='off'/>
    </graphics>
    <graphics type='vnc' port='-1' autoport='yes' listen='127.0.0.1'>
      <listen type='address' address='127.0.0.1'/>
    </graphics>
    <sound model='ich6'>
    </sound>
    <video>
      <model type='qxl' ram='65536' vram='65536' vgamem='16384' heads='1' primary='yes'/>
    </video>
    <redirdev bus='usb' type='spicevmc'>
      <address type='usb' bus='0' port='1'/>
    </redirdev>
    <redirdev bus='usb' type='spicevmc'>
      <address type='usb' bus='0' port='2'/>
    </redirdev>
    <memballoon model='virtio'>
    </memballoon>
  </devices>
</domain>'''

if __name__ == '__main__':
    print (render_xml(VMNAME='ION'))
