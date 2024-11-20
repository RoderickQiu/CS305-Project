import ast
import asyncio
import threading
import time
import traceback

from util import *
import socket


class ConferenceServer:
    def __init__(
        self,
    ):
        # async server
        self.running = False
        self.conference_id = None  # conference_id for distinguish difference conference
        self.host_info = ""  # to distinguish if the client created the conference
        self.conf_serve_ports = {}
        self.data_serve_ports = {}
        self.data_types = [
            "screen",
            "camera",
            "audio",
            "text",
        ]  # example data types in a video conference
        self.clients_info = []
        self.clients_udp_addrs = {}
        self.client_conns = {}
        self.mode = "Client-Server"  # or 'P2P' if you want to support peer-to-peer conference mode

    def handle_data(self, conn_socket, from_info, data_type):
        """
        running task: receive sharing stream data from a client and decide how to forward them to the rest clients
        """
        from_info = str(from_info)
        try:
            while self.running:
                data, addr = conn_socket.recvfrom(CHUNK)
                if not data:
                    break
                message = data.decode().strip()
                if data_type == "text":
                    timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
                    formatted_message = f"[{timestamp}] {from_info}: {message}"
                    print(
                        f"Received data from addr {str(addr)} with type {data_type}: {message}"
                    )

                    # Forward message to all other clients
                    self.broadcast_message(formatted_message, from_info, data_type)
        except asyncio.CancelledError:
            pass

    def broadcast_message(self, message, from_info, data_type):
        for client_id, socket_list in self.client_conns.items():
            if client_id != from_info:
                port = self.data_serve_ports[client_id][data_type]
                writer: socket.socket = self.client_conns[client_id][port]
                addr = self.clients_udp_addrs[client_id][data_type]
                writer.sendto(message.encode(), addr)

    async def log(self):
        while self.running:
            print("Something about server status")
            await asyncio.sleep(LOG_INTERVAL)

    def cancel_conference(self):
        """
        handle cancel conference request: disconnect all connections to cancel the conference
        """
        self.conf_serve_ports = {}
        self.data_serve_ports = {}
        self.clients_info = []
        self.client_conns = {}
        self.running = False

    def start(self):
        """
        start the ConferenceServer and necessary running tasks to handle clients in this conference
        """
        self.running = True


class MainServer:
    def __init__(self, server_ip, main_port):
        # async server
        self.server_ip = server_ip
        self.server_port = main_port
        self.main_server = None

        self.conference_count = 0
        self.conference_port_save = main_port + 1
        self.conference_conns = []
        self.conference_ids = []
        self.from_info_to_conference = {}
        self.conference_servers = (
            {}
        )  # self.conference_servers[conference_id] = ConferenceManager

    def handle_create_conference(self, from_info):
        """
        create conference: create and start the corresponding ConferenceServer, and reply necessary info to client
        """
        try:
            new_conference = ConferenceServer()
            new_conference.conference_id = self.conference_count
            new_conference.host_info = from_info
            self.conference_ids.append(new_conference.conference_id)
            self.conference_count += 1
            new_conference.conf_serve_ports = {}
            new_conference.data_serve_ports = {}

            new_conference.start()
            self.conference_servers[new_conference.conference_id] = new_conference
            print(f"Create conference, id {new_conference.conference_id}")
            return new_conference.conference_id, 200
        except Exception as e:
            print(f"Error in creating conference: {e}")
            return "Error in creating conference", 500

    def handle_join_conference(self, from_info, conference_id):
        """
        join conference: search corresponding conference_info and ConferenceServer, and reply necessary info to client
        """
        if conference_id not in self.conference_ids:
            print(f"Conference {conference_id} not found")
            return "Conference not found", 404

        try:
            print(f"Joining conference {conference_id} ...")
            self.from_info_to_conference[from_info] = conference_id
            conference_server: ConferenceServer = self.conference_servers[conference_id]
            conference_server.clients_info.append(from_info)

            # build conference port's socket
            use_port = self.conference_port_save
            conference_server.conf_serve_ports[from_info] = use_port
            conference_server.client_conns[from_info] = {}
            conference_server.client_conns[from_info][use_port] = socket.socket(
                socket.AF_INET, socket.SOCK_STREAM
            )
            conference_server.client_conns[from_info][use_port].bind(
                (self.server_ip, use_port)
            )
            conference_server.client_conns[from_info][use_port].listen(5)
            self.conference_port_save += 1

            # build data ports' socket
            conference_server.data_serve_ports[from_info] = {}
            for data_type in conference_server.data_types:
                use_port = self.conference_port_save
                conference_server.data_serve_ports[from_info][data_type] = use_port
                conference_server.client_conns[from_info][use_port] = socket.socket(
                    socket.AF_INET, socket.SOCK_DGRAM
                )
                conference_server.client_conns[from_info][use_port].bind(
                    (self.server_ip, use_port)
                )
                self.conference_port_save += 1

            save_server_port(self.conference_port_save)

            print(f"Client {from_info} join conference {conference_id}")
            return (
                json.dumps(
                    {
                        "host": self.server_ip,
                        "conference_id": conference_id,
                        "conf_serve_port": conference_server.conf_serve_ports[
                            from_info
                        ],
                        "data_serve_ports": conference_server.data_serve_ports[
                            from_info
                        ],
                        "data_types": conference_server.data_types,
                    }
                ),
                200,
            )
        except Exception as e:
            print(f"Error in joining conference: {e}")
            traceback.print_exc()
            return "Error in joining conference", 500

    def handle_quit_conference(self, from_info):
        """
        quit conference (in-meeting request & or no need to request)
        """
        try:
            conference_id = self.from_info_to_conference[from_info]
            conference_server = self.conference_servers[conference_id]

            if (
                len(conference_server.client_conns.items()) == 1
            ):  # is the only client in the conference, so can shut down the conference
                self.handle_cancel_conference(from_info, True)
                print(
                    f"Client {from_info} quit and shut down conference {conference_id}"
                )
                return "Quit conference successfully", 200

            conference_server.conf_serve_ports.pop(from_info)
            self.from_info_to_conference.pop(from_info)
            conference_server.data_serve_ports.pop(from_info)
            del conference_server.client_conns[from_info]

            print(f"Client {from_info} quit conference {conference_id}")
            return "Quit conference successfully", 200
        except Exception as e:
            print(f"Error in quitting conference: {e}")
            return "Error in quitting conference", 500

    def handle_start_data_stream(self, from_info, conference_id, udp_info):
        """
        start data stream: start data stream from a client in a conference
        """
        try:
            conf_server: ConferenceServer = self.conference_servers[conference_id]
            conf_server.clients_udp_addrs[from_info] = udp_info
            for data_type in conf_server.data_serve_ports[from_info]:
                data_port = conf_server.data_serve_ports[from_info][data_type]
                data_thread = threading.Thread(
                    target=conf_server.handle_data,
                    args=(
                        conf_server.client_conns[from_info][data_port],
                        from_info,
                        data_type,
                    ),
                )
                data_thread.start()
            return "Start data stream successfully", 200
        except Exception as e:
            print(f"Error in starting data stream: {e}")
            return "Error in starting data stream", 500

    def handle_client_exit(self, from_info, current_client):
        """
        exit the program (in-meeting request)
        """
        try:
            if from_info in self.from_info_to_conference:
                conference_id = self.from_info_to_conference[from_info]
                if conference_id in self.conference_servers:
                    conference_server = self.conference_servers[conference_id]
                    if from_info in conference_server.conf_serve_ports:
                        conference_server.conf_serve_ports.pop(from_info)
                    if from_info in conference_server.data_serve_ports:
                        conference_server.data_serve_ports.pop(from_info)
                    if from_info in conference_server.clients_udp_addrs:
                        conference_server.clients_udp_addrs.pop(from_info)
                    if from_info in self.from_info_to_conference:
                        del self.from_info_to_conference[from_info]
                    if from_info in conference_server.client_conns:
                        del conference_server.client_conns[from_info]

            current_client.close()
            self.conference_conns.remove(current_client)

            print(f"Client {from_info} exit successfully")
            return "Client exit successfully", 200
        except Exception as e:
            print(f"Error in handling client exit: {e}")
            traceback.print_exc()
            return "Error in handling client exit", 500

    def handle_cancel_conference(self, from_info, forced=False):
        """
        cancel conference (in-meeting request, a ConferenceServer should be closed by the MainServer)
        """
        try:
            conference_id = self.from_info_to_conference[from_info]
            conference_server: ConferenceServer = self.conference_servers[conference_id]

            if conference_server.host_info != from_info and not forced:
                return "Only the manager can cancel the conference", 403

            conference_server.broadcast_message(CANCEL_MSG, from_info, "text")
            conference_server.cancel_conference()
            self.conference_ids.remove(conference_id)
            self.conference_servers.pop(conference_id)

            print(f"Cancel conference, id {conference_id}")
            return "Cancelled successfully", 200
        except Exception as e:
            print(f"Error in cancelling conference: {e}")
            traceback.print_exc()
            return "Error in cancelling conference", 500

    def request_handler(self, client_socket: socket.socket, from_info):
        """
        running task: handle out-meeting (or also in-meeting) requests from clients
        """
        print(f"start connecting {from_info}")
        from_info = str(from_info)
        while True:
            try:
                # data = reader.read(100)  # Adjust buffer size as needed
                message = client_socket.recv(CHUNK).decode()
                request = message.split(" ")
                print(f"Received {message} from {from_info}")

                action = request[0]
                response = ""
                status_code = 400

                if action == "create":
                    conference_id, status_code = self.handle_create_conference(
                        from_info
                    )
                    response = str(conference_id)

                elif action == "join":
                    conference_id = int(request[1])
                    response, status_code = self.handle_join_conference(
                        from_info, conference_id
                    )

                elif action == "list":
                    response = json.dumps(self.conference_ids)
                    status_code = 200

                elif action == "quit":
                    response, status_code = self.handle_quit_conference(from_info)

                elif action == "cancel":
                    response, status_code = self.handle_cancel_conference(from_info)

                elif action == "exit":
                    self.handle_client_exit(from_info, client_socket)
                    break

                elif action == "link":
                    conference_id = int(request[1])
                    udp_info = ast.literal_eval(request[2])
                    response, status_code = self.handle_start_data_stream(
                        from_info, conference_id, udp_info
                    )

                print(response + "\n" + str(status_code))
                client_socket.sendall((response + "\n" + str(status_code)).encode())
            except Exception as e:
                traceback.print_exc()
                print(f"Error handling request: {e}")

    def start(self):
        """
        start MainServer
        """
        self.main_server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.main_server.bind(
            (self.server_ip, self.server_port)
        )  # Bind to any available network interface
        self.main_server.listen(10)
        print("Server listening on port", self.server_port)

        try:
            while True:
                # Accept a new client connection
                client_socket, addr = self.main_server.accept()
                self.conference_conns.append(client_socket)
                print(f"Accepted connection from {addr}")
                # Start a new thread to handle the client
                client_thread = threading.Thread(
                    target=self.request_handler,
                    args=(
                        client_socket,
                        addr,
                    ),
                )
                client_thread.start()
        except KeyboardInterrupt:
            print("Shutting down the server...")
            self.main_server.close()


if __name__ == "__main__":
    server = MainServer(SERVER_IP, sync_server_host())
    server.start()
