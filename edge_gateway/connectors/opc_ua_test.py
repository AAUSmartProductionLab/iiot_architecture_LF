"""
A script to test the AsyncOPCUAClient class.
"""

import asyncio
import logging

from connector_components.opc_ua_client import AsyncOPCUAClient  # adjust import!

# -------------------------
# Configuration
# -------------------------
OPC_URL = "opc.tcp://MartinPC:53530/OPCUA/SimulationServer"
TEST_NODE = "ns=3;i=1001"   # change to a valid node on your server


# -------------------------
# Logging setup
# -------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

logging.getLogger("asyncua").setLevel(logging.WARNING)


# -------------------------
# Test functions
# -------------------------
async def test_connection():
    print("\n--- Testing connection ---")
    client = AsyncOPCUAClient(OPC_URL)

    await client.connect()
    print("Connected:", client.is_connected())

    await client.disconnect()
    print("Disconnected:", not client.is_connected())


#async def test_read():
#    print("\n--- Testing read ---")
#
#    async with AsyncOPCUAClient(OPC_URL) as client:
        # value = await client.read(TEST_NODE)
        # print(f"Read value from {TEST_NODE}: {value}")


async def test_safe_read():
    print("\n--- Testing safe_read (with retry) ---")

    async with AsyncOPCUAClient(OPC_URL) as client:
        value = await client.safe_read(TEST_NODE)
        print(f"Safe read value: {value}")


#async def test_write():
#    print("\n--- Testing write ---")
#
#    async with AsyncOPCUAClient(OPC_URL) as client:
#        print("Writing value 42...")
#        await client.write(TEST_NODE, 42)
#
#        value = await client.read(TEST_NODE)
#        print(f"New value: {value}")


# -------------------------
# Main runner
# -------------------------
async def main():
    try:
        await test_connection()
#        await test_read()
        await test_safe_read()

        # Only run if your node is writable
        #await test_write()

    except Exception as e:
        print("Test failed:", e)


if __name__ == "__main__":
    asyncio.run(main())