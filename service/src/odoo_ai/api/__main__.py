"""Development entrypoint for the Assistant Service."""

import uvicorn

DEV_HOST = "127.0.0.1"
DEV_PORT = 8000


def main() -> None:
    """Run the local HTTP service on loopback."""

    uvicorn.run("odoo_ai.api:app", host=DEV_HOST, port=DEV_PORT)


if __name__ == "__main__":
    main()
