"""Discover stored data through a device AAS; uses only the Python standard library."""
import argparse
import base64
import json
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from urllib.request import urlopen

TIME_SERIES = "https://admin-shell.io/idta/TimeSeries/1/1"


def read_json(url):
    with urlopen(url, timeout=10) as response:
        return json.load(response)


def encoded(identifier):
    return base64.urlsafe_b64encode(identifier.encode()).decode().rstrip("=")


def semantic(element, identifier):
    return any(k.get("value") == identifier for k in element.get("semanticId", {}).get("keys", []))


def discover(base, aas_id, datapoint):
    shell = read_json(f"{base.rstrip('/')}/shells/{encoded(aas_id)}")
    for ref in shell.get("submodels", []):
        sm_id = ref["keys"][-1]["value"]
        sm = read_json(f"{base.rstrip('/')}/submodels/{encoded(sm_id)}")
        if not semantic(sm, TIME_SERIES):
            continue
        for collection in sm.get("submodelElements", []):
            if not semantic(collection, "https://admin-shell.io/idta/TimeSeries/Segments/1/1"):
                continue
            for segment in collection.get("value", []):
                properties = {e["idShort"]: e.get("value") for e in segment.get("value", [])}
                if properties.get("Datapoint") == datapoint:
                    return properties["Endpoint"], properties["Query"]
    raise ValueError(f"No history link for {datapoint!r} in this device AAS")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--aas-url", required=True, help="BaSyx AAS Environment URL, e.g. http://server:8081")
    parser.add_argument("--aas-id", required=True, help="Full device AAS identifier, copied from the dashboard")
    parser.add_argument("--datapoint", required=True)
    parser.add_argument("--start", help="ISO timestamp including timezone")
    parser.add_argument("--end", help="ISO timestamp including timezone")
    args = parser.parse_args()
    endpoint, query = discover(args.aas_url, args.aas_id, args.datapoint)
    parsed = urlsplit(endpoint)
    if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("History endpoint must be an HTTP(S) URL without embedded credentials")
    params = dict(parse_qsl(query))
    for key in ("start", "end"):
        if getattr(args, key):
            params[key] = getattr(args, key)
    url = urlunsplit(parsed._replace(query=urlencode(params)))
    # Same-origin continuation; no database address, SQL or credentials required.
    while url:
        if urlsplit(url).netloc != parsed.netloc or urlsplit(url).scheme != parsed.scheme:
            raise ValueError("Pagination unexpectedly changed the history server")
        page = read_json(url)
        for record in page["records"]:
            print(json.dumps(record))
        if page.get("page_limit_reached"):
            raise RuntimeError("Too many records: repeat with a shorter time window")
        url = page.get("next_url")


if __name__ == "__main__":
    main()
