import sys

from .config import ConfigError, load_config
from .server import WebServer


def main(argv) -> int:
    if len(argv) > 2:
        print("usage: python3 -m webserv [config_file]", file=sys.stderr)
        return 1
    path = argv[1] if len(argv) == 2 else "config/default.conf"
    try:
        servers = load_config(path)
    except ConfigError as e:
        print(f"webserv: config error: {e}", file=sys.stderr)
        return 1
    server = WebServer(servers)
    try:
        server.bind()
    except OSError as e:
        print(f"webserv: {e}", file=sys.stderr)
        return 1
    server.run()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
