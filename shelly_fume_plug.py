import requests


SHELLY_IP = "192.168.0.26"

def set_plug_state(on=True):
    state = "on" if on else "off"

    url = f"http://{SHELLY_IP}/rpc/Switch.Set?id=0&on={str(on).lower()}"
    response = requests.get(url)
    return response.json()

# Turn it on
print(set_plug_state(False))
