import json

HELP = (
    "Create         : create an conference\n"
    "List           : list all available conferences\n"
    "Join [conf_id ]: join a conference with conference ID\n"
    "Quit           : quit an on-going conference\n"
    "Cancel         : cancel your on-going conference (only the manager)\n"
    "Send [message] : send a text message to all participants\n"
    "Exit           : exit the program\n"
    "Help           : show this help message\n"
    "Open Camera:   : open camera\n"
    "Close Camera:  : close camera\n"
    "Open Mic       : open microphone\n"
    "Close Mic      : close microphone\n"
)
CANCEL_MSG = "The conference has been canceled by the manager"

SERVER_IP = "10.27.107.219"
CLIENT_IP = "10.32.52.104"
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


def get_server_port():
    with open("data.json", "r") as f:
        data = json.load(f)
    return data["server"]["host"]


def get_client_port():
    with open("data.json", "r") as f:
        data = json.load(f)
    return data["client"]["port"]
