"""
A script to test connector functionality with OPC UA Client.
"""

import asyncio

from connector_components.opc_ua_client import AsyncOPCUAClient
from connector_components.mqtt_pub_class import MqttPublisher


OPC_URL = "opc.tcp://192.168.0.131:53530/OPCUA/SimulationServer"
TEST_NODE = "ns=3;i=1001"


async def main():
    reader = AsyncOPCUAClient(OPC_URL)
    writer = MqttPublisher("127.0.0.1")

    try:
        await reader.connect()
        writer.connect() 

        await asyncio.sleep(1)

        while True:
            data = await reader.safe_read(TEST_NODE)
            writer.publish("/test", data)

            print("Published:", data)

            await asyncio.sleep(5)

    except KeyboardInterrupt:
        print("\nLoop cancelled by user.")

    finally:
        await reader.disconnect()
        writer.disconnect()


if __name__ == "__main__":
    asyncio.run(main())