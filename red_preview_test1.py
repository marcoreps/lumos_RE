import hashlib
import requests
import subprocess
import json
import time


LASER_IP = "192.168.0.70"
SSH_USER = "mbtc"
GCODE_FILENAME = "preview_square.gc"
REMOTE_PATH = "/mnt/SDCARD/data/framing/gcode.gc"


def get_md5(filename):
    with open(filename, "rb") as f:
        return hashlib.md5(f.read()).hexdigest().upper()

def run_calibration_100mm():
    # We want a 100mm square centered at (105, 105)

    gcode = f""";100mm Calibration Square
M15S0
M107X-105Y-105 ; Confirmed Center Offset
M19S1
M18S1          ; Red Dot
M11S0.2
G90
M3S100
#headed
M3S1000
G0F480000
; Drawing the Square
G0 X55 Y55
G1 X155 Y55 S0
G1 X155 Y155
G1 X55 Y155
G1 X55 Y55
; Center Crosshair for alignment
G0 X100 Y105
G1 X110 Y105
G0 X105 Y100
G1 X105 Y110
M6
"""
    filename = "cal_100.gc"
    with open(filename, "w") as f: f.write(gcode)
    

    
    # 1. Upload
    print(f"[*] Uploading 100mm test...")
    subprocess.run(["scp", "-O", "-o", "HostKeyAlgorithms=+ssh-rsa", 
                    filename, f"{SSH_USER}@{LASER_IP}:/mnt/SDCARD/data/framing/gcode.gc"], check=True)
    
    # 2. Trigger
    md5 = hashlib.md5(open(filename,"rb").read()).hexdigest().upper()
    payload = {"framing_file": "/mnt/SDCARD/data/framing/gcode.gc", "md5": md5}
    requests.post(f"http://{LASER_IP}:8080/lumos/dev/framing_preview_start", json=payload)
    
    print("[+] 100mm Preview Running. Measure it! Press Ctrl+C to stop.")
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        # stop tracing
        requests.post(f"http://{LASER_IP}:8080/lumos/dev/framing_preview_stop")
        print("\n[!] Stopped.")
            


if __name__ == "__main__":
    run_calibration_100mm()
