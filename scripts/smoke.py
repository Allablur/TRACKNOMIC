"""Read-only smoke check for local or deployed services; standard TLS verification stays enabled."""
import argparse
import json
from urllib.request import urlopen


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api", default="http://127.0.0.1:8000")
    parser.add_argument("--frontend", default="http://127.0.0.1:3000")
    args = parser.parse_args()
    with urlopen(args.api.rstrip("/") + "/health", timeout=30) as response:
        assert response.status == 200
        assert json.load(response) == {"status": "ok", "database": "connected"}
    for path in ["/dashboard", "/artists", "/compare", "/albums", "/genres", "/reports", "/settings"]:
        with urlopen(args.frontend.rstrip("/") + path, timeout=30) as response:
            assert response.status == 200 and "Trackonomics" in response.read().decode()
    with urlopen(args.frontend.rstrip("/") + "/api/v1/dashboard/overview", timeout=30) as response:
        overview = json.load(response)
        assert all(isinstance(overview[key], int) for key in ("artists", "albums", "tracks"))
    print("Health, seven frontend routes, and frontend-to-API analytics proxy passed.")


if __name__ == "__main__":
    main()
