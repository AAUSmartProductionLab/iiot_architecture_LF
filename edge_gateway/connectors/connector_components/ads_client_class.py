"""
This module implements an ADS client class.
"""

import pyads
import logging
from .models import ADSClientConfig, ADSReadRequest

logger = logging.getLogger(__name__)

class ADSClient:

    #------------------------------
    # Instantiation
    #------------------------------
    def __init__(self, config : ADSClientConfig):
        # Local Connection Attributes
        self.local_ip = config.local_ip
        self.local_netid = config.local_netid

        # If on linux, instantiate local address
        if not pyads.utils.platform_is_windows():
            pyads.open_port()
            pyads.set_local_address(self.local_netid)
            pyads.close_port()

        # Target Connection Attributes
        self.target_ip = config.target_ip
        self.target_netid = config.target_netid
        self.target_port = config.target_port
        self.target_routename = config.target_routename
        self.target_route_registered = False

        # Authentication Attributes
        self.username = config.username
        self.password = config.password

        # Type mapping dictionary
        self.ADS_DATA_TYPES = {
            "BOOL": pyads.PLCTYPE_BOOL,
            "DINT": pyads.PLCTYPE_DINT,
            "INT": pyads.PLCTYPE_INT,
            "LREAL": pyads.PLCTYPE_LREAL,
            "REAL": pyads.PLCTYPE_REAL,
            "SHORT": pyads.PLCTYPE_SHORT,
            "SINT": pyads.PLCTYPE_SINT,
            "UDINT": pyads.PLCTYPE_UDINT,
            "UINT": pyads.PLCTYPE_UINT,
            "USHORT": pyads.PLCTYPE_USHORT,
            "USINT": pyads.PLCTYPE_USINT,
            "STRING": pyads.PLCTYPE_STRING,
            "WSTRING": pyads.PLCTYPE_WSTRING,
            }
        
        # Instantiate Connection
        self.connection = pyads.Connection(
            ams_net_id = self.target_netid,
            ams_net_port = self.target_port,
            ip_address = self.target_ip
        )
    #------------------------------
    # Connection / Disconnection
    #------------------------------

    def connect(self):
        # Register route if route not yet registered
        if not self.target_route_registered:
            self.target_route_registered = self.register_route()
        # Check if connection is open
        if not self.connection.is_open:
            try:
                # Open connection
                self.connection.open()
                logger.info(
                    f"Connected to {self.target_netid}"
                    )
            except Exception as e:
                raise RuntimeError(
                    f"Failed to connect to {self.target_netid} at {self.target_ip}"
                    ) from e

    def disconnect(self):
        # Check if connection is open
        if self.connection.is_open:
            try:
                # Close connection
                self.connection.close()
                logger.info(
                    f"Successfully disconnected from {self.target_netid} at {self.target_ip}"
                    )
            except Exception as e:
                raise RuntimeError(
                    f"Failed to disconnect from {self.target_netid} at {self.target_ip}"
                    ) from e
        

    def register_route(self):
        # Check if route exists - this appears not to be 
        # implemented in pyads

        # Local route registration seems to be handled 
        # by ads.Connection() instantiation

        # Register route at PLC
        try:
            pyads.ads.add_route_to_plc(
                sending_net_id = self.local_netid,
                adding_host_name = self.local_ip,
                ip_address = self.target_ip,
                username = self.username if self.username else None,
                password = self.password if self.password else None,
                route_name = self.target_routename,
                added_net_id = self.target_netid if self.target_netid else None
                )
            logger.info(f"Successfully registered AMS route to {self.target_netid} at {self.target_ip}")
            return True
        except Exception as e:
            logger.error(f"AMS route registration failed: {e}")
            raise

    #------------------------------
    # Read
    #------------------------------
    def read(self, request: ADSReadRequest):
        try:
            # Check that connection is open, if not raise error
            if not self.connection.is_open:
                raise RuntimeError("ADS connection is not open.")
            # Read based on read type
            if request.ads_readtype == "by name":
                # Check that a name is given
                if request.dataname is None:
                    raise ValueError(
                        f"'dataname' must be specified for 'by name' reads."
                    )
                # Read by handle
                res = self.connection.read_by_name(
                    data_name= request.dataname,
                    plc_datatype= self.ADS_DATA_TYPES[request.datatype]
                    )

            elif request.ads_readtype == "list by name":
                if not request.datanames:
                    raise ValueError(
                        f"'datanames' must be specified for 'list by name' reads."
                    )
                # Read list by handle
                res = self.connection.read_list_by_name(
                    data_names= request.datanames
                    )

            elif request.ads_readtype == "by index":
                # Read by index
                res = self.connection.read(
                    index_group= request.index_group,
                    index_offset= request.index_offset,
                    plc_datatype= self.ADS_DATA_TYPES[request.datatype]
                    )
            else:
                raise ValueError(
                    f"Unsupported ADS read type: {request.ads_readtype}"
                    )
            return res
        
        except Exception as e:
            logger.error(f"Failed to read: {e}")
            raise