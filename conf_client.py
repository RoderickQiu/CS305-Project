import ast
import os
import traceback
import urllib
from util import *
import socket
from typing import Dict
import json
import threading
import cv2
import struct
import time
from flask import Flask
from werkzeug.serving import make_server
import logging
import random
import pyaudio

# 生成一个8位的随机数字
# flask server thread
app = Flask(__name__)
werkzeug_logger = logging.getLogger("werkzeug")
werkzeug_logger.setLevel(logging.ERROR)
video_images = dict()
last_receive_time = dict()

# 初始化 PyAudio
p = pyaudio.PyAudio()


def get_video_view_link(flask_url):
    file_path = "video.html"
    absolute_path = os.path.abspath(file_path)
    file_url = f"file://{absolute_path}"
    query_params = urllib.parse.urlencode({"url": "http://" + flask_url})
    full_url = f"{file_url}?{query_params}"
    print(f"Copy and open {full_url} to see videos")


@app.route("/")
def print_videos():
    result = '<style>.grid-container {display: grid;gap: 10px;grid-template-columns: repeat(2, 1fr);}</style><div class="grid-container">'
    for img_name in video_images:
        if time.time() - last_receive_time[img_name] <= 1:
            result += f'<div class="grid-item"><div>{str(img_name)}</div><div><img src="{str(video_images[img_name])}"/></div></div>'
    result += "</div>"
    return result


class FlaskServer:
    def __init__(self, app, host, port):
        self.host = host
        self.port = port
        self.server = make_server(host, port, app)
        self.ctx = app.app_context()
        self.ctx.push()

    def start(self):
        print(f"And running a flask server at {self.host}:{self.port}")
        self.server.serve_forever()

    def shutdown(self):
        self.server.shutdown()


flask_server: FlaskServer | None = None
flask_thread: threading.Thread | None = None


def start_flask(ip, port):
    global flask_server
    flask_server = FlaskServer(app, ip, port)
    flask_server.start()


class ConferenceClient:
    def __init__(self, HOST: str, CLIENT_IP: str, PORT: int):
        # sync client
        self.data_types = [
            "screen",
            "camera",
            "audio",
            "text",
        ]  # example data types in a video conference
        self.conference_id = -1
        self.is_working = True
        self.id = random.randint(10000000, 99999999)

        self.HOST = HOST  # server addr
        self.CLIENT_IP = CLIENT_IP  # my own addr
        self.PORT = PORT  # main server port
        self.on_meeting = False  # status
        self.on_camera = False
        self.on_audio = False
        self.on_screen = False
        self.was_on_record = [False, False]
        self.conns = (
            None  # you may need to maintain multiple conns for a single conference
        )
        self.cap = None
        self.support_data_types = []  # for some types of data
        self.share_data = {}
        self.isp2p = False
        self.p2p_no_peer = True

        self.conference_info = (
            None  # you may need to save and update some conference_info regularly
        )
        self.recv_data = None  # you may need to save received streamd data from other clients in conference
        self.sockets: Dict[str, socket.socket] = {}
        self.data_serve_ports = {}
        self.udp_addrs = {}
        self.server_host = HOST
        self.udp_addr_count = get_client_port()

        self.sockets["main"] = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sockets["main"].connect((HOST, PORT))

    def create_sockets(self):
        self.sockets["confe"] = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        for data_type in self.data_types:
            self.sockets[data_type] = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    def create_conference(self, mode, extra_options=None):
        """
        create a conference: send create-conference request to server and obtain necessary data to
        """
        if extra_options is None:
            extra_options = {}
        print("[Info]: Creating a conference")
        recv_lines = []
        conference_id = -1
        self.create_sockets()
        msg = f"create {mode} {json.dumps(extra_options).replace(' ','')}"
        self.sockets["main"].sendall(msg.encode())
        self.recv_data = self.sockets["main"].recv(CHUNK).decode()
        self.output_data(self.sockets["main"])

        recv_lines = self.recv_data.splitlines()
        if not recv_lines[-1] == "200":
            print(f"[Error]: An error occurs, please input again!")
            return

        conference_id = int(recv_lines[0])

        self.join_conference(conference_id)

    def join_conference(self, conference_id: int, just_recreated=False):
        """
        join a conference: send join-conference request with given conference_id, and obtain necessary data to
        """
        if self.on_meeting:
            print("[Warn]: Already joined a meeting")
            return

        print(f"[Info]: Joining conference {conference_id}")
        self.create_sockets()

        msg = f"join {conference_id}"
        self.sockets["main"].sendall(msg.encode())
        self.recv_data = self.sockets["main"].recv(CHUNK).decode()
        self.output_data(self.sockets["main"])

        recv_lines = self.recv_data.splitlines()
        if not recv_lines[-1] == "200":
            print(f"[Error]: An error occurs, please input again!")
            return

        recv_dict: Dict[str] = json.loads(recv_lines[0])

        if "should_recreate" in recv_dict:
            if recv_dict["should_recreate"] == "True":
                print(f"Conference change to use server mode, switching...")
                self.create_conference(
                    "server",
                    {
                        "should_recreate": "True",
                        "conference_id": recv_dict["conference_id"],
                    },
                )
                return

        self.on_meeting = True
        self.conference_id = conference_id

        self.udp_addr_count = get_client_port() + 10 * random.randint(3, 109)
        self.sockets["confe"].bind((self.CLIENT_IP, self.udp_addr_count))
        self.udp_addrs["confe"] = (self.CLIENT_IP, self.udp_addr_count)
        self.udp_addr_count += 1

        for data_type in self.data_types:
            self.sockets[data_type].bind((self.CLIENT_IP, self.udp_addr_count))
            self.udp_addrs[data_type] = (self.CLIENT_IP, self.udp_addr_count)
            self.udp_addr_count += 1

        save_client_port(self.udp_addr_count)
        threading.Thread(target=self.recv_commands, daemon=True).start()

        if (
            recv_dict["isp2p"] == "False" or recv_dict["member_id"] == 1
        ):  # server or second member
            self.data_serve_ports = recv_dict["data_serve_ports"]
            self.server_host = recv_dict["host"]

            if just_recreated:
                if self.was_on_record[0]:
                    self.on_camera = True
                    self.send_video()
                if self.was_on_record[1]:
                    self.send_multimedia_signal("open audio")
                    self.on_audio = True
                    self.send_audio()

            if recv_dict["member_id"] == 1:
                self.isp2p = True
                self.p2p_no_peer = False
                msg = f"p2p info {self.conference_id} 1 {self.CLIENT_IP} {str(self.udp_addrs).replace(' ', '')}"
                self.sockets["main"].sendall(msg.encode())
                self.recv_data = self.sockets["main"].recv(CHUNK).decode()
                self.output_data(self.sockets["main"])

                recv_lines = self.recv_data.splitlines()
                if not recv_lines[-1] == "200":
                    print(f"[Error]: An error occurs, please input again!")
                    return

                threading.Thread(target=self.recv_text_messages, daemon=True).start()
                threading.Thread(target=self.recv_video, daemon=True).start()
                threading.Thread(target=self.recv_audio, daemon=True).start()

                print(f"[Info]: Conference {self.conference_id} started.")
            else:
                self.start_conference(conference_id)
        elif recv_dict["member_id"] == 0:  # is first member
            self.isp2p = True
            self.p2p_no_peer = True
            msg = f"p2p info {self.conference_id} 0 {self.CLIENT_IP} {str(self.udp_addrs).replace(' ', '')}"
            self.sockets["main"].sendall(msg.encode())
            self.recv_data = self.sockets["main"].recv(CHUNK).decode()
            self.output_data(self.sockets["main"])

            recv_lines = self.recv_data.splitlines()
            if not recv_lines[-1] == "200":
                print(f"[Error]: An error occurs, please input again!")
                return

    def quit_conference(self):
        """
        quit your on-going conference
        """
        if not self.on_meeting:
            print("[Warn]: Not in a conference.")
            return

        self.on_meeting = False
        self.on_audio = False

        msg = f"quit"
        self.sockets["main"].sendall(msg.encode())
        self.recv_data = self.sockets["main"].recv(CHUNK).decode()
        self.output_data(self.sockets["main"])

        recv_lines = self.recv_data.splitlines()
        print(f"[info]:{recv_lines}\n!!!!!")
        if not recv_lines[-1] == "200":
            print(f"[Error]: An error occurs, please input again!")
            return

        self.configure_cancelled()

    def configure_cancelled(self, new_conf_id=-1):
        try:
            try:
                self.on_camera = False
                if self.cap is not None:
                    self.cap.release()
            except:
                print()

            self.sockets["confe"].close()
            for data_type in self.data_types:
                if self.sockets[data_type] is not None:
                    self.sockets[data_type].close()
            del self.sockets["confe"]
            for data_type in self.data_types:
                del self.sockets[data_type]

            self.on_meeting = False
            self.conference_id = -1

            if new_conf_id > -1:  # join the newly recreated conf in server mode
                self.join_conference(new_conf_id, just_recreated=True)
        except:
            return

    def perform_exit(self):
        if self.on_meeting:
            self.quit_conference()

        msg = f"exit"
        self.sockets["main"].sendall(msg.encode())
        self.recv_data = self.sockets["main"].recv(CHUNK).decode()
        self.output_data(self.sockets["main"])

        self.is_working = False
        self.sockets["main"].close()

        if flask_server is not None and flask_thread is not None:
            flask_server.shutdown()
            flask_thread.join()

        exit(0)

    def cancel_conference(self):
        """
        cancel your on-going conference (when you are the conference manager): ask server to close all clients
        """
        if not self.on_meeting:
            print("[Warn]: Not in a conference.")
            return

        msg = f"cancel"
        self.on_meeting = False
        self.sockets["main"].sendall(msg.encode())
        self.recv_data = self.sockets["main"].recv(CHUNK).decode()
        self.output_data(self.sockets["main"])

        recv_lines = self.recv_data.splitlines()
        if recv_lines is None or len(recv_lines)==0:
            print(f"[Warn]:  Only the manager can cancel the conference")
            self.on_meeting = True
            return
        if recv_lines[-1] == "403":
            print(f"[Warn]: Only the manager can cancel the conference.")
            self.on_meeting = True
            return
        elif not recv_lines[-1] == "200":
            print(f"[Error]: An error occurs, please input again!")
            self.on_meeting = True
            return
        else:
            self.configure_cancelled()
            self.on_camera = False
            self.on_meeting = False
            self.conference_id = -1

    def output_data(self, socket: socket.socket):
        """
        running task: output received stream data
        """
        # (host, port) = socket.getpeername()
        # print(f"{host}:{port}\n{self.recv_data}")

    def start_conference(self, conference_id: int):
        """
        init conns when create or join a conference with necessary conference_info
        and
        start necessary running task for conference
        """
        msg = f"link {conference_id} {str(self.udp_addrs).replace(' ', '')}"
        self.sockets["main"].sendall(msg.encode())
        self.recv_data = self.sockets["main"].recv(CHUNK).decode()
        self.output_data(self.sockets["main"])

        recv_lines = self.recv_data.splitlines()
        if not recv_lines[-1] == "200":
            print(f"[Error]: An error occurs, please input again!")
            return

        if not self.on_meeting:  # 检查是否已加入会议
            print("[Error]: Not in a conference.")
            return
        threading.Thread(target=self.recv_text_messages, daemon=True).start()
        threading.Thread(target=self.recv_video, daemon=True).start()
        threading.Thread(target=self.recv_audio, daemon=True).start()

        print(f"[Info]: Conference {self.conference_id} started.")

    def list_conferences(self):
        """
        init conns when create or join a conference with necessary conference_info
        and
        start necessary running task for conference
        """
        msg = f"list"
        self.sockets["main"].sendall(msg.encode())
        self.recv_data = self.sockets["main"].recv(CHUNK).decode()
        self.output_data(self.sockets["main"])

        recv_lines = self.recv_data.splitlines()
        if not recv_lines[-1] == "200":
            print(f"[Error]: An error occurs, please input again!")
            return

        print(f"[Info]: List of ongoing conferences: {recv_lines[0]}")

    def send_text_message(self, message: str):
        """
        Send a text message to the server for broadcasting to other clients.
        """
        if not self.on_meeting:
            print("[Warn]: You must join a conference to send messages.")
            return

        if self.p2p_no_peer and self.isp2p:
            print("[Warn]: No peer yet in p2p mode.")
            return

        try:
            msg = f"text: {message}"
            self.sockets["text"].sendto(
                msg.encode(), (self.server_host, self.data_serve_ports["text"])
            )
            print(f"[Info]: Message sent: {message}")
        except KeyError:
            print(f"[Error]: Text socket is not initialized.")
        except Exception as e:
            if self.on_meeting:
                print(f"[Error]: Failed to send message. {e}")
                traceback.print_exc()

    def recv_text_messages(self):
        """
        Continuously receive text messages from the server.
        """
        try:
            while self.on_meeting:
                data = self.sockets["text"].recv(CHUNK).decode()  # Blocking receive
                if data:
                    print(f"[Message]: {data}")
        except Exception as e:
            if self.on_meeting:
                traceback.print_exc()
                print(f"[Error]: Failed to receive messages. {e}")

    def recv_commands(self):
        """
        Continuously receive commands from the server.
        """
        try:
            while self.on_meeting:
                data = self.sockets["confe"].recv(CHUNK).decode()  # Blocking receive
                if data:
                    split_data = data.split(" ")
                    if (
                        CANCEL_MSG in data or SHOULD_RECREATE_MSG in data
                    ):  # Check if the conference has been cancelled
                        print(
                            f"[Info]: {CANCEL_MSG if CANCEL_MSG in data else SHOULD_RECREATE_MSG}"
                        )
                        new_conf_id = int(split_data[-1])
                        self.on_meeting = False
                        self.configure_cancelled(new_conf_id=new_conf_id)
                        break
                    elif (
                        P2P_ESTAB_MSG in data
                    ):  # The first p2p host establish conn with the second
                        self.p2p_no_peer = False
                        print(
                            f"[Info]: P2P established with {split_data[2]}"
                        )  # "P2P Established {ip} {ports}"
                        self.server_host = split_data[2]
                        self.data_serve_ports = ast.literal_eval(split_data[3])

                        threading.Thread(
                            target=self.recv_text_messages, daemon=True
                        ).start()
                        threading.Thread(target=self.recv_video, daemon=True).start()
                        threading.Thread(target=self.recv_audio, daemon=True).start()

                        print(f"[Info]: Conference {self.conference_id} started.")
                    else:
                        print(f"[Message]: {data}")
        except Exception as e:
            if self.on_meeting:
                traceback.print_exc()
                print(f"[Error]: Failed to receive messages. {e}")

    def send_audio(self):
        if not self.on_meeting:
            print("[Warn]: You must join a conference to share audios!")
            return

        def audio_stream():
            MAX_SIZE = 65535
            while self.on_audio:
                data = streamin.read(1024)  # 从麦克风获取音频数据
                # print("收集完毕")
                if len(data) > MAX_SIZE:
                    # print("数据过大，进行分块发送...")
                    chunks = [
                        data[i : i + MAX_SIZE] for i in range(0, len(data), MAX_SIZE)
                    ]
                    for chunk in chunks:
                        self.sockets["audio"].sendto(
                            chunk, (self.server_host, self.data_serve_ports["audio"])
                        )
                else:
                    if "audio" in self.sockets:
                        self.sockets["audio"].sendto(
                            data, (self.server_host, self.data_serve_ports["audio"])
                        )  # 发送数据给服务器

                time.sleep(0.01)

        threading.Thread(target=audio_stream, daemon=True).start()

    def recv_audio(self):
        while self.on_meeting:
            try:
                data = self.sockets["audio"].recv(65535)
                # print("接受到audio")
                streamout.write(data)
            except:
                print("[Warn] Empty audio")

    def send_video(self):
        if not self.on_meeting:
            print("[Warn]: You must join a conference to share videos!")
            return
        if not self.on_camera:
            print("[Warn]: You must open the camera to show your image!")
            return
        if self.p2p_no_peer and self.isp2p:
            print("[Warn]: No peer yet in p2p mode.")
            return

        def video_stream():
            self.cap = cv2.VideoCapture(0)
            CHUNK_SIZE = 1024
            encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), 60]

            try:
                while self.cap.isOpened() and self.on_camera:
                    open, img = self.cap.read()
                    img_screen = ImageGrab.grab()
                    img_np = np.array(img_screen)
                    img_np = cv2.cvtColor(img_np, cv2.COLOR_RGB2BGR)
                    img_flipped = cv2.flip(img, 1)
                    video_height, video_width, _ = img_np.shape

                    cam_height, cam_width, _ = img_flipped.shape
                    # 480*640 camera 1080*1920
                    x_offset = video_width - cam_width  # 横向偏移
                    y_offset = 0
                    img_np[
                        y_offset : y_offset + cam_height,
                        x_offset : x_offset + cam_width,
                    ] = img_flipped

                    if not open:
                        break
                    img_resized = cv2.resize(img_np, (480, 320))

                    result, imgencode = cv2.imencode(".jpg", img_resized, encode_param)
                    id_num = self.id.to_bytes(4, byteorder="big")

                    frame_data = imgencode.tobytes()
                    total_size = len(frame_data)  # 获取总大小
                    combined_data = id_num + frame_data

                    self.sockets["camera"].sendto(
                        combined_data,
                        (self.server_host, self.data_serve_ports["camera"]),
                    )
                    time.sleep(0.01)

                    """time.sleep(0.01)
                    
                    # 转换为 4 字节大端序
                    
                    self.sockets["camera"].sendto(
                        struct.pack("!L", total_size),
                        (self.server_host, self.data_serve_ports["camera"]),
                    )
                    total_chunks = (total_size + CHUNK_SIZE - 1) // CHUNK_SIZE
                    for i in range(total_chunks):
                        start = i * CHUNK_SIZE
                        end = start + CHUNK_SIZE
                        chunk_data = (
                            i.to_bytes(2, "big")  # 分块索引（2字节）
                            + total_chunks.to_bytes(2, "big")  # 总分块数（2字节）
                            + frame_data[
                                i * CHUNK_SIZE : (i + 1) * CHUNK_SIZE
                            ]  # 分块内容
                        )
                        # 发送数据包
                        self.sockets["camera"].sendto(
                            chunk_data,
                            (self.server_host, self.data_serve_ports["camera"]),
                        )
                        time.sleep(0.007)"""
            finally:
                self.cap.release()

        threading.Thread(target=video_stream, daemon=True).start()

    def recv_video(self):
        try:
            CHUNK_SIZE = 1024  # 分块大小
            while self.on_meeting:
                packet, _ = self.sockets["camera"].recvfrom(60000)
                id_num = int.from_bytes(packet[:4], byteorder="big")
                frame_data = packet[4:]
                nparr = np.frombuffer(frame_data, dtype=np.uint8)
                if nparr is not None:
                    video_images[str(id_num)] = get_base64_image(nparr)
                    last_receive_time[str(id_num)] = time.time()

                """
               
                # print(id_num)
                data, _ = self.sockets["camera"].recvfrom(4)
                frame_size = struct.unpack("!L", data)[0]
                total_chunks = (frame_size + CHUNK_SIZE - 1) // CHUNK_SIZE
                buffer = [None] * total_chunks  # 初始化缓存列表

                for _ in range(total_chunks):
                    chunk_data, _ = self.sockets["camera"].recvfrom(CHUNK_SIZE + 4)
                    chunk_index = int.from_bytes(chunk_data[:2], "big")
                    total_chunks_received = int.from_bytes(chunk_data[2:4], "big")

                    if total_chunks_received != total_chunks:
                        continue  # 分块数量不一致，丢弃

                    buffer[chunk_index] = chunk_data[4:]  # 存储分块数据

                if None not in buffer:
                    frame_data = b"".join(buffer)
                    nparr = np.frombuffer(frame_data, dtype=np.uint8)
                    # img_decoded = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

                    if nparr is not None:
                        video_images[str(id_num)] = get_base64_image(nparr)
                        # cv2.imshow("Meeting", img_decoded)
                        # if cv2.waitKey(1) & 0xFF == ord("q"):
                        #     break
                else:
                    print("Failed to decode the image")"""

        except Exception as e:
            if self.on_meeting:
                print(f"[Error]: Failed to receive others video. {e}")

    def send_multimedia_signal(self, word):
        self.sockets["main"].sendall(word.encode())
        self.recv_data = self.sockets["main"].recv(CHUNK).decode()
        self.output_data(self.sockets["main"])

        recv_lines = self.recv_data.splitlines()
        if not recv_lines[-1] == "200":
            print(f"[Error]: An error occurs, please input again!")

    def start(self):
        """
        execute functions based on the command line input
        """
        while True:
            if not self.on_meeting:
                status = "Free"
            else:
                status = f"OnMeeting-{self.conference_id}"

            recognized = True
            cmd_input = (
                input(f"({status}) Please enter a operation (enter '?' to help): ")
                .strip()
                .lower()
            )
            fields = cmd_input.split(maxsplit=1)
            if len(fields) == 0:
                print("[Warn] You must input something. Aborting...")
            elif len(fields) == 1:
                if cmd_input in ("?", "？", "help"):
                    print(HELP)
                elif cmd_input == "create":
                    self.create_conference("p2p")  # p2p as the default mode
                elif cmd_input == "quit":
                    self.quit_conference()
                elif cmd_input == "cancel":
                    self.cancel_conference()
                elif cmd_input == "exit":
                    self.perform_exit()
                elif cmd_input == "list":
                    self.list_conferences()

                else:
                    recognized = False
            elif len(fields) == 2:
                if fields[0] == "join":
                    input_conf_id = fields[1]
                    if input_conf_id.isdigit():
                        self.join_conference(int(input_conf_id))
                    else:
                        print("[Warn]: Input conference ID must be in digital form")
                elif fields[0] == "create":
                    mode = fields[1]
                    if mode in ("server", "p2p"):
                        self.create_conference(mode)
                    else:
                        print("[Warn]: Mode must be 'server' or 'p2p'")
                elif fields[0] == "send":
                    message = fields[1]
                    self.send_text_message(message)
                elif fields[0] == "open":
                    if fields[1] == "camera":
                        self.on_camera = True
                        self.was_on_record[0] = True
                        self.send_video()
                    elif fields[1] == "audio":
                        self.send_multimedia_signal("open audio")
                        self.was_on_record[1] = True
                        self.on_audio = True
                        self.send_audio()
                    elif fields[1] == "screen":
                        self.on_screen = True
                elif fields[0] == "close":
                    if fields[1] == "camera":
                        self.on_camera = False
                        self.was_on_record[0] = False
                        try:
                            if self.cap is not None:
                                self.cap.release()
                        except:
                            print()
                    elif fields[1] == "audio":
                        self.send_multimedia_signal("close audio")
                        self.on_audio = False
                        self.was_on_record[1] = False
                else:
                    recognized = False
            else:
                recognized = False

            if not recognized:
                print(f"[Warn]: Unrecognized cmd_input {cmd_input}")


if __name__ == "__main__":
    flask_port = get_client_port()
    flask_thread = threading.Thread(target=start_flask, args=(CLIENT_IP, flask_port))
    flask_thread.start()
    get_video_view_link(CLIENT_IP + ":" + str(flask_port))
    save_client_port(flask_port + 1)

    print("Please input the server's ip and port, e.g. 127.0.0.1:8888...")
    input_addr = input().strip().split(":")
    input_ip, input_port = input_addr[0], input_addr[1]
    print(f"Connecting to {input_ip}, port is {input_port}")
    client1 = ConferenceClient(input_ip, CLIENT_IP, int(input_port))
    client1.start()
