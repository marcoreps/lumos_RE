if [ -f /etc/mbtc/wlan0_mac.txt ];then
        wlan0_mac1=`cat /etc/mbtc/wlan0_mac.txt`
        echo "mac_from web:$wlan0_mac1"
        ifconfig wlan0 down
        ifconfig wlan0 hw ether $wlan0_mac1
        ifconfig wlan0 up
else
        wlan0_mac1=`cat /sys/class/sunxi_info/sys_info |grep serial|awk '{print $3}'|cut -b 3-4`
        wlan0_mac2=`cat /sys/class/sunxi_info/sys_info |grep serial|awk '{print $3}'|cut -b 5-6`
        wlan0_mac3=`cat /sys/class/sunxi_info/sys_info |grep serial|awk '{print $3}'|cut -b 7-8`
        wlan0_mac=4C:43:31:$wlan0_mac1:$wlan0_mac2:$wlan0_mac3
        echo "mac_from chipid $wlan0_mac"
        ifconfig wlan0 down
        ifconfig wlan0 hw ether $wlan0_mac
        ifconfig wlan0 up
fi
ps|grep udhcpc|grep -v grep|awk '{print $1}'|xargs kill -9
udhcpc -i wlan0 &
