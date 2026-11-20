"""Hot-reload through the local Codex app server's Unix WebSocket (Linux)."""
import base64
import hashlib
import json
import os
import socket
import struct
import sys
import time


def handshake(sock, reader):
    key = base64.b64encode(os.urandom(16)).decode()
    request = ("GET / HTTP/1.1\r\nHost: localhost\r\nUpgrade: websocket\r\n"
               f"Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\n"
               "Sec-WebSocket-Version: 13\r\n\r\n")
    sock.sendall(request.encode())
    expected = base64.b64encode(hashlib.sha1(
        (key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode()).digest())
    headers = []
    while len(headers) < 32:
        line = reader.readline(4096)
        if line == b"\r\n":
            break
        if not line:
            raise ConnectionError("App server disconnected during handshake")
        headers.append(line)
    if not headers or b"101 Switching Protocols" not in headers[0] or not any(
        h.lower().startswith(b"sec-websocket-accept:") and h.split(b":", 1)[1].strip() == expected
        for h in headers[1:]
    ):
        raise ConnectionError("Invalid app-server WebSocket handshake")


def send(sock, data, opcode=1):
    size = len(data)
    extension = b"" if size < 126 else struct.pack(">H", size)
    mask = os.urandom(4)
    masked = bytes(value ^ mask[index % 4] for index, value in enumerate(data))
    sock.sendall(bytes([128 | opcode, 128 | min(size, 126)]) + extension + mask + masked)


def receive(sock, reader):
    body = bytearray()
    until = time.monotonic() + 12
    while time.monotonic() < until:
        header = reader.read(2)
        if len(header) != 2:
            raise ConnectionError("Disconnected from app server")
        size = header[1] & 127
        if size == 126:
            size = struct.unpack(">H", reader.read(2))[0]
        elif size == 127:
            size = struct.unpack(">Q", reader.read(8))[0]
        if len(body) + size > 24 * 1024 * 1024 or header[1] & 128:
            raise ConnectionError("Invalid app-server frame")
        data = reader.read(size)
        opcode = header[0] & 15
        if opcode == 9:
            send(sock, data, opcode=10)
        elif opcode != 10:
            if opcode not in (0, 1):
                raise ConnectionError("Unexpected app-server frame")
            body.extend(data)
            if header[0] & 128:
                return json.loads(body)
    raise TimeoutError("App-server frame timed out")


def refresh(path, mode):
    if mode not in {"install", "uninstall"}:
        raise ValueError("Expected install or uninstall")
    with socket.socket(socket.AF_UNIX) as sock, sock.makefile("rb") as reader:
        sock.settimeout(10)
        sock.connect(path)
        peer = sock.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12)
        if struct.unpack("3i", peer)[1] != os.getuid():
            raise ConnectionError("Unexpected app-server socket owner")
        handshake(sock, reader)
        request_id = 0

        def call(method, params):
            nonlocal request_id
            request_id += 1
            send(sock, json.dumps(dict(method=method, id=request_id, params=params)).encode())
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                response = receive(sock, reader)
                if response.get("id") == request_id:
                    if "error" in response:
                        raise RuntimeError(f"App server rejected {method}")
                    return response["result"]
            raise TimeoutError(f"Timed out waiting for {method}")

        call("initialize", {"clientInfo": {"name": "learning_installer", "version": "1.0"},
                            "capabilities": {"experimentalApi": True}})
        send(sock, b'{"method":"initialized"}')
        if call("config/batchWrite", {"edits": [], "reloadUserConfig": True})["status"] != "ok":
            raise RuntimeError("App server did not reload config")
        threads = call("thread/loaded/list", {})["data"]
        for thread in threads:
            entry = call("hooks/list", {"threadId": thread})["data"][0]
            hooks = [h for h in entry["hooks"] if "codex-learning/learn.py hook" in h.get("command", "")]
            expected = 4 if mode == "install" else 0
            if len(hooks) != expected or any(
                h["trustStatus"] != "trusted" or not h["enabled"] for h in hooks
            ):
                raise RuntimeError("Hook verification failed in loaded thread " + thread)
        print("Refreshed and verified hook configuration in", len(threads), "loaded threads.")


if __name__ == "__main__":
    refresh(*sys.argv[1:])
