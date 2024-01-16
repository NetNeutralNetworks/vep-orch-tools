# get dependencyies
# run this script from this directory to download debs
ORIGPATH=$(pwd)
SCRIPT=$(realpath "$0")
SCRIPTPATH=$(dirname "$SCRIPT")
echo $SCRIPTPATH
cd "$SCRIPTPATH"

printf "
$(pwd)
"

rm *.deb

options="-o=dir::cache=./ -o=dir::etc::sourcelist=../../sources.list"
sudo apt update $options

PACKAGES=(
"i2c-tools"
"efibootmgr"
)

for package in ${PACKAGES[*]}
do
    printf "
    #####################################
    $package
    #####################################
    "
    apt-get download $options $(apt-cache depends $options $package | grep -E 'Depends' | cut -d ':' -f 2,3 | sed -e s/'<'/''/ -e s/'>'/''/)
    apt-get download $options i2c-tools
done

#for i in $(apt-cache depends jq | grep -E 'Depends|Recommends|Suggests' | cut -d ':' -f 2,3 | sed -e s/'<'/''/ -e s/'>'/''/); do apt-get download $i; done
#apt-get download jq

# FIX: libc6 will not install, workarround remove deb (no effect on installable)
rm libc6*
rm -f *.bin

cd "$ORIGPATH"