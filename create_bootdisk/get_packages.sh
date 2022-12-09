#!/bin/bash

# This script requires apt-dev to be installed

[ "$UID" -eq 0 ] || exec sudo bash "$0" "$@"
destination_folder=$1

mkdir -p "$destination_folder"
cd "$destination_folder"

printf "
$(pwd)
"

packages=(
"wireguard"
"git"
"qemu-kvm"
"libvirt-daemon"
"libvirt-clients"
"bridge-utils"
"cockpit"
"cockpit-machines"
"i2c-tools"
)


apt -o=dir::etc::sourcelist=./sources.list update
# download files
for package in ${packages[*]}
do
    echo $package
    apt -y install -d -o=dir::cache=./ -o=dir::etc::sourcelist=../sources.list $package
done
# create Package file
(cd $destination_folder/archives/; dpkg-scanpackages . > Packages)
# create Release file
(cd $destination_folder/archives/; apt-ftparchive release . > Release)
# Release file should be signed to able to validate files packages
#gpg -a --yes --clearsign --output InRelease --local-user $(id -un) --detach-sign /local_repo/debs/archives/Release

printf "
Downloaded $packages and dependancies to $destination_folder

add the following line to /etc/apt/sources.list: deb file:///<absolute Package path>/ ./

Because the release list is not signed apt needs to be told to trust them:

apt -y update --allow-insecure-repositories
apt -y install <package> --allow-unauthenticated

"