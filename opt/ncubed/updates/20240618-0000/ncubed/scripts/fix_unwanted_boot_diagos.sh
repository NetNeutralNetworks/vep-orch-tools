mount /dev/mmcblk0p2 /mnt

string='efibootmgr -O' 
sed -i -e "\|$string|h; \${x;s|$string||;{g;t};a\\" -e "$string" -e "}" /mnt/etc/rc.local

string='( sleep 30 ; init 6 ) &' 
sed -i -e "\|$string|h; \${x;s|$string||;{g;t};a\\" -e "$string" -e "}" /mnt/etc/rc.local

umount /mnt