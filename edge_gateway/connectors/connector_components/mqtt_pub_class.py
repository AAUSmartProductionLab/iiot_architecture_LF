"""
This module defines the MqttPublisher class, which is responsible 
for publishing messages to an MQTT broker. It uses the paho-mqtt 
library to handle MQTT communication. The class provides methods 
for connecting to the broker, publishing messages, 
and disconnecting from the broker.

Intended usage is a newly initialised connecter per protocol connector.
"""

import paho.mqtt.client as mqtt
import logging
import time

logger = logging.getLogger(__name__)

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

    #------------------------------
    # Connection / Disconneciton
    #------------------------------

    def connect(self):
        """Connect to the MQTT broker."""
        
        if self.connected:
            logger.info("Already connected to MQTT broker.")
            return

        try:
            #Connect to Broker
            self.client.connect(self.broker_address, self.broker_port)
            # Start MQTT Loop
            self.client.loop_start()
            self.wait_until_connected()
        except Exception as e:
            logger.error(f"Failed to connect to MQTT broker: {e}")
            raise

    def disconnect(self):
        """Disconnect from the MQTT broker."""
        if not self.connected:
            logger.info("Client not connected, cannot disconnect.")
            return
        try:
            #End MQTT Loop
            self.client.loop_stop()
            # Disconnect from Broker
            self.client.disconnect()
            logger.info("Disconnected from MQTT broker")
        except Exception as e:
            # If failure raise exception
            logger.error(f"Failed to disconnect from MQTT broker: {e}")
            raise
        
    
    def on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            self.connected = True
            logger.info(f"Connected to MQTT broker at {self.broker_address}:{self.broker_port}")
        else:
            logger.error(f"Connection failed with code {rc}.")

    def on_disconnect(self, client, userdata, rc):
        self.connected = False
        if rc == 0:
            logger.info("Disconnected cleanly.")
        else:
            logger.error(f"Unexpected disconnection with code {rc}.")
    
    def wait_until_connected(self, timeout=5):
        start = time.time()
        while not self.connected:
            if time.time() - start > timeout:
                raise TimeoutError("Connection timeout")
            time.sleep(0.1)

    #------------------------------
    # Publish 
    #------------------------------

    def publish(self, topic, payload):
        """Publish a message to the specified topic."""
        # Ensure connection before publishing
        if not self.connected:
            logger.error("Cannot publish: not connected.")
            return
        try:
            # Publish to Broker and wait for response
            for key, value in payload.items():
                pub = self.client.publish(f"{topic}/{key}", str(value), qos=self.qos)
                pub.wait_for_publish()
                logger.info(f"Published message to topic '{topic}/{key}': {value}")
        except Exception as e:
            # If failure raise exception
            logger.error(f"Failed to publish message: {e}")
            raise