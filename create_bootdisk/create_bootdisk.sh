#!/bin/bash
# elevate
[ "$UID" -eq 0 ] || exec sudo bash "$0" "$@"

usage(){
printf "
./create_bootdisk [-t|--target] [-C]

	-t, --target:  /dev/<dev> (target device)
	-C, --copyimages

"
}

while [ "$1" != "" ]; do
    case $1 in
        -t | --target )            shift
                                usbdevice="$1"
                                ;;
        -C | --copyimages )     copyimages=1
        			 			;;
        -h | --help )           usage
                                exit
                                ;;
        * )                     usage
                                exit 1
    esac
    shift
done

if [ ${usbdevice} ]; then
	printf "Image will be built and put on $usbdevice\n"
	read -rsp $"Press any key to continue..." -n1 key
fi

# set vars
file="netcube-autoinstall.$(date "+%Y.%m.%d-%H.%M.%S").img"
#isofile="ubuntu-20.04.4-live-server-amd64.iso"
#isofile="ubuntu-22.04.1-live-server-amd64.iso"
#isofile="ubuntu-22.04.3-live-server-amd64.iso"
isofile="ubuntu-22.04.4-live-server-amd64.iso"
mountfolder1=`pwd`"/part01/"
mountfolder2=`pwd`"/part02/"

#########################################
# prep disk file
#########################################
# if [ ${copyimages} ]; then
# 	# create 8Gb empty file
# 	dd if=/dev/zero of=$file bs=8G seek=1 count=0
# else
# 	# create 4Gb empty file
# 	dd if=/dev/zero of=$file bs=4G seek=1 count=0
# fi
truncate -s 8G $file
# sgdisk -og $file
# sgdisk -n 0:0:+3500MiB -t 0:ef00 $file
# sgdisk -n 0:0:0 $file

# mount file to loop device
device=`losetup -f`
losetup -P $device $file

# partition and format disk
sgdisk -og $device
sgdisk -n 0:0:+3500MiB -t 0:ef00 $device
mkfs.vfat -F32 $device"p1"
sgdisk -n 0:0:0 $device
mkfs.ext4 $device"p2"

# mount partitions
mkdir $mountfolder1
mount $device"p1" $mountfolder1
mkdir $mountfolder2
mount $device"p2" $mountfolder2

#########################################
# Write files to partitions
#########################################
if mountpoint -q $mountfolder1; then
	# copy boot files
	7z x $isofile -o$mountfolder1
	#cp -r ./unattended_install/ubuntu\ 20.04/* $mountfolder
	cp -r ./unattended_install/ubuntu\ 22.04/* $mountfolder1
	mkdir $mountfolder1/ncubed
	cp -r ../opt/ncubed/updates $mountfolder1/ncubed
	cp -r ../opt/ncubed/FIRMWARE $mountfolder1/ncubed
	cp -r ./unattended_install/bin $mountfolder1/ncubed
else
	printf "ERROR: disk not properly mounted"
	exit 0
fi

if mountpoint -q $mountfolder2; then
	if [ ${copyimages} ]; then
		cp -r ./unattended_install/images $mountfolder2/
	else
		mkdir $mountfolder2/images
		touch $mountfolder2/images/put_qcow2_images_here
	fi
else
	printf "ERROR: disk not properly mounted"
	exit 0
fi

#########################################
# if device given, write image to device
#########################################
printf "
\e[1m To write image to usb device use: 
\e[92m sudo dd if=$file of=/dev/<dev> oflag=direct bs=16M status=progress conv=fsync
\e[0m
"

if [ ${usbdevice} ]; then
	dd if=$file of=$usbdevice oflag=direct bs=16M status=progress conv=fsync
fi

#########################################
# cleanup
#########################################
read -rsp $"Press any key to cleanup and exit" -n1 key
umount $mountfolder1
rm -r $mountfolder1
umount $mountfolder2
rm -r $mountfolder2
losetup -D