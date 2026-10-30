"""Container liveness check that preserves the configured Host header."""
import os
from urllib.parse import urlsplit
import urllib.request


def main():
    host = urlsplit(os.environ["RESIDENCY_ORIGIN"]).netloc
    request = urllib.request.Request("http://127.0.0.1:7340/healthz", headers={"Host": host})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(request, timeout=4) as response:
        if response.status != 200:
            raise SystemExit(1)


if __name__ == "__main__":
    main()
