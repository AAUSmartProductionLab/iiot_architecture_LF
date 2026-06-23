"""
A script to test connector functionality.

Stage 1:
- Implement the finished modbus connector and test integration with modbusTCPserver and mqtt broker.

Stage 3:
- Implemet and test with docker. 
"""

from connector_components.modbus_sync_tcp_client_class import ModbusClient
from connector_components.mqtt_pub_class import MqttPublisher
import time

reader = ModbusClient("127.0.0.1")
writer = MqttPublisher("127.0.0.1")

try:
    reader.connect()
    writer.connect()
    time.sleep(5)

    while True:
        data = reader.read("FC3", 1, 5)
        writer.publish("/test", data)

        time.sleep(5)

except KeyboardInterrupt:
    print("\nLoop cancelled by user.")