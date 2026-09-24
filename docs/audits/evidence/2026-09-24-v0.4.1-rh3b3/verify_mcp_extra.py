from chstockdata.mcp_server import build_server

server = build_server()
assert server is not None
print(f"mcp_server={type(server).__name__}")
