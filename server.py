import socket
import sys
import threading

clients_lock = threading.Lock()
clients = {}  # username -> {control, data, addr}
control_to_user = {}


def make_response(code, *lines):
    if lines:
        return (str(code) + "\n" + "\n".join(lines) + "\n").encode()
    return (str(code) + "\n").encode()


def send_data(sock, code, *lines):
    try:
        sock.sendall(make_response(code, *lines))
        return True
    except Exception:
        return False


def broadcast_to_all(code, *lines, exclude=None):
    with clients_lock:
        targets = [(u, info["data"]) for u, info in clients.items() if u != exclude]
    for _, dsock in targets:
        send_data(dsock, code, *lines)


def remove_client(control_sock):
    username = None
    with clients_lock:
        username = control_to_user.pop(control_sock, None)
        info = clients.pop(username, None) if username else None
    if info:
        try:
            info["data"].close()
        except Exception:
            pass
    try:
        control_sock.close()
    except Exception:
        pass
    if username:
        broadcast_to_all(200, "quit", username)


def client_thread(control_sock, address):
    data_sock = None
    try:
        file = control_sock.makefile("r", encoding="utf-8", newline="\n")
        for raw in file:
            command_line = raw.rstrip("\n")
            if not command_line:
                continue
            parts = command_line.split(" ", 2)
            command = parts[0].lower()

            if command == "connect":
                print("Connection requested. Creating data socket", flush=True)
                try:
                    _, client_ip, client_port = command_line.split(" ", 2)
                    client_port = int(client_port)
                    data_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    data_sock.connect((client_ip, client_port))
                    local_data_port = data_sock.getsockname()[1]
                    control_sock.sendall(make_response(200, str(local_data_port)))
                except Exception:
                    try:
                        control_sock.sendall(make_response(500))
                    except Exception:
                        pass

            elif command == "login":
                username = command_line[6:].strip() if len(command_line) > 5 else ""
                print(f"Login requested by: {username}", flush=True)
                if not username or data_sock is None:
                    send_data(data_sock if data_sock else control_sock, 500)
                    continue
                with clients_lock:
                    if username in clients:
                        ok = False
                    else:
                        clients[username] = {"control": control_sock, "data": data_sock, "addr": address}
                        control_to_user[control_sock] = username
                        ok = True
                if ok:
                    send_data(data_sock, 200)
                    broadcast_to_all(200, "join", username, exclude=username)
                else:
                    send_data(data_sock, 500)

            elif command == "who":
                print("Who requested. Sending users.", flush=True)
                with clients_lock:
                    username = control_to_user.get(control_sock)
                    users = ", ".join(clients.keys())
                    dsock = clients.get(username, {}).get("data")
                if dsock:
                    send_data(dsock, 200, users)

            elif command == "broadcast":
                message = command_line[len("broadcast"):].strip()
                with clients_lock:
                    username = control_to_user.get(control_sock)
                    dsock = clients.get(username, {}).get("data")
                if not username or not dsock:
                    if data_sock:
                        send_data(data_sock, 500)
                    continue
                print(f"Broadcast requested by {username}", flush=True)
                print(f"Message: {message}", flush=True)
                broadcast_to_all(200, "Broadcast", username, message)

            elif command == "private":
                rest = command_line[len("private"):].strip()
                if " " in rest:
                    recipient, message = rest.split(" ", 1)
                else:
                    recipient, message = rest, ""
                with clients_lock:
                    sender = control_to_user.get(control_sock)
                    sender_sock = clients.get(sender, {}).get("data") if sender else None
                    recipient_sock = clients.get(recipient, {}).get("data")
                print(f"Private message from {sender} to {recipient}", flush=True)
                if sender and recipient_sock:
                    send_data(recipient_sock, 200, "Private", sender, message)
                    if sender_sock:
                        send_data(sender_sock, 200)
                else:
                    if sender_sock:
                        send_data(sender_sock, 500)

            elif command == "quit":
                with clients_lock:
                    username = control_to_user.get(control_sock)
                    dsock = clients.get(username, {}).get("data") if username else data_sock
                print(f"Quit requested by {username if username else address[0]}", flush=True)
                if dsock:
                    send_data(dsock, 200)
                remove_client(control_sock)
                break

            else:
                with clients_lock:
                    username = control_to_user.get(control_sock)
                    dsock = clients.get(username, {}).get("data") if username else data_sock
                if dsock:
                    send_data(dsock, 500)
    except Exception:
        remove_client(control_sock)


def main():
    if len(sys.argv) != 2:
        print("Usage: python server.py <port>")
        return
    port = int(sys.argv[1])
    print("Starting server…", flush=True)
    print("Creating server socket", flush=True)
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind(("", port))
    server_socket.listen(20)
    print("Awaiting connections…", flush=True)
    try:
        while True:
            control_sock, address = server_socket.accept()
            threading.Thread(target=client_thread, args=(control_sock, address), daemon=True).start()
    except KeyboardInterrupt:
        pass
    finally:
        server_socket.close()


if __name__ == "__main__":
    main()
