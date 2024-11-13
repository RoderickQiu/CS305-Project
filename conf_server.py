import asyncio
import json

from util import *
import socket


class ConferenceServer:
    def __init__(
        self,
    ):
        # async server
        self.running = False
        self.conference_id = None  # conference_id for distinguish difference conference
        self.conf_serve_ports = {}
        self.data_serve_ports = {}
        self.data_types = [
            "screen",
            "camera",
            "audio",
            "text",
        ]  # example data types in a video conference
        self.clients_info = []
        self.client_conns = {}
        self.mode = "Client-Server"  # or 'P2P' if you want to support peer-to-peer conference mode

    async def handle_data(self, reader, writer, data_type):
        """
        running task: receive sharing stream data from a client and decide how to forward them to the rest clients
        """

    async def log(self):
        while self.running:
            print("Something about server status")
            await asyncio.sleep(LOG_INTERVAL)

    async def cancel_conference(self):
        """
        handle cancel conference request: disconnect all connections to cancel the conference
        """
        for client in self.clients_info:
            for port in self.client_conns[client]:
                self.client_conns[client][port].close()

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
        self.from_info_to_conference = {}
        self.conference_servers = (
            {}
        )  # self.conference_servers[conference_id] = ConferenceManager

    def handle_create_conference(
        self,
    ):
        """
        create conference: create and start the corresponding ConferenceServer, and reply necessary info to client
        """
        try:
            new_conference = ConferenceServer()
            new_conference.conference_id = self.conference_count
            self.conference_count += 1
            new_conference.conf_serve_ports = []
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
        if conference_id not in self.conference_conns:
            print(f"Conference {conference_id} not found")
            return "Conference not found", 404

        try:
            print(f"Joining conference {conference_id} ...")
            self.from_info_to_conference[from_info] = conference_id
            conference_server = self.conference_servers[conference_id]
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
                    socket.AF_INET, socket.SOCK_STREAM
                )
                conference_server.client_conns[from_info][use_port].bind(
                    (self.server_ip, use_port)
                )
                conference_server.client_conns[from_info][use_port].listen(5)
                self.conference_port_save += 1

            print(f"Client {from_info} join conference {conference_id}")
            return (
                json.dumps(
                    {
                        "conference_id": conference_id,
                        "conf_serve_port": use_port,
                        "data_serve_ports": conference_server.data_serve_ports[
                            use_port
                        ],
                        "data_types": conference_server.data_types,
                    }
                ),
                200,
            )
        except Exception as e:
            print(f"Error in joining conference: {e}")
            return "Error in joining conference", 500

    def handle_quit_conference(self, from_info):
        """
        quit conference (in-meeting request & or no need to request)
        """
        try:
            conference_id = self.from_info_to_conference[from_info]
            conference_server = self.conference_servers[conference_id]
            conference_server.conf_serve_ports.pop(from_info)
            self.from_info_to_conference.pop(from_info)
            conference_server.data_serve_ports.pop(from_info)

            # disconnect sockets
            for port in conference_server.client_conns[from_info]:
                conference_server.client_conns[from_info][port].close()

            print(f"Client {from_info} quit conference {conference_id}")
            return "Quit conference successfully", 200
        except Exception as e:
            print(f"Error in quitting conference: {e}")
            return "Error in quitting conference", 500

    def handle_cancel_conference(self, from_info):
        """
        cancel conference (in-meeting request, a ConferenceServer should be closed by the MainServer)
        """
        try:
            conference_id = self.from_info_to_conference[from_info]
            conference_server = self.conference_servers[conference_id]
            conference_server.cancel_conference()
            print(f"Cancel conference, id {conference_id}")
        except Exception as e:
            print(f"Error in cancelling conference: {e}")
            return "Error in cancelling conference", 500

    async def request_handler(self, reader, writer, from_info):
        """
        running task: handle out-meeting (or also in-meeting) requests from clients
        """
        try:
            data = await reader.read(100)  # Adjust buffer size as needed
            message = data.decode()
            request = message.split(" ")
            print(f"Received {message} from {from_info}")

            action = request[0]
            response = ""
            status_code = 400

            if action == "create":
                conference_id, status_code = self.handle_create_conference()
                response = str(conference_id)

            elif action == "join":
                conference_id = int(request[1])
                response, status_code = self.handle_join_conference(
                    from_info, conference_id
                )

            elif action == "quit_conference":
                response, status_code = self.handle_quit_conference(from_info)

            elif action == "cancel_conference":
                response, status_code = self.handle_cancel_conference(from_info)

            print(response + "\n" + str(status_code))
            writer.write((response + "\n" + str(status_code)).encode())
            await writer.drain()
        except Exception as e:
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

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(self.accept_connections(loop))
        try:
            loop.run_forever()
        finally:
            loop.close()

    async def accept_connections(self, loop):
        self.main_server.setblocking(False)
        while True:
            client_socket, addr = await loop.sock_accept(self.main_server)
            print(f"New connection from {addr}")
            reader, writer = await asyncio.open_connection(sock=client_socket)
            loop.create_task(self.request_handler(reader, writer, addr))


if __name__ == "__main__":
    server = MainServer(SERVER_IP, MAIN_SERVER_PORT)
    server.start()
