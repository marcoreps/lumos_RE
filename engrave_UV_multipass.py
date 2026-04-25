import hashlib
import requests
import subprocess
import time

LASER_IP = "192.168.0.70"
STATUS_URL = "http://192.168.0.70:8080/process/status"
SSH_USER = "mbtc"
REMOTE_PATH = "/mnt/SDCARD/data/printing/gcode.gc"
number_of_passes = 2

def get_laser_status():
    try:
        response = requests.get(STATUS_URL, timeout=5)
        data = response.json()
        return data.get("status")
    except Exception as e:
        print(f"Error communicating with Lazer: {e}")
        return None

def run_engrave_100mm():
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
    filename = "random_UV_gcode.gc"
    
    print(f"Uploading engraving job to {REMOTE_PATH}...")
    subprocess.run(["scp", "-O", "-o", "HostKeyAlgorithms=+ssh-rsa", 
                    filename, f"{SSH_USER}@{LASER_IP}:{REMOTE_PATH}"], check=True)
                    
    print("READY TO GO: Make sure the door is closed and safety goggles are on!")
    for i in range(number_of_passes):
        run_engrave_100mm()
        time.sleep(5)
        while get_laser_status() == 2:
            time.sleep(5)
