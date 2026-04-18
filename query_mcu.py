import requests
import hashlib
import json

LASER_IP = "192.168.0.70"
PORT = "8080"
ENDPOINT = f"http://{LASER_IP}:{PORT}/test/cmd/mcu"

def query_mcu(gcode_command):
    """
    Sends a query G-code to the MCU and returns the parsed data string.
    """
    # Ensure command ends with newline
    payload = f"{gcode_command}\n"
    
    # Calculate MD5 hash (Uppercase)
    md5_hash = hashlib.md5(payload.encode('utf-8')).hexdigest().upper()
    
    # Parameters for the URL
    params = {"md5": md5_hash}
    
    try:
        print(f"[*] Querying: {gcode_command.strip()}...")
        response = requests.post(ENDPOINT, params=params, data=payload.encode('utf-8'))
        
        if response.status_code == 200:
            res_json = response.json()
            return res_json.get("data", "No data returned")
        else:
            return f"Error: HTTP {response.status_code}"
            
    except Exception as e:
        return f"Connection Failed: {str(e)}"

if __name__ == "__main__":
    
    # Expected: "M27 Z0.000 X0.000 U0.000 B0.000"
    pos = query_mcu("M27")
    print(f"[+] Current Position: {pos}")
    
    safety = query_mcu("M22")
    print(f"[+] Safety/Limit Status maybe?: {safety}")
    
    # Expected: "M29S3Q0"
    state = query_mcu("M29")
    print(f"[+] Machine State maybe?: {state}")
    

