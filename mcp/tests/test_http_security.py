"""Streamable-HTTP mode: Host-header (DNS-rebinding) protection stays on and security headers are set."""
import os, socket, subprocess, sys, time, urllib.request, urllib.error
import pytest

def _free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p

@pytest.fixture(scope="module")
def server():
    port = _free_port()
    env = {**os.environ, "SJRWMD_MCP_TRANSPORT": "streamable-http", "SJRWMD_MCP_HOST": "127.0.0.1",
           "SJRWMD_MCP_PORT": str(port), "SJRWMD_MCP_ALLOWED_HOSTS": "mcp.example.org"}
    p = subprocess.Popen([sys.executable, "-m", "sjrwmd_mcp.server"], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(100):
        try: socket.create_connection(("127.0.0.1", port), 0.2).close(); break
        except OSError: time.sleep(0.1)
    yield port
    p.terminate(); p.wait(10)

INIT = b'{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"t","version":"0"}}}'

def _post(port, host):
    req = urllib.request.Request(f"http://127.0.0.1:{port}/mcp", data=INIT, method="POST", headers={
        "Host": host, "Content-Type": "application/json", "Accept": "application/json, text/event-stream"})
    try:
        r = urllib.request.urlopen(req, timeout=10); return r.status, r.headers
    except urllib.error.HTTPError as e:
        return e.code, e.headers

def test_allowed_hosts(server):
    for host in (f"127.0.0.1:{server}", "mcp.example.org"):
        status, headers = _post(server, host)
        assert status == 200, host
        assert headers["X-Content-Type-Options"] == "nosniff"
        assert "frame-ancestors 'none'" in headers["Content-Security-Policy"]

def test_rebinding_host_rejected(server):
    status, _ = _post(server, "evil.example.com")
    assert status == 421 or status == 400
