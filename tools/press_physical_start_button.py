import hashlib
import requests
import subprocess
import time

LASER_IP = "192.168.0.70"
SSH_USER = "mbtc"

def run_engrave():
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
    run_engrave()
