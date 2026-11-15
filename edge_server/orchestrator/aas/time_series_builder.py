"""IDTA 02008-1-1 LinkedSegment profile for the project's read-only history API.

Only descriptions/links are stored in AAS, never samples. The HTTP response and
extension properties are project-specific, not standardized AAS operations.
"""
from urllib.parse import urlencode
from basyx.aas import model
from . import ids

BASE = "https://admin-shell.io/idta/TimeSeries"


class TimeSeriesBuilder:
    def __init__(self, semantic_factory, element_factory):
        self.sf, self.ef = semantic_factory, element_factory

    def sem(self, path=""):
        return self.sf.create_external_reference(f"{BASE}{'/' + path if path else ''}/1/1")

    def build(self, system_id, *, datapoints, api_base):
        ef = self.ef
        record = ef.create_collection("Record", [
            model.Property(id_short="Time00", value_type=model.datatypes.DateTime,
                           semantic_id=self.sem("UtcTime"))
        ], semantic_id=self.sem("Record"))
        metadata = ef.create_collection("Metadata", [
            ef.create_multi_language_property("Name", f"{system_id} measurement history",
                                        semantic_id=self.sem("Metadata/Name")),
            ef.create_multi_language_property("Description",
                "External, change-reported samples. HTTP JSON rows contain time, datapoint, value, unit and topic. "
                "Time is the stored telemetry timestamp, not a guaranteed source or insertion timestamp. "
                "No fixed sampling rate or completeness is implied.", semantic_id=self.sem("Metadata/Description")),
            record,
        ], semantic_id=self.sem("Metadata"))
        segments = []
        for i, dp in enumerate(datapoints):
            query = urlencode({"device": system_id, "datapoint": dp["name"], "limit": 1000})
            elements = [
                ef.create_multi_language_property("Name", dp["name"],
                                            semantic_id=self.sem("Segment/Name")),
                ef.create_property("Endpoint", api_base + "/api/measurements/history", semantic_id=self.sem("Endpoint")),
                ef.create_property("Query", query, semantic_id=self.sem("Query")),
            ]
            # Application extensions deliberately use project-owned identifiers.
            for key, value in {"Datapoint": dp["name"], "Datatype": dp.get("datatype", ""),
                               "Unit": dp.get("unit", ""), "Topic": dp.get("uns_topic", ""),
                               "Method": "GET", "ApiDescription": api_base + "/openapi.json"}.items():
                elements.append(ef.create_property(key, value, semantic_id=self.sf.create_external_reference(
                    f"{ids.BASE}/concepts/History/{key}/1/0")))
            segments.append(ef.create_collection(f"LinkedSegment{i:02d}", elements,
                                                semantic_id=self.sem("Segments/LinkedSegment")))
        return model.Submodel(id_=ids.submodel_id(system_id, "TimeSeries"), id_short="TimeSeries",
            kind=model.ModellingKind.INSTANCE, semantic_id=self.sem(), submodel_element=[metadata,
                ef.create_collection("Segments", segments, semantic_id=self.sem("Segments"))])
