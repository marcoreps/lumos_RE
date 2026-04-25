import hashlib
import requests
import subprocess
import time

LASER_IP = "192.168.0.70"
SSH_USER = "mbtc"
REMOTE_PATH = "/mnt/SDCARD/data/printing/gcode.gc"

def run_engrave_100mm():
    gcode = """
M15S1
M107X-105Y-105                         ; Sets the workspace coordinate offset to center
M57A450B30
M19S0                                  ; Red preview point disabled
M18S0                                  ; UV preview point disabled?
G90                                    ; Set to Absolute Positioning mode
G4P1                                   ; Dwell/Pause for 1ms/s
M46A1B0
G0X105Y105                             ; Rapid move to the center of the canvas
M25S1
M26S1
M24S15
M15S0                                   ; Exhaust fan speed range 0 - 100
M59A-1000B50
M1S1                                   
M3S1000
M11S0.005                              ; Micro-delay for mirror stabilization?
M38F48                                 ; Set Laser Pulse Frequency to 48kHz
M39P200                                ; Set MOPA Pulse Width to 200ns
G0F15000                               ; Set Rapid Travel speed (250 mm/s)
G1F12000                               ; Set Linear Work speed (200 mm/s)
G0X55Y54.9F15000                       ; Rapid move to the bottom-left corner of the square
G1X155Y54.9S10F600                     ; Draw bottom edge: 100mm at 1% power (S10) and 10 mm/s (F600)
G1X155Y154.9                           ; Draw right edge: 100mm move
G1X55Y154.9                            ; Draw top edge: 100mm move
G1X55Y54.9                             ; Draw left edge: 100mm move
G0X55.1Y55                             ; Slight rapid offset at completion

G0X105Y105                             ; Rapid move back to center/home
M9                                     
G1 S0                                  ; Ensure laser power is set to zero
M5                                     
G90                                    ; Set to Absolute Positioning mode
M6                                     ; End of program




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
