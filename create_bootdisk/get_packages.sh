#!/bin/bash

# This script requires apt-dev to be installed

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
#packages=$(apt-cache depends $options --recurse --no-recommends --no-suggests --no-conflicts --no-breaks --no-replaces --no-enhances --no-pre-depends ${PACKAGES[*]} | grep "^\w")
# download files
#apt install -y -d --reinstall $options ${packages[*]}
# do;
for package in ${PACKAGES[*]}
do
    printf "
    #####################################
    $package
    #####################################
    "
    # get all dependencies for this package
    # for p in $(apt-cache depends $options --recurse --no-recommends --no-suggests --no-conflicts --no-breaks --no-replaces --no-enhances --no-pre-depends $package | grep "^\w" | sort -u);
    # do
    #     apt-get download $options $p:amd64
    apt-get download $options $(apt-cache depends --recurse --no-recommends --no-suggests --no-conflicts --no-breaks --no-replaces --no-enhances $options $package | grep "^\w" | sort -u)
    #done
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