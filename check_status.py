import socket, json

HOST, PORT = "192.168.100.167", 8000

# Build a JSON-RPC “status” request
request = {
    "jsonrpc": "2.0",
    "method": "status",
    "id": "status"
}
payload = (json.dumps(request) + "\n").encode()

with socket.create_connection((HOST, PORT), timeout=5) as sock:
    sock.sendall(payload)
    # Read the response (adjust buffer size if needed)
    response = sock.recv(4096).decode()
    print("Server replied:", response)
