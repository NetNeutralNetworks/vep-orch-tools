#!/bin/bash
# elevate
[ "$UID" -eq 0 ] || exec sudo bash "$0" "$@"

usage(){
printf "
./create_bootdisk -i|--image

	-i, --image:  image file

"
}

if [ -z "$1" ]
  then
    usage
    exit 0
fi

while [ "$1" != "" ]; do
    case $1 in
        -i | --image )            shift
                                file="$1"
                                ;;
        -h | --help )           usage
                                exit
                                ;;
        * )                     usage
                                exit 1
    esac
    shift
done

mountfolder1=`pwd`"/part01/"
mountfolder2=`pwd`"/part02/"

# mount file to loop device
device=`losetup -f`
losetup -P $device $file

# partition and format disk
# sgdisk -og $device
# sgdisk -n 0:0:+1800MiB -t 0:ef00 $device
# mkfs.vfat -F32 $device"p1"
# sgdisk -n 0:0:0 $device
# mkfs.ext4 $device"p2"

# mount partitions
mkdir $mountfolder1
mount $device"p1" $mountfolder1
mkdir $mountfolder2
mount $device"p2" $mountfolder2

#########################################
# cleanup
#########################################
read -rsp $"Press any key to cleanup and exit" -n1 key
umount $mountfolder1
rm -r $mountfolder1
umount $mountfolder2
rm -r $mountfolder2
losetup -D