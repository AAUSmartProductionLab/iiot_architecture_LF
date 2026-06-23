"""
This module defines the MqttPublisher class, which is responsible 
for publishing messages to an MQTT broker. It uses the paho-mqtt 
library to handle MQTT communication. The class provides methods 
for connecting to the broker, publishing messages, 
and disconnecting from the broker.

Intended usage is a newly initialised connecter per protocol connector.
"""

import paho.mqtt.client as mqtt
import time

class MqttPublisher:
    """A class to publish messages to an MQTT broker."""
    def __init__(self, broker_address, broker_port=1883, qos=0, client_id=None):
        """Initialize the MQTT publisher with the broker address and port."""
        # Attributes
        self.broker_address = broker_address
        self.broker_port = broker_port
        self.qos = qos
        self.client_id = client_id
        self.connected = False

        # Initialise Client
        self.client = mqtt.Client(client_id=self.client_id)
        
        # Callbacks
        self.client.on_connect = self.on_connect
        self.client.on_disconnect = self.on_disconnect

    def connect(self):
        """Connect to the MQTT broker."""
        try:
            #Connect to Broker
            self.client.connect(self.broker_address, self.broker_port)
            # Start MQTT Loop
            self.client.loop_start()
            self.wait_until_connected()
        except Exception as e:
            print(f"Failed to connect to MQTT broker: {e}")

    def publish(self, topic, payload):
        """Publish a message to the specified topic."""
        # Ensure connection before publishing
        if not self.connected:
            print("Cannot publish: not connected.")
            return
        try:
            # Publish to Broker and wait for response
            pub = self.client.publish(topic, str(payload), qos=self.qos)
            pub.wait_for_publish()
            print(f"Published message to topic '{topic}': {payload}")
        except Exception as e:
            # If failure raise exception
            print(f"Failed to publish message: {e}")

    def disconnect(self):
        """Disconnect from the MQTT broker."""
        try:
            #End MQTT Loop
            self.client.loop_stop()
            # Disconnect from Broker
            self.client.disconnect()
            print("Disconnected from MQTT broker")
        except Exception as e:
            # If failure raise exception
            print(f"Failed to disconnect from MQTT broker: {e}")
        
    
    def on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            self.connected = True
            print(f"Connected to MQTT broker at {self.broker_address}:{self.broker_port}")
        else:
            print(f"Connection failed with code {rc}.")

    def on_disconnect(self, client, userdata, rc):
        
        self.connected = False
        if rc == 0:
            print("Disconnected cleanly.")
        else:
            print(f"Unexpected disconnection with code {rc}.")

    
    def wait_until_connected(self, timeout=5):
        start = time.time()
        while not self.connected:
            if time.time() - start > timeout:
                raise TimeoutError("Connection timeout")
            time.sleep(0.1)
