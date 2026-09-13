#! /bin/sh
 
host_dir=`echo ~`
app_name="mbtc_creater"
bt_gatt_name="bt_gatt_mbtc"
daemon_vsftpd_name="vsftpd"
file_name="bindmonitor.log"
pid=0
proc_app_num()
{
	num=`ps| grep $app_name | grep -v grep | wc -l`
	echo "app mbtc_creater num:"$num
	return $num
}

proc_bt_num()
{
	num=`ps| grep $bt_gatt_name | grep -v grep | wc -l`
	echo "app bt_gatt_mbtc num:"$num
	return $num
}

proc_app_id()
{
	pid=`ps| grep $app_name | grep -v grep | awk '{print $1}'`
}
proc_bt_id()
{
	pid=`ps| grep $bt_gatt_name | grep -v grep | awk '{print $1}'`
}


proc_vsftpd_id()
{
	pid=`ps| grep $daemon_vsftpd_name | grep -v grep | awk '{print $1}'`
}


while :
	do
		proc_app_num
		number=$?
		if [ $number -eq 0 ];then 
			/usr/bin/mbtc_creater &
			proc_app_id
			#echo ${pid}, `date` #>> $file_name
		fi
		#echo $date
		proc_bt_num
		number=$?
		if [ $number -eq 0 ];then 
			/usr/bin/bt_gatt_mbtc &
			proc_bt_id
			#echo ${pid}, `date` #>> $file_name
		fi
		proc_vsftpd_id
		number=$?
		if [ $number -eq 0 ];then 
			/usr/bin/vsftpd &
			proc_vsftpd_id
			#echo ${pid}, `date` #>> $file_name
		fi
	sleep 60
	done
