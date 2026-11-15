# Festo CP Lab module: OPC UA interface (device sheet)

Controller: Festo CECC-LK (CODESYS V3). Application: `Application`.

| Setting | Value |
| --- | --- |
| OPC UA endpoint | `opc.tcp://192.168.68.62:4840` |
| Security | None, anonymous login |
| Namespace index of the PLC variables | 2 |
| NodeId format | `ns=2;s=\|var\|CECC-LK.Application.<symbol>` |

Example: symbol `FBs.stpStopper1.convConveyor.xRight` has the NodeId
`ns=2;s=|var|CECC-LK.Application.FBs.stpStopper1.convConveyor.xRight`.

## Symbol configuration (published variables)

| Symbol | IEC type | OPC UA type | Description |
| --- | --- | --- | --- |
| `FBs.stpStopper1.convConveyor.xRight` | BOOL | Boolean | Conveyor running to the right |
| `FBs.stpStopper1.stpStopper.cpfssStopper.xCarrierAvailable` | BOOL | Boolean | Carrier present at the stopper |
| `FBs.stpStopper1.stpStopper.cpfssStopper.xReleaseStopper` | BOOL | Boolean | Release the stopper (command) |
| `FBs.stpStopper1.stpStopper.stManualControl.xReadRfid` | BOOL | Boolean | Manual RFID read request |
| `FBs.stpStopper1.stpStopper.stRfidVisu.uiCarrierID` | UINT | UInt16 | Carrier ID read from the RFID tag |
| `FBs.stpStopper1.stpStopper.stManualControl.xWriteRfid` | BOOL | Boolean | Manual RFID write request |
| `FBs.stpStopper1.stRfidData.stMesData.udiPNo` | UDINT | UInt32 | Product number from the MES data on the carrier |
| `fromCDPX.stManualWorkplace.xManualJobStarted` | BOOL | Boolean | Manual job started at the workplace |
| `fromCDPX.stManualWorkplace.xManualJobFinished` | BOOL | Boolean | Manual job finished at the workplace |

Data type names in the framework's wizard: Boolean = `bool`, UInt16 = `uint16`,
UInt32 = `uint32`.
