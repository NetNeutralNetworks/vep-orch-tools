# get dependencyies
for i in $(apt-cache depends i2c-tools | grep -E 'Depends|Recommends|Suggests' | cut -d ':' -f 2,3 | sed -e s/'<'/''/ -e s/'>'/''/); do apt-get download $i; done
for i in $(apt-cache depends jq | grep -E 'Depends|Recommends|Suggests' | cut -d ':' -f 2,3 | sed -e s/'<'/''/ -e s/'>'/''/); do apt-get download $i; done
for i in $(apt-cache depends efibootmgr | grep -E 'Depends|Recommends|Suggests' | cut -d ':' -f 2,3 | sed -e s/'<'/''/ -e s/'>'/''/); do apt-get download $i; done

apt-get download i2c-tools
apt-get download efibootmgr
apt-get download jq
