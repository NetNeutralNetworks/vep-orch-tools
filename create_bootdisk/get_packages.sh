#!/bin/bash

# This script requires apt-dev to be installed
if [[ -z $1 ]]; then
    echo "pleae spesify a detination folder, example: ./get_packages.sh unattended_install/ubuntu\ 22.04/local_repo/" 1>&2
    exit 1
fi

#[ "$UID" -eq 0 ] || exec sudo bash "$0" "$@"
destination_folder=$1

mkdir -p "$destination_folder"
cd "$destination_folder"

printf "
$(pwd)
"

PACKAGES=(
"wireguard"
"git"
"qemu-system-x86"
"libvirt-daemon"
"libvirt-clients"
"bridge-utils"
"cockpit"
"cockpit-machines"
"i2c-tools"
"snmpd"
"debsums"
"efibootmgr"
"python3-libvirt"
"dnsmasq-base"
)
options="-o=dir::cache=./ -o=dir::etc::sourcelist=../sources.list"
sudo apt update $options

printf "
#####################################
linux-image-generic
#####################################
"
apt-get download $options $(apt-cache depends --recurse --no-recommends --no-suggests --no-conflicts --no-breaks --no-replaces --no-enhances $options linux-image-generic | grep "^\w" | sort -u )


for package in ${PACKAGES[*]}
do
    printf "
    #####################################
    $package
    #####################################
    "
    apt-get download $options $(apt-cache depends --recurse --no-recommends --no-suggests --no-conflicts --no-breaks --no-replaces --no-enhances $options $package | grep -vE "^linux-" | grep "^\w" | sort -u )
done

# create Package file
#cd archives
dpkg-scanpackages -a amd64 . > Packages
# create Release file
apt-ftparchive release . > Release
# Release file should be signed to able to validate files packages
#gpg -a --yes --clearsign --output InRelease --local-user $(id -un) --detach-sign /local_repo/debs/archives/Release

printf "
Downloaded $packages and dependancies to $destination_folder

add the following line to /etc/apt/sources.list: deb file:///<absolute Package path>/ ./

Because the release list is not signed apt needs to be told to trust them:

apt -y update --allow-insecure-repositories
apt -y install <package> --allow-unauthenticated

"
