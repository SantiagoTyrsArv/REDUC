"""Write the OpenAPI document that packages/api-client is generated from."""

import json
import sys
from pathlib import Path

from reduc.api.main import create_app
from reduc.settings import Settings


class _NoRateLimit:
    async def allows(self, _client_ip: str) -> bool:
        return True


def main() -> None:
    """Export without touching Redis, PostgreSQL or the network."""
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("openapi.json")
    schema = create_app(Settings(), _NoRateLimit()).openapi()
    target.write_text(json.dumps(schema, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
