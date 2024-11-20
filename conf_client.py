from util import *
import socket
from typing import Dict
import json
import threading


class ConferenceClient:
    def __init__(self, HOST: str, PORT: str):
        # sync client
        self.data_types = [
            "screen",
            "camera",
            "audio",
            "text",
        ]  # example data types in a video conference
        self.conference_id = -1
        self.is_working = True
        self.HOST = HOST  # server addr
        self.on_meeting = False  # status
        self.conns = (
            None  # you may need to maintain multiple conns for a single conference
        )
        self.support_data_types = []  # for some types of data
        self.share_data = {}

        self.conference_info = (
            None  # you may need to save and update some conference_info regularly
        )
        self.recv_data = None  # you may need to save received streamd data from other clients in conference
        self.sockets: Dict[str, socket.socket] = {}
        self.data_serve_ports = {}
        self.udp_addrs = {}
        self.server_host = HOST
        self.udp_addr_count = CLIENT_TCP_PORT

        self.sockets["main"] = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sockets["main"].connect((HOST, PORT))

    def create_sockets(self):
        self.sockets["confe"] = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        for data_type in self.data_types:
            self.sockets[data_type] = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    def create_conference(self):
        """
        create a conference: send create-conference request to server and obtain necessary data to
        """
        print("Creating a conference")
        recv_lines = []
        conference_id = -1
        self.create_sockets()
        msg = "create"
        self.sockets["main"].sendall(msg.encode())
        self.recv_data = self.sockets["main"].recv(CHUNK).decode()
        self.output_data(self.sockets["main"])

        recv_lines = self.recv_data.splitlines()
        if recv_lines[-1] == "204":
            self.configure_cancelled()  # TODO this and similar code: workaround, might have a better way
            return
        elif not recv_lines[-1] == "200":
            print(f"An error occurs, please input again!")
            return

        conference_id = int(recv_lines[0])

        self.join_conference(conference_id)

    def join_conference(self, conference_id: int):
        """
        join a conference: send join-conference request with given conference_id, and obtain necessary data to
        """
        if self.on_meeting:
            print("Already joined a meeting")
            return

        print(f"Joining conference {conference_id}")
        self.create_sockets()

        msg = f"join {conference_id}"
        self.sockets["main"].sendall(msg.encode())
        self.recv_data = self.sockets["main"].recv(CHUNK).decode()
        self.output_data(self.sockets["main"])

        recv_lines = self.recv_data.splitlines()
        if recv_lines[-1] == "204":
            self.configure_cancelled()
            return
        elif not recv_lines[-1] == "200":
            print(f"An error occurs, please input again!")
            return

        self.on_meeting = True
        self.conference_id = conference_id

        recv_dict: Dict[str] = json.loads(recv_lines[0])
        self.sockets["confe"].connect((self.HOST, recv_dict["conf_serve_port"]))
        self.data_serve_ports = recv_dict["data_serve_ports"]
        self.server_host = recv_dict["host"]
        for data_type in self.data_types:
            self.sockets[data_type].bind((self.HOST, self.udp_addr_count))
            self.udp_addrs[data_type] = (self.HOST, self.udp_addr_count)
            self.udp_addr_count += 1

        save_client_port(self.udp_addr_count)
        self.start_conference(conference_id)

    def quit_conference(self):
        """
        quit your on-going conference
        """
        self.on_meeting = False

        msg = f"quit"
        self.sockets["main"].sendall(msg.encode())
        self.recv_data = self.sockets["main"].recv(CHUNK).decode()
        self.output_data(self.sockets["main"])

        recv_lines = self.recv_data.splitlines()
        print(recv_lines)
        if recv_lines[-1] == "204":
            self.configure_cancelled()
            return
        elif not recv_lines[-1] == "200":
            print(f"An error occurs, please input again!")
            return

        self.configure_cancelled()

    def configure_cancelled(self):
        try:
            self.sockets["confe"].close()
            for data_type in self.data_types:
                if self.sockets[data_type] is not None:
                    self.sockets[data_type].close()
            del self.sockets["confe"]
            for data_type in self.data_types:
                del self.sockets[data_type]

            self.on_meeting = False
            self.conference_id = -1
        except:
            return

    def cancel_conference(self):
        """
        cancel your on-going conference (when you are the conference manager): ask server to close all clients
        """
        self.on_meeting = False

        msg = f"cancel"
        self.sockets["main"].sendall(msg.encode())
        self.recv_data = self.sockets["main"].recv(CHUNK).decode()
        self.output_data(self.sockets["main"])

        recv_lines = self.recv_data.splitlines()
        print(recv_lines)
        if recv_lines[-1] == "204":
            self.configure_cancelled()
            return
        elif not recv_lines[-1] == "200":
            print(f"An error occurs, please input again!")
            return

        self.on_meeting = False
        self.conference_id = -1

    def keep_share(
        self, data_type, send_conn, capture_function, compress=None, fps_or_frequency=30
    ):
        """
        running task: keep sharing (capture and send) certain type of data from server or clients (P2P)
        you can create different functions for sharing various kinds of data
        """
        pass

    def share_switch(self, data_type):
        """
        switch for sharing certain type of data (screen, camera, audio, etc.)
        """
        pass

    def keep_recv(self, recv_conn, data_type, decompress=None):
        """
        running task: keep receiving certain type of data (save or output)
        you can create other functions for receiving various kinds of data
        """

    def output_data(self, socket: socket.socket):
        """
        running task: output received stream data
        """
        (host, port) = socket.getpeername()
        print(f"{host}:{port}\n{self.recv_data}")

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
        print(recv_lines)
        if recv_lines[-1] == "204":
            self.configure_cancelled()
            return
        elif not recv_lines[-1] == "200":
            print(f"An error occurs, please input again!")
            return

        if not self.on_meeting:  # 检查是否已加入会议
            print("[Error]: Not in a conference.")
            return
        threading.Thread(target=self.recv_text_messages, daemon=True).start()

        print(f"[Info]: Conference {self.conference_id} started.")

    def send_text_message(self, message: str):
        """
        Send a text message to the server for broadcasting to other clients.
        """
        if not self.on_meeting:
            print("[Warn]: You must join a conference to send messages.")
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
                print(f"[Error]: Failed to receive messages. {e}")

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
                input(f'({status}) Please enter a operation (enter "?" to help): ')
                .strip()
                .lower()
            )
            fields = cmd_input.split(maxsplit=1)
            if len(fields) == 1:
                if cmd_input in ("?", "？"):
                    print(HELP)
                elif cmd_input == "create":
                    self.create_conference()
                elif cmd_input == "quit":
                    self.quit_conference()
                elif cmd_input == "cancel":
                    self.cancel_conference()
                else:
                    recognized = False
            elif len(fields) == 2:
                if fields[0] == "join":
                    input_conf_id = fields[1]
                    if input_conf_id.isdigit():
                        self.join_conference(int(input_conf_id))
                    else:
                        print("[Warn]: Input conference ID must be in digital form")
                elif fields[0] == "switch":
                    data_type = fields[1]
                    if data_type in self.share_data.keys():
                        self.share_switch(data_type)
                elif fields[0] == "send":
                    message = fields[1]
                    self.send_text_message(message)
                else:
                    recognized = False
            else:
                recognized = False

            if not recognized:
                print(f"[Warn]: Unrecognized cmd_input {cmd_input}")


if __name__ == "__main__":
    client1 = ConferenceClient(SERVER_IP, MAIN_SERVER_PORT)
    client1.start()
