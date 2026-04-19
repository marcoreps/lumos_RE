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

    gcode = f""";wecreat 3.0.5-21
;canvas border: 0 0 210 210
M15S0
M107X-105Y-105
M41S0
M19S1
M18S1
M11S0.2
G90
M3S100
#headed

M3S1000
M11S0.005
M38F48
G0F480000
G1F300000
G0X55Y54.9F480000
G1X155Y54.9S0F300000
G1X155Y154.9
G1X55Y154.9
G1X55Y54.9
G0X55.1Y55

"""
    filename = "cal_100.gc"
    with open(filename, "w") as f: f.write(gcode)
    

    
    # 1. Upload
    print(f"Uploading test...")
    subprocess.run(["scp", "-O", "-o", "HostKeyAlgorithms=+ssh-rsa", 
                    filename, f"{SSH_USER}@{LASER_IP}:/mnt/SDCARD/data/framing/gcode.gc"], check=True)
    
    # 2. Trigger
    md5 = hashlib.md5(open(filename,"rb").read()).hexdigest().upper()
    payload = {"framing_file": "/mnt/SDCARD/data/framing/gcode.gc", "md5": md5}
    requests.post(f"http://{LASER_IP}:8080/lumos/dev/framing_preview_start", json=payload)
    
    print("Preview Running. Press Ctrl+C to stop.")
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        # stop tracing
        requests.post(f"http://{LASER_IP}:8080/lumos/dev/framing_preview_stop")
        print("\nStopped preview.")
            


if __name__ == "__main__":
    run_calibration_100mm()
