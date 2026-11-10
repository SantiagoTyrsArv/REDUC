"""Worker process placeholder until the pipeline actors arrive in T-22."""

import time


def run() -> None:
    """Keep the worker service alive while pipeline actors are not configured."""
    while True:
        time.sleep(3600)


if __name__ == "__main__":
    run()
