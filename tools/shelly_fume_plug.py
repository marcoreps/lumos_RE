import requests
import time

# Configurations
LASER_URL = "http://192.168.0.70:8080/process/status"
SHELLY_IP = "192.168.0.26"
POST_RUN_EXTRACTION_TIME = 10  # Seconds to run after status 2 ends

def set_plug_state(state):
    try:
        url = f"http://{SHELLY_IP}/rpc/Switch.Set?id=0&on={str(state).lower()}"
        requests.get(url, timeout=5)
    except Exception as e:
        print(f"Error communicating with Shelly: {e}")

def get_laser_status():
    try:
        response = requests.get(LASER_URL, timeout=5)
        data = response.json()
        return data.get("status")
    except Exception as e:
        print(f"Error communicating with Lazer: {e}")
        return None

def main():
    overrun_counter = 0
    plug_is_on = False

    print("Fume extractor automation initated. Spamming the laser ...")

    while True:
        status = get_laser_status()
        
        if status == 2:
            overrun_counter = POST_RUN_EXTRACTION_TIME
        elif overrun_counter > 0:
            overrun_counter -= 1
        
        on = (overrun_counter > 0)
        set_plug_state(on)

        time.sleep(1)

if __name__ == "__main__":
    main()
