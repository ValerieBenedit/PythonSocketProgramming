import os
import socket
import sys
from pathlib import Path

BUFFER_SIZE = 4096
SERVER_FILES_DIR = Path("server_files")
SERVER_FILES_DIR.mkdir(exist_ok=True)


def safe_path(filename: str) -> Path:
    
    name = os.path.basename(filename.strip())
    if not name or name in (".", ".."):
        raise ValueError("bad filename")
    return SERVER_FILES_DIR / name


def send_status(control_socket: socket.socket, code: int, data: str = "") -> None:
     
    message = f"{code}\n\n{data}"
    control_socket.sendall(message.encode("utf-8"))


def recv_line(control_socket: socket.socket) -> str:
    data = b""
    while not data.endswith(b"\n"):
        chunk = control_socket.recv(1)
        if not chunk:
            break
        data += chunk
    return data.decode("utf-8", errors="replace").strip()


def send_over_data_socket(data_listener: socket.socket, payload: bytes) -> None:
    data_socket, _ = data_listener.accept()
    with data_socket:
        data_socket.sendall(payload)


def receive_over_data_socket(data_listener: socket.socket) -> bytes:
    data_socket, _ = data_listener.accept()
    chunks = []
    with data_socket:
        while True:
            chunk = data_socket.recv(BUFFER_SIZE)
            if not chunk:
                break
            chunks.append(chunk)
    return b"".join(chunks)


def handle_client(control_socket: socket.socket, client_address) -> None:
    username = "unknown"



    print("Connection requested. Creating data socket", flush=True)
    data_listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    data_listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    data_listener.bind(("", 0))
    data_listener.listen(5)
    data_port = data_listener.getsockname()[1]

    try:
        send_status(control_socket, 200, str(data_port))

        while True:
            raw_command = recv_line(control_socket)
            if not raw_command:
                break

            parts = raw_command.split(maxsplit=1)
            command = parts[0].lower()
            argument = parts[1] if len(parts) > 1 else ""

            if command == "login":
                username = argument.strip() or "unknown"
                print(f"Login requested by: {username}", flush=True)
                send_status(control_socket, 200)

            elif command == "list":
                print(f"List requested by {username}. Sending files.", flush=True)
                try:
                    files = sorted(p.name for p in SERVER_FILES_DIR.iterdir() if p.is_file())
                    send_status(control_socket, 200)
                    send_over_data_socket(data_listener, ", ".join(files).encode("utf-8"))
                except Exception:
                    send_status(control_socket, 500)

            elif command == "stor":
                filename = argument.strip()
                print(f"Stor {filename} requested by {username}", flush=True)
                try:
                    path = safe_path(filename)
                    incoming = receive_over_data_socket(data_listener)
                    path.write_bytes(incoming)
                    print("STOR complete", flush=True)
                    send_status(control_socket, 200)
                except Exception:
                    send_status(control_socket, 500)

            elif command == "retr":
                filename = argument.strip()
                print(f"Retr requested by {username}. Sending file: {filename}", flush=True)
                try:
                    path = safe_path(filename)
                    if not path.is_file():
                        raise FileNotFoundError(filename)
                    send_status(control_socket, 200)
                    send_over_data_socket(data_listener, path.read_bytes())
                    print("File sent.", flush=True)
                except Exception:
                    send_status(control_socket, 500)

            elif command == "dele":
                filename = argument.strip()
                print(f"Dele requested by {username}. Deleting file: {filename}", flush=True)
                try:
                    path = safe_path(filename)
                    if not path.is_file():
                        raise FileNotFoundError(filename)
                    path.unlink()
                    print("Delete complete", flush=True)
                    send_status(control_socket, 200)
                except Exception:
                    send_status(control_socket, 500)

            elif command == "quit":
                print(f"Quit requested by {username}", flush=True)
                send_status(control_socket, 200)
                break

            else:
                send_status(control_socket, 500)

    finally:
        data_listener.close()
        control_socket.close()


def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: python server.py <port>")
        sys.exit(1)

    port = int(sys.argv[1])

    print("Starting server…", flush=True)
    print("Creating server socket", flush=True)

    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind(("", port))
    server_socket.listen(5)

    print("Awaiting connections…", flush=True)

    try:
        while True:
            control_socket, client_address = server_socket.accept()
            handle_client(control_socket, client_address)
    except KeyboardInterrupt:
        pass
    finally:
        server_socket.close()


if __name__ == "__main__":
    main()
