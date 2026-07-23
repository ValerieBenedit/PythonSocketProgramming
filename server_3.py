import socket
import sys
import threading
import struct
import hashlib

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa


HOST = "0.0.0.0"
clients = {}
lock = threading.Lock()

KEY_SIZE = 2048
RSA_BLOCK = KEY_SIZE // 8
MAX_CHUNK = RSA_BLOCK - 2 * 32 - 2


def recv_exact(sock, size):
    data = b""
    while len(data) < size:
        part = sock.recv(size - len(data))
        if not part:
            raise ConnectionError
        data += part
    return data


def send_frame(sock, data):
    sock.sendall(struct.pack("!I", len(data)) + data)


def recv_frame(sock):
    size = struct.unpack("!I", recv_exact(sock, 4))[0]
    return recv_exact(sock, size)


def encrypt(public_key, text):
    raw = text.encode()
    chunks = [raw[i:i + MAX_CHUNK] for i in range(0, len(raw), MAX_CHUNK)] or [b""]

    result = struct.pack("!I", len(chunks))
    for chunk in chunks:
        result += public_key.encrypt(
            chunk,
            padding.OAEP(
                mgf=padding.MGF1(hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None,
            ),
        )
    return result


def decrypt(private_key, data):
    count = struct.unpack("!I", data[:4])[0]
    raw = b""
    offset = 4

    for _ in range(count):
        block = data[offset:offset + RSA_BLOCK]
        offset += RSA_BLOCK
        raw += private_key.decrypt(
            block,
            padding.OAEP(
                mgf=padding.MGF1(hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None,
            ),
        )

    return raw.decode()


def make_message(text):
    digest = hashlib.sha256(text.encode()).hexdigest()
    return digest + "\n" + text


def check_message(text):
    digest, message = text.split("\n", 1)
    expected = hashlib.sha256(message.encode()).hexdigest()

    if digest != expected:
        raise ValueError("Invalid hash")

    return message


def send_encrypted(client, text):
    packet = encrypt(client["key"], make_message(text))
    send_frame(client["socket"], packet)


def recv_encrypted(sock, private_key):
    packet = recv_frame(sock)
    return check_message(decrypt(private_key, packet))


def response(code, data=""):
    if data:
        return f"{code}\n\n{data}"
    return f"{code}\n"


def broadcast(text):
    with lock:
        current_clients = list(clients.values())

    for client in current_clients:
        try:
            send_encrypted(client, text)
        except OSError:
            pass


def remove_client(username):
    with lock:
        client = clients.pop(username, None)

    if client:
        try:
            client["socket"].close()
        except OSError:
            pass

        broadcast(response(200, f"leave\n{username}"))


def handle_client(data_socket, private_key):
    username = None

    try:
        while True:
            print("Received encrypted message")
            message = recv_encrypted(data_socket, private_key)
            lines = message.split("\n")
            command = lines[0].lower()

            if command == "login":
                if len(lines) < 3:
                    break

                requested_name = lines[1].strip()
                public_key_text = "\n".join(lines[2:])
                public_key = serialization.load_pem_public_key(public_key_text.encode())

                with lock:
                    if requested_name in clients:
                        temp_client = {"socket": data_socket, "key": public_key}
                        send_encrypted(temp_client, response(500))
                        break

                    username = requested_name
                    clients[username] = {
                        "socket": data_socket,
                        "key": public_key,
                    }

                print(f"Login requested by: {username}")
                send_encrypted(clients[username], response(200, "login"))
                broadcast(response(200, f"join\n{username}"))

            elif command == "who" and username:
                print("Who requested. Sending users.")

                with lock:
                    names = ", ".join(sorted(clients.keys()))

                send_encrypted(clients[username], response(200, names))

            elif command == "broadcast" and username:
                if len(lines) < 2:
                    send_encrypted(clients[username], response(500))
                    continue

                text = "\n".join(lines[1:])
                print(f"Broadcast requested by {username}")
                print(f"Message: {text}")
                broadcast(response(200, f"broadcast\n{username}\n{text}"))

            elif command == "private" and username:
                if len(lines) < 3:
                    send_encrypted(clients[username], response(500))
                    continue

                target_name = lines[1]
                text = "\n".join(lines[2:])

                with lock:
                    target = clients.get(target_name)

                if not target:
                    send_encrypted(clients[username], response(500))
                    continue

                print(f"Private message from {username} to {target_name}")
                send_encrypted(
                    target,
                    response(200, f"private\n{username}\n{text}"),
                )
                send_encrypted(clients[username], response(200))

            elif command == "quit" and username:
                print(f"Quit requested by {username}")
                send_encrypted(clients[username], response(200))
                break

            elif username:
                send_encrypted(clients[username], response(500))

    except (ConnectionError, OSError, ValueError):
        pass
    finally:
        if username:
            remove_client(username)
        else:
            data_socket.close()


def accept_data_connection(data_listener, private_key):
    try:
        data_socket, _ = data_listener.accept()
        handle_client(data_socket, private_key)
    finally:
        data_listener.close()


def handle_control(control_socket, private_key, public_key_pem):
    try:
        command = control_socket.recv(4096).decode().strip().split()

        if len(command) != 3 or command[0].lower() != "connect":
            return

        client_ip = command[1]
        client_port = int(command[2])

        print("Connection requested. Creating data socket")

        data_listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        data_listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        data_listener.bind((HOST, 0))
        data_listener.listen(1)

        data_port = data_listener.getsockname()[1]

        callback = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        callback.connect((client_ip, client_port))

        connect_reply = f"200\n{data_port}\n{public_key_pem}"
        send_frame(callback, connect_reply.encode())
        callback.close()

        threading.Thread(
            target=accept_data_connection,
            args=(data_listener, private_key),
            daemon=True,
        ).start()

    except (OSError, ValueError):
        pass
    finally:
        control_socket.close()


def main():
    if len(sys.argv) != 2:
        print("Usage: python server.py <CONTROL PORT>")
        return

    control_port = int(sys.argv[1])

    print("Starting server…")
    print("Creating RSA keypair")

    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=KEY_SIZE,
    )
    public_key = private_key.public_key()

    public_key_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()

    print("RSA keypair created")
    print("Creating server socket")

    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind((HOST, control_port))
    server_socket.listen()

    print("Awaiting connections…")

    while True:
        control_socket, _ = server_socket.accept()

        threading.Thread(
            target=handle_control,
            args=(control_socket, private_key, public_key_pem),
            daemon=True,
        ).start()


if __name__ == "__main__":
    main()
