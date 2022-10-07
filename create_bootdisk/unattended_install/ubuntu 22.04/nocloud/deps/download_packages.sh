# get dependencyies
# run this script from this directory to download debs

for i in $(apt-cache depends i2c-tools | grep -E 'Depends' | cut -d ':' -f 2,3 | sed -e s/'<'/''/ -e s/'>'/''/); do apt-get download $i; done
apt-get download i2c-tools

for i in $(apt-cache depends efibootmgr | grep -E 'Depends' | cut -d ':' -f 2,3 | sed -e s/'<'/''/ -e s/'>'/''/); do apt-get download $i; done
apt-get download efibootmgr

#for i in $(apt-cache depends jq | grep -E 'Depends|Recommends|Suggests' | cut -d ':' -f 2,3 | sed -e s/'<'/''/ -e s/'>'/''/); do apt-get download $i; done
#apt-get download jq

# FIX: libc6 will not install, workarround remove deb (no effect on installable)
rm libc6*