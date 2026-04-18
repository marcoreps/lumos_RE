import hashlib
import requests
import subprocess
import json
import time

LASER_IP = "192.168.0.70"
SSH_USER = "mbtc"


def set_interior_light(led_id, level, status=1):
    url = f"http://192.168.0.70:8080/device/light/status"
    # The machine wants this JSON
    payload = {
        "led": led_id,
        "status": status,
        "level": level
    }

    response = requests.post(url, json=payload)
    return response.status_code            


if __name__ == "__main__":
    set_interior_light(8, 0)
    set_interior_light(9, 0)
