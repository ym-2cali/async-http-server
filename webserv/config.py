"""Parser for the nginx-like configuration file (see docs/01_config_parsing)."""
from dataclasses import dataclass, field

KNOWN_METHODS = ("GET", "POST", "DELETE")
DEFAULT_MAX_BODY = 1024 * 1024


class ConfigError(Exception):
    pass


@dataclass
class LocationConfig:
    path: str
    root: str | None = None
    index: list[str] | None = None
    autoindex: bool = False
    methods: set[str] = field(default_factory=lambda: set(KNOWN_METHODS))
    cgi_extensions: list[str] = field(default_factory=list)
    cgi_path: str | None = None
    upload_dir: str | None = None
    redirect: tuple[int, str] | None = None
    client_max_body_size: int | None = None


@dataclass
class ServerConfig:
    host: str = "0.0.0.0"
    port: int | None = None
    server_names: list[str] = field(default_factory=list)
    root: str = "./www"
    index: list[str] = field(default_factory=lambda: ["index.html"])
    error_pages: dict[int, str] = field(default_factory=dict)
    client_max_body_size: int = DEFAULT_MAX_BODY
    locations: list[LocationConfig] = field(default_factory=list)

    def match_location(self, path: str) -> LocationConfig:
        """Longest prefix match, on path-segment boundaries."""
        best = None
        for loc in self.locations:
            prefix = loc.path.rstrip("/")
            if loc.path == "/" or path == prefix or path.startswith(prefix + "/"):
                if best is None or len(loc.path) > len(best.path):
                    best = loc
        return best or LocationConfig(path="/")


# --------------------------------------------------------------------------- #
#                                   lexer                                     #
# --------------------------------------------------------------------------- #

def tokenize(text: str) -> list[tuple[str, int]]:
    tokens, i, line, n = [], 0, 1, len(text)
    while i < n:
        c = text[i]
        if c == "\n":
            line += 1
            i += 1
        elif c.isspace():
            i += 1
        elif c == "#":
            while i < n and text[i] != "\n":
                i += 1
        elif c in "{};":
            tokens.append((c, line))
            i += 1
        elif c in "\"'":
            end = text.find(c, i + 1)
            if end == -1:
                raise ConfigError(f"line {line}: unterminated string")
            tokens.append((text[i + 1:end], line))
            line += text.count("\n", i, end)
            i = end + 1
        else:
            start = i
            while i < n and not text[i].isspace() and text[i] not in "{};#":
                i += 1
            tokens.append((text[start:i], line))
    return tokens


# --------------------------------------------------------------------------- #
#                                   parser                                    #
# --------------------------------------------------------------------------- #

def parse_size(value: str, line: int) -> int:
    units = {"k": 1024, "m": 1024 ** 2, "g": 1024 ** 3}
    mult = units.get(value[-1:].lower(), 1)
    digits = value[:-1] if mult != 1 else value
    if not digits.isdigit():
        raise ConfigError(f"line {line}: invalid size '{value}'")
    return int(digits) * mult


def parse_port(value: str, line: int) -> int:
    if not value.isdigit() or not 1 <= int(value) <= 65535:
        raise ConfigError(f"line {line}: invalid port '{value}'")
    return int(value)


class _Parser:
    def __init__(self, tokens):
        self.tokens = tokens
        self.pos = 0

    def peek(self):
        return self.tokens[self.pos] if self.pos < len(self.tokens) else (None, self.last_line())

    def last_line(self):
        return self.tokens[-1][1] if self.tokens else 1

    def next(self):
        tok = self.peek()
        if tok[0] is None:
            raise ConfigError(f"line {tok[1]}: unexpected end of file")
        self.pos += 1
        return tok

    def expect(self, value):
        tok, line = self.next()
        if tok != value:
            raise ConfigError(f"line {line}: expected '{value}', got '{tok}'")

    def directive_args(self):
        """Collect values up to ';'."""
        args = []
        while True:
            tok, line = self.next()
            if tok == ";":
                return args
            if tok in "{}":
                raise ConfigError(f"line {line}: missing ';'")
            args.append(tok)

    def parse(self) -> list[ServerConfig]:
        servers = []
        while self.peek()[0] is not None:
            tok, line = self.next()
            if tok != "server":
                raise ConfigError(f"line {line}: unexpected '{tok}' (only 'server' blocks allowed at top level)")
            servers.append(self.parse_server())
        if not servers:
            raise ConfigError("no server block defined")
        seen = set()
        for s in servers:
            for name in s.server_names or [""]:
                key = (s.host, s.port, name)
                if key in seen:
                    raise ConfigError(f"duplicate server {name or '(default)'} on {s.host}:{s.port}")
                seen.add(key)
        return servers

    def parse_server(self) -> ServerConfig:
        self.expect("{")
        srv = ServerConfig()
        while True:
            tok, line = self.next()
            if tok == "}":
                break
            if tok == "location":
                srv.locations.append(self.parse_location())
                continue
            args = self.directive_args()
            if not args:
                raise ConfigError(f"line {line}: '{tok}' needs a value")
            if tok == "listen":
                host, _, port = args[0].rpartition(":")
                srv.host = host or "0.0.0.0"
                srv.port = parse_port(port, line)
            elif tok == "server_name":
                srv.server_names = [a.lower() for a in args]
            elif tok == "root":
                srv.root = args[0]
            elif tok == "index":
                srv.index = args
            elif tok == "error_page":
                if len(args) < 2:
                    raise ConfigError(f"line {line}: error_page needs <code...> <path>")
                for code in args[:-1]:
                    if not code.isdigit() or not 300 <= int(code) <= 599:
                        raise ConfigError(f"line {line}: invalid status code '{code}'")
                    srv.error_pages[int(code)] = args[-1]
            elif tok == "client_max_body_size":
                srv.client_max_body_size = parse_size(args[0], line)
            else:
                raise ConfigError(f"line {line}: unknown directive '{tok}' in server block")
        if srv.port is None:
            raise ConfigError(f"line {line}: server block without 'listen'")
        return srv

    def parse_location(self) -> LocationConfig:
        path, line = self.next()
        if not path.startswith("/"):
            raise ConfigError(f"line {line}: location path must start with '/'")
        self.expect("{")
        loc = LocationConfig(path=path)
        while True:
            tok, line = self.next()
            if tok == "}":
                return loc
            args = self.directive_args()
            if not args:
                raise ConfigError(f"line {line}: '{tok}' needs a value")
            if tok == "root":
                loc.root = args[0]
            elif tok == "index":
                loc.index = args
            elif tok == "autoindex":
                if args[0] not in ("on", "off"):
                    raise ConfigError(f"line {line}: autoindex must be 'on' or 'off'")
                loc.autoindex = args[0] == "on"
            elif tok == "allow_methods":
                bad = [m for m in args if m not in KNOWN_METHODS]
                if bad:
                    raise ConfigError(f"line {line}: unsupported method(s) {', '.join(bad)}")
                loc.methods = set(args)
            elif tok == "cgi_extension":
                loc.cgi_extensions = args
            elif tok == "cgi_path":
                loc.cgi_path = args[0]
            elif tok == "upload_dir":
                loc.upload_dir = args[0]
            elif tok == "client_max_body_size":
                loc.client_max_body_size = parse_size(args[0], line)
            elif tok == "return":
                if len(args) != 2 or args[0] not in ("301", "302", "303", "307", "308"):
                    raise ConfigError(f"line {line}: return needs <3xx code> <url>")
                loc.redirect = (int(args[0]), args[1])
            else:
                raise ConfigError(f"line {line}: unknown directive '{tok}' in location block")


def load_config(path: str) -> list[ServerConfig]:
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
    except OSError as e:
        raise ConfigError(f"cannot read {path}: {e.strerror}") from None
    return _Parser(tokenize(text)).parse()
