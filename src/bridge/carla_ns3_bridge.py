import json
import socket
import threading
import time
import sys
from src.common.logger import logger
from config.settings import NS3_HOST, NS3_SEND_PORT, NS3_RECV_PORT

class CarlaNs3Bridge:
    """Bridge for communication between CARLA and ns-3 using standard sockets"""
    
    def __init__(self, ns3_host: str = NS3_HOST, ns3_send_port: int = NS3_SEND_PORT, ns3_recv_port: int = NS3_RECV_PORT):
        self.ns3_host = ns3_host
        self.ns3_send_port = ns3_send_port
        self.ns3_recv_port = ns3_recv_port
        self.socket = None
        self.receiver_socket = None
        self.connected = False
        self.running = True
        self.reconnect_thread = None
        self.receiver_thread = None
        self.received_messages = []

    def _connect(self) -> bool:
        """Connect to ns-3 server"""
        if self.socket:
            self.socket.close()
            
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.connect((self.ns3_host, self.ns3_send_port))
            self.connected = True
            return True
        except Exception as e:
            logger.error(f"Error connecting to NS-3 bridge: {e}")
            self.connected = False
            return False

    def _reconnect_loop(self):
        """Try to reconnect periodically"""
        while self.running and not self.connected:
            if self._connect():
                break
            time.sleep(5)

    def ensure_connection(self):
        """Ensure there's a connection to ns-3, try to reconnect if not"""
        if not self.connected and not self.reconnect_thread:
            self.reconnect_thread = threading.Thread(target=self._reconnect_loop)
            self.reconnect_thread.daemon = True
            self.reconnect_thread.start()

    def _listen_for_messages(self):
        """Listen for messages from ns-3"""
        try:
            self.receiver_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.receiver_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.receiver_socket.bind((self.ns3_host, self.ns3_recv_port))
            self.receiver_socket.listen(1)
            
            while self.running:
                try:
                    client_socket, _ = self.receiver_socket.accept()
                    data = client_socket.recv(1024)
                    if data:
                        try:
                            message = json.loads(data.decode('utf-8'))
                            if message.get("type") == "simulation_end":
                                logger.info("Received simulation end signal from NS-3")
                                self.running = False
                                break
                        except json.JSONDecodeError:
                            pass
                    client_socket.close()
                except socket.error:
                    break
        except Exception as e:
            logger.error(f"Error in end signal listener: {e}")
        finally:
            if self.receiver_socket:
                self.receiver_socket.close()

    def _start_receiver(self):
        """Start threads to receive messages from ns-3"""
            
        if not self.receiver_thread:
            self.receiver_thread = threading.Thread(target=self._listen_for_messages)
            self.receiver_thread.daemon = True
            self.receiver_thread.start()

    def send_vehicle_states(self, vehicles):
        """Send vehicle states to ns-3"""
        if not self.running:
            logger.info("Simulation ended, not sending more vehicle states")
            return False
            
        if not self.connected:
            logger.warning("Not connected, attempting to reconnect...")
            self.ensure_connection()
            if not self.connected:
                logger.error("Failed to reconnect")
                return False
        
        try:
            message = json.dumps(vehicles)
            self.socket.sendall((message + "\n").encode('utf-8'))
            logger.info(f"Sent {len(message)} bytes to NS-3 successfully")
            return True
        except Exception as e:
            logger.error(f"Error sending vehicle states: {e}")
            self.connected = False
            return False

    def stop(self):
        """Stop the bridge"""
        self.running = False
        if self.socket:
            self.socket.close()
        if self.receiver_socket:
            self.receiver_socket.close()
        if self.reconnect_thread:
            self.reconnect_thread.join(timeout=1.0)
        if self.receiver_thread:
            self.receiver_thread.join(timeout=1.0)

    def _start_sender(self):
        """Start the sender"""
        self._connect()

    def start(self):
        """Start the bridge"""
        self._start_receiver()
        self._start_sender()
        logger.info("Bridge started")

    def is_simulation_running(self) -> bool:
        """Check if the simulation is running"""
        return self.running
