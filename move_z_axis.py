import requests
import hashlib

IP = "192.168.0.70:8080"

def send_gcode(gcode_str):
    payload = f"{gcode_str}\n"
    md5_hash = hashlib.md5(payload.encode('utf-8')).hexdigest().upper()
    url = f"http://{IP}/test/cmd/mcu?md5={md5_hash}"
    print(f"[*] Sending: {gcode_str}")
    print(f"[*] Calculated MD5: {md5_hash}")
    response = requests.post(url, data=payload.encode('utf-8'))
    print(f"[+] MCU Response: {response.text}")

if __name__ == "__main__":
    send_gcode("G0Z70")
