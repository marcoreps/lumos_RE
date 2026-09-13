#!/bin/sh

# 指定SD卡的设备名称（例如：/dev/mmcblk0）
SD_CARD_DEVICE="/dev/mmcblk0"
SD_CARD_SUBDIR_DATA="/mnt/SDCARD/data"
SD_CARD_SUBDIR_CONF="/mnt/SDCARD/config"
SD_CARD_SUBDIR_DATA_FRAMING="/mnt/SDCARD/data/framing"
SD_CARD_SUBDIR_DATA_PRINT="/mnt/SDCARD/data/printing"
SD_CARD_SUBDIR_DATA_TEMP="/mnt/SDCARD/data/tmp"

umount /dev/mmcblk0p1
umount /dev/mmcblk0p2

# 检查设备是否存在
if [ ! -e "$SD_CARD_DEVICE" ]; then
    echo "错误：设备 '$SD_CARD_DEVICE' 不存在。"
    exit 1
fi

# 使用lsblk检查分区数量
PARTITION_COUNT=$(lsblk -l -n "$SD_CARD_DEVICE" | grep -c "${SD_CARD_DEVICE##*/}p")

# 判断分区数量
if [ "$PARTITION_COUNT" -eq 2 ]; then
    echo "SD卡 '$SD_CARD_DEVICE' 已经分两个区。"
	
else # "$PARTITION_COUNT" -lt 2 ]; then
    echo "SD卡 '$SD_CARD_DEVICE' 分区数量不足两个（当前分区数：$PARTITION_COUNT)。"
	# ............... root ............
	if [ "$EUID" -ne 0 ]; then
	  echo "...... root ....................."
	  exit 1
	fi

	# ...........................
	if [ -z "$SD_CARD_DEVICE" ]; then
	  echo "......: $0 <SD.........>"
	  echo "......: $0 /dev/mmcblk0"
	  exit 1
	fi

	DEVICE=$SD_CARD_DEVICE

	# ........................
	if [ ! -e "$DEVICE" ]; then
	  echo "...... $DEVICE ........."
	  exit 1
	fi

	# ..................
	echo "....................."
	umount ${DEVICE}p* 2>/dev/null

	# ...... fdisk ......
	echo "...... SD ......"
	{
	  echo o              # ........................
	  echo n              # ...............
	  echo p              # .........
	  echo 1              # .........
	  echo                # ..................
	  echo +512M          # ...... 512MB ..................
	  echo n              # .....................
	  echo p              # .........
	  echo 2              # .........
	  echo                # ..................
	  echo                # ..................
	  echo w              # ...............
	} | fdisk "$DEVICE"

	# ...............
	echo ".................."
	mkfs.ext4 "${DEVICE}p1"  # ........................... FAT32
	mkfs.ext4 "${DEVICE}p2"  # ........................... ext4

	# ......
	echo "SD .............................."
	echo "...... 1 (FAT32): ${DEVICE}p1"
	echo "...... 2 (ext4): ${DEVICE}p2"

	
fi

if [ ! -d "$SD_CARD_SUBDIR_DATA" ]; then
	mkdir -p "$SD_CARD_SUBDIR_DATA"
fi

if [ ! -d "$SD_CARD_SUBDIR_CONF" ]; then
	mkdir -p "$SD_CARD_SUBDIR_CONF"
fi

#mount -t ext4 /dev/mmcblk0p1 /mnt/SDCARD/config
#mount -t ext4 /dev/mmcblk0p2 /mnt/SDCARD/data

if [ ! -d "$SD_CARD_SUBDIR_DATA_FRAMING" ]; then
	mkdir -p "$SD_CARD_SUBDIR_DATA_FRAMING"
fi

if [ ! -d "$SD_CARD_SUBDIR_DATA_PRINT" ]; then
	mkdir -p "$SD_CARD_SUBDIR_DATA_PRINT"
fi

if [ ! -d "$SD_CARD_SUBDIR_DATA_TEMP" ]; then
	mkdir -p "$SD_CARD_SUBDIR_DATA_TEMP"
fi

#mkdir -p /mnt/SDCARD/config
#mkdir -p /mnt/SDCARD/data

