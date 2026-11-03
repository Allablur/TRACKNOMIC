"""Import a real artist into your deployed API without exposing Spotify credentials."""

import argparse
import getpass
import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Never forward an operator token to a redirect destination.
        return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--api", required=True, help="Your API base URL, normally HTTPS"
    )
    parser.add_argument(
        "--artist", required=True, help="Spotify artist ID, URI or artist share link"
    )
    args = parser.parse_args()
    url = urlsplit(args.api)
    if url.username or url.password or url.query or url.fragment or not url.hostname:
        parser.error(
            "Use an API base URL without credentials, query strings or fragments"
        )
    if url.scheme != "https" and not (
        url.scheme == "http" and url.hostname in {"localhost", "127.0.0.1"}
    ):
        parser.error("HTTPS is required except for localhost development")
    token = getpass.getpass("API ingestion token (hidden): ")
    request = Request(
        args.api.rstrip("/") + "/api/v1/ingestion/spotify/artists",
        data=json.dumps({"artist_id": args.artist}).encode(),
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + token,
        },
        method="POST",
    )
    try:
        with build_opener(NoRedirect()).open(request, timeout=90) as response:
            data = json.load(response)
        print(f"Imported {data['name']} from Spotify. {data['spotify_url']}")
        print("Scope:", json.dumps(data["import_scope"]))
    except HTTPError as exc:
        try:
            problem = json.load(exc)
        except (ValueError, UnicodeError):
            problem = {
                "detail": "The API returned a non-JSON error; check its base URL"
            }
        print(
            f"Import failed (HTTP {exc.code}): {problem.get('detail', 'Request failed')}"
        )
        if exc.headers.get("Retry-After"):
            print("Retry after", exc.headers["Retry-After"], "seconds.")
        raise SystemExit(1) from None
    except (URLError, TimeoutError):
        raise SystemExit(
            "Could not reach the API; check the URL and try again."
        ) from None


if __name__ == "__main__":
    main()
