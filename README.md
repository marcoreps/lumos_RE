# lumos_RE
 Investigating remote control possibilities for WeCreat Lumos Ultra Laser Engraver

---

# Confirmed

## Network access

Observed defaults:

```text
SSH/FTP user:      mbtc
SSH/FTP password:  mbtc
HTTP API:          TCP/8080
Filesystem server: TCP/8082 (Mongoose 7.17)
OS:                Tina Linux (OpenWrt-derived, Allwinner SoC)
```

SSH:

```bash
ssh -o HostKeyAlgorithms=+ssh-rsa \
    -o PubkeyAcceptedAlgorithms=+ssh-rsa \
    mbtc@192.168.0.70
```

The service on **port 8082** exposes the root filesystem through a Mongoose file server.



## Interesting filesystem paths

```text
/etc/mbtc/                               machine configuration and calibration stuff
/etc/mbtc/sn.json                        factory serial number
/overlay/work/logfile.txt                mbtc_creater runtime log

/mnt/SDCARD/data/framing/gcode.gc        generated job G-code
/mnt/SDCARD/data/framing/framing_mode.gcode
/mnt/SDCARD/data/framing/framing_data.gcode

/usr/bin/mbtc_creater                    main local API / machine-control process

/mnt/UDISK/update.tar.gz                 staged OTA package
```

## curl http://192.168.0.70:8080/device/info

Example from app version `1.5.3`:

```json
{
  "app_version": "1.5.3",
  "dev_type": "LU25xx",
  "laser_id": "5w_uv",
  "name": "wecreat",
  "ver_mcu_1": "000241",
  "ver_mcu_2": "120015"
}
```

## OEM software on Linux

The Windows WeCreat MakeIt application is Electron-based and can run under Bottles/Wine.

A currently known-working combination is:

```text
Runner:       Caffe 8.21
Launch flag:  --no-sandbox
DXVK disabled
```

---


# UV source control

## RS232 link

The 5 W UV source communicate with MCU1 over RS232:

```text
9600 baud
8 data bits
no parity
1 stop bit
CRLF-terminated ASCII commands
```
## UV standby / pump control

This was the main reason for this project. The older firmware left the UV source fully pumped whenever the engraver was powered on, even while using only the MOPA module. That caused roughly 100 W of unnecessary power consumption, cooling-fan noise, and unnecessary UV pump/crystal wear. After flashing ed658bb4e05c5a341dca7c98ba14b955.tar.gz on September 13 2026 using manual_firmware_update.py I am able to run query_mcu.py M43S0 to power down the UV laser source and query_mcu.py M43S1 to power it back up. Internally I believe this translates to mcu1 sending SS 0 or SS 1 to the UV source via RS232. Awesome!

The dev firmware containing MCU1 version `000241` adds a new `M43` handler:

```text
M43S0  ->  SS 0\r\n  -> UV source low-power / standby state
M43S1  ->  SS 1\r\n  -> UV source powered back up
```

Using the generic MCU command utility:

```bash
./mcu_cmd.py M43S0
./mcu_cmd.py M43S1
```

The same firmware also adds a not yet understood new MCode:

```text
M44 -> RVV\r\n
```

### Related MCU1 behavior

Firmware analysis also shows:

```text
M41S0 -> SPK1\r\n
M41S1 -> SPK0\r\n
```

This appears to control the UV source's equivalent of "first pulse killer" or something like that?

---


# Firmware update notes

Vendor update feeds:

```text
https://package.wecreat.com/lumos-pro/test.txt
https://package.wecreat.com/lumos-pro/dev.txt
( https://package.wecreat.com/lumos-pro/version.json )
```


Files seen in the last few months:

```text
    https://package.wecreat.com/lumos-pro/test.txt
    https://package.wecreat.com/lumos-pro/224ba7007723fd804633114686eac904.tar.gz

    https://package.wecreat.com/lumos-pro/dev.txt
    https://package.wecreat.com/lumos-pro/5035695862f8e56b3ad871f9ac5a1e9e.tar.gz
    https://package.wecreat.com/lumos-pro/4756e18225fd1c4fbe5d6dffb329fa0f.tar.gz
    https://package.wecreat.com/lumos-pro/b698c91f4f73260f9c56488abee08d82.tar.gz
    https://package.wecreat.com/lumos-pro/679d452c15a3f9876959465f006944e3.tar.gz
    https://package.wecreat.com/lumos-pro/ed658bb4e05c5a341dca7c98ba14b955.tar.gz

```
After flashing firmware with manual_firmware_update.py, a power cycle is needed for the machine to report íts new versions. Careful here, brickage likely not impossible.


---

# Local HTTP API

Endpoints found in `/usr/bin/mbtc_creater` include:

## Device

```text
/device/info
/device/heartbeat
/device/set_config
/device/set_device_type
/device/set_wlan0_mac
/device/set_factory_sn
/device/sys_restart
/device/set_inverse_dis
/device/laser_led_switch
/device/global/cfg_peripheral_status
```

## Camera

```text
/camera/take_photo
/camera/measure_distance
/camera/get_calibration
/camera/measure_material_thick

/device/camera/factory_upload
/device/camera/factory_download
/device/camera/upload
/device/camera/download

/lumos/camera/start_autofocus
/lumos/camera/stop_autofocus
```

## Material / jobs

```text
/device/material/upload
/device/material/download

/process/upload
/process/multipart
/process/fileupload_via_ftp
/process/start
/process/control
/process/status
/process/door_status
```

## Lighting

```text
/device/light/status
/device/light/progress
/device/light/focus_light
/device/light/logo_light
/device/light/get_init_value
```

The OEM application reports PWM-controlled peripherals including:

```text
frontlight
backlight
servo
```

## Direct command endpoints

Useful reverse-engineering endpoints include:

```text
/test/cmd/mcu
/test/cmd/rs485
```

The MCU endpoint expects the command  plus a matching uppercase MD5 query parameter.

---



# Controller / serial architecture

## `/dev/ttyS2`

onnects to the secondary controller responsible for at least:

- Z-axis motion
- physical start-button supervision

## `/dev/ttyS4`

Connects to MCU1, a GD32F407 in LQFP144.

Observed boot/default baud rate:

```text
500000 baud
```

The UV source RS232 path reaches MCU1 as follows:

```text
UV TX -> level shifter -> GD32F407 pin 116 / PD2
UV RX <- level shifter <- GD32F407 pin 113 / PC12
```

These pins correspond to UART5 in the STM32/GD32 peripheral mapping.

---

# MCU commands

## Pretty sure

| Command | Function / observation |
|---|---|
| `$H0` | Home Z axis and remain at home |
| `$H1` | Home Z axis and return to previous position |
| `$RST` | Reset MCU |
| `$GETVER` | MCU version query; raw response includes e.g. `V1:000241` |
| `M27` | Position query |
| `M22` | Safety/limit state query |
| `M29` | Machine state query |
| `M15 S0..100` | Exhaust fan speed |
| `M38 F...` | Pulse frequency, kHz |
| `M39 P...` | Pulse width, ns |
| `M3 S...` | Constant laser power mode |
| `M4 S...` | Speed-proportional laser power mode |
| `M41S0/1` | UV PulseKill mode; maps to `SPK1` / `SPK0` respectively |
| `M43S0/1` | UV source standby / wake; maps to `SS 0` / `SS 1` |
| `M44` | Sends UV-source query `RVV` |


Motion/G-code conventions:

```text
G0 / G1                 movement
F value                  mm/min (mm/s * 60)
S value                  laser power, apparently 0..1000
G4 P1                    1 ms dwell
```

Additional strings of interest that need figuring out:

```text
M134S1
M134S0
M33Y1
M33Y0
M107
$GETID
$SH1
$SH0
M54S0
M54S1
M40S0
M3
```

## LightBurn profile clues

From a LightBurn `.lbdev` profile:

```json
"Macro0_Content": "M18S1\n",
"Macro0_Label": "455Blue",
"Macro3_Content": "M18S0\n",
"Macro3_Label": "1064red"
```

This suggests `M18` is related to source/optical-path selection.

---

# Process state and job control

Observed `/process/status` values:

```text
2 = busy / working
3 = job finished but still loaded/armed? (exact semantics not fully confirmed)
4 = waiting / idle
6 = preview tracing
```

A job waiting for the physical start-button press can be started with press_physical_start_button.py or:

```bash
curl -X POST http://192.168.0.70:8080/process/start
```

This will mercilessly start whatever file is "armed", so make sure there are no eyes or flammables in the working volume.

---

# GPIO notes

Front RGB LED:

```bash
# blue
echo 0 > /sys/class/gpio/gpio114/value

# red
echo 0 > /sys/class/gpio/gpio115/value

# green
echo 0 > /sys/class/gpio/gpio116/value
```

Focus-assist red lasers:

```bash
# front
echo 0 > /sys/class/gpio/gpio113/value

# front-left
echo 0 > /sys/class/gpio/gpio112/value
```

Killing `mbtc_creater` together with its restart mechanism eventually appears to trigger a watchdog/safety response and turns the machine's lights off.


There's some very annoying coil whine associated with the interior lighting, it's usually noisy mirror drivers, not here! disable_interior_lights.py or old operator age takes care of that.

---

# TODO / Future investigations

There is still a lot of functionality in the Lumos Ultra that has not been fully understood or exposed outside the OEM software.

- [ ] **Camera**
  - Document the camera API and available controls
  - Determine whether exposure, gain, white balance, etc. can be controlled
  - Locate + document factory and user camera calibration
  - Camera-based automated research of MOPA Color engraving?!

- [ ] **Workpiece height measurement**
  - Reverse engineer the intended autofocus system using the two red focus-assist laser points
  - Investigate `/lumos/camera/start_autofocus`, `/lumos/camera/stop_autofocus`, `/camera/measure_distance`, and related MCU commands
  - Find out whether the unfinished/prototype autofocus implementation can be made reliable

- [ ] **Manual Z-height adjustment knob**
  - Document the calibration function for it maybe

- [ ] **Field-lenses**
  - Determine where per-machine and/or per-lens field-correction calibration is stored.
  - Determine whether correction is performed in MakeIt before G-code generation, by `mbtc_creater`, or by the MCU during playback.
  - Extract the de-distort model and make it usable by third-party software
  - Figure out automatic field-lens detection if implemented in my prototype machine at all
  - Find the working-area dimensions and correction data associated with all supported lens
  - Investigate whether new other custom F-theta lenses can be used

- [ ] **Accessories**
  - Document the gcode used by the rotary attachment and linear slider extension
  - Identify the two additional stepper-motor channels and their corresponding MCU/G-code commands.
  - Determine axis scaling, homing, limits, and accessory-detection mechanisms

- [ ] **Timing compensation**
  - Laser-on, laser-off, jump, polygon or similar timing constants have to be in gcode right?
  - Is the GD32 and representation in gocde sufficiently "agile" accomodate hardware behavior perfectly?
  - Expose these parameters if possible; accurate timing is particularly important for high-pass-count precision work such as PCB structuring.

- [ ] **Peripherals**
  - `/device/light/get_init_value`?
  - What does the `servo` PWM channel control?

- [ ] **Configuration and calibration storage**
  - Lots of interesting files in `/etc/mbtc/`.
  - Which values are factory calibration, user configuration, machine identity, or replaceable defaults?

- [ ] **Network/privacy behaviour**
  - What's the OEM application's downloaded `tracking.xlsx` / `tracking.db`?

---


```text
 _____  _              __     _
|_   _||_| ___  _ _   |  |   |_| ___  _ _  _ _
  | |   _ |   ||   |  |  |__ | ||   || | ||_'_|
  | |  | || | || _ |  |_____||_||_|_||___||_,_|
  |_|  |_||_|_||_|_|  Tina is Based on OpenWrt!
 ----------------------------------------------
 Tina Linux (Neptune, 6191F77D)
 ----------------------------------------------
mbtc@mbtc_421D4F:~# strings /usr/bin/mbtc_creater | grep -E "(/process/|/device/|/camera/|/job/)"
/device/info
/device/heartbeat
/device/set_config
/device/set_device_type
/device/set_wlan0_mac
/device/camera/factory_upload
/device/camera/factory_download
/device/camera/upload
/device/camera/download
/device/material/upload
/device/material/download
/device/set_factory_sn
/device/sys_restart
/device/set_inverse_dis
/device/laser_led_switch
/camera/take_photo
/camera/measure_distance
/camera/get_calibration
/camera/measure_material_thick
/process/upload
/process/multipart
/process/fileupload_via_ftp
/process/start
/process/control
/process/status
/process/door_status
/device/light/status
/device/light/progress
/device/light/focus_light
/device/light/logo_light
/device/global/cfg_peripheral_status
/lumos/camera/start_autofocus
/lumos/camera/stop_autofocus
```
