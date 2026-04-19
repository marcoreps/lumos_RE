import hashlib
import requests
import subprocess
import time

LASER_IP = "192.168.0.70"
SSH_USER = "mbtc"
REMOTE_PATH = "/mnt/SDCARD/data/printing/gcode.gc"

def run_engrave_100mm():
    gcode = """;wecreat 3.0.5-21
;canvas border: 0 0 210 210
M15S1
M107X-105Y-105
M57A450B30
M19S0
M18S1
G90
G4P1
M46A1B0
G0X105Y105
M25S1
M26S1
M24S15
M15S0
M59A0B50
M1S1
M3S1000
M11S0.005
M38F48 ;48 kHz Pulse rate
G0F15000
G1F6000
G0X55Y54.9F15000
G1X155Y54.9S10F6000 ;F6000 = 100mm/s
G1X155Y154.9
G1X55Y154.9
G1X55Y54.9
G0X55.1Y55
G0X105Y105
M9
G1 S0
M5
G90
M6
"""
    filename = "actual_engraving_for_reals.gc"
    with open(filename, "w") as f: 
        f.write(gcode)
    
    print(f"Uploading engraving job to {REMOTE_PATH}...")
    subprocess.run(["scp", "-O", "-o", "HostKeyAlgorithms=+ssh-rsa", 
                    filename, f"{SSH_USER}@{LASER_IP}:{REMOTE_PATH}"], check=True)
                    
    print("READY TO GO: Make sure the door is closed and safety goggles are on!")
    input("\nPress [ENTER] to fire da laz0r...")

    print("Triggering laser start via API...")
    try:
        response = requests.post(f"http://{LASER_IP}:8080/process/start")
        if response.status_code == 200:
            print("Job started successfully!")
        else:
            print(f"Failed to start. Status Code: {response.status_code}")
            print(f"Response: {response.text}")
    except Exception as e:
        print(f"Error calling API: {e}")

if __name__ == "__main__":
    run_engrave_100mm()
