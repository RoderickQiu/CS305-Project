import json

HELP = (
    "Create         : create an conference\n"
    "Join [conf_id ]: join a conference with conference ID\n"
    "Quit           : quit an on-going conference\n"
    "Cancel         : cancel your on-going conference (only the manager)\n"
    "Send [message] : send a text message to all participants\n"
    "Help           : show this help message\n"
)

SERVER_IP = "127.0.0.1"
with open("data.json", "r") as f:
    data = json.load(f)
    MAIN_SERVER_PORT = data["server"]["host"]
    CLIENT_TCP_PORT = data["client"]["port"]
TIMEOUT_SERVER = 5
DGRAM_SIZE = 1500  # UDP
LOG_INTERVAL = 2


CHUNK = 1024
CHANNELS = 1  # Channels for audio capture
RATE = 44100  # Sampling rate for audio capture

camera_width, camera_height = 480, 480  # resolution for camera capture


def save_server_port(port):
    with open("data.json", "r") as f:
        data = json.load(f)
        data["server"]["port"] = port
    with open("data.json", "w") as f:
        json.dump(data, f)


def sync_server_host():
    with open("data.json", "r") as f:
        data = json.load(f)
        data["server"]["host"] = data["server"]["port"]
    with open("data.json", "w") as f:
        json.dump(data, f)
    return data["server"]["host"]


def save_client_port(port):
    with open("data.json", "r") as f:
        data = json.load(f)
        data["client"]["port"] = port
    with open("data.json", "w") as f:
        json.dump(data, f)
