import socket
import sys
import threading
import struct
import hashlib

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

KEY_SIZE = 2048
RSA_BLOCK = KEY_SIZE // 8
MAX_CHUNK = RSA_BLOCK - 2 * 32 - 2

server_public_key = None
client_private_key = None
client_public_key_pem = None

data_socket = None
my_username = None


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


def send_encrypted(sock, text):
    packet = encrypt(server_public_key, make_message(text))
    send_frame(sock, packet)


def recv_encrypted(sock):
    packet = recv_frame(sock)
    return check_message(decrypt(client_private_key, packet))


def listen_server():
    global data_socket
    while True:
        try:
            message = recv_encrypted(data_socket)
            print("Received encrypted message")
            
            parts = message.split("\n\n", 1)
            code = parts[0].strip()
            data = parts[1] if len(parts) > 1 else ""

            if code == "200":
                lines = data.split("\n") if data else []
                event = lines[0] if lines else ""

                if event == "login":
                    print("200 status code received. Login successful")
                elif event == "join":
                    if len(lines) > 1 and lines[1] != my_username:
                        pass  # Standard join broadcast notification
                elif event == "leave":
                    pass  # Standard leave broadcast notification
                elif event == "broadcast":
                    if len(lines) >= 3:
                        sender = lines[1]
                        text = "\n".join(lines[2:])
                        print(f"Broadcast message from {sender}: {text}")
                elif event == "private":
                    if len(lines) >= 3:
                        sender = lines[1]
                        text = "\n".join(lines[2:])
                        print(f"{sender}: {text}")
                else:
                    if data == "":
                        print("200 status code received.")
                    elif "Message sent." in data or data == "":
                        print("200 status code received. Message sent.")
                    else:
                        print(f"200 status code received. Users currently connected: {data}")
            elif code == "500":
                print("500 status code received.")

        except (ConnectionError, OSError, ValueError):
            break


def main():
    global server_public_key, client_private_key, client_public_key_pem, data_socket, my_username

    print("Starting client...")

    # Generate RSA 2048 keypair
    client_private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=KEY_SIZE,
    )
    client_public_key = client_private_key.public_key()
    client_public_key_pem = client_public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()

    connected = False

    while True:
        try:
            line = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            break

        if not line:
            continue

        parts = line.split(maxsplit=2)
        command = parts[0].lower()

        if command == "connect":
            if len(parts) < 3:
                continue

            server_ip = parts[1]
            server_port = int(parts[2])

            # Create a listener socket for the callback from the server
            callback_listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            callback_listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            callback_listener.bind(("0.0.0.0", 0))
            callback_listener.listen(1)
            callback_port = callback_listener.getsockname()[1]

            # Get local IP relative to server connection
            temp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                temp_sock.connect((server_ip, server_port))
                my_ip = temp_sock.getsockname()[0]
            except Exception:
                my_ip = "127.0.0.1"
            finally:
                temp_sock.close()

            # Send connect request to server control port
            control_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            control_socket.connect((server_ip, server_port))
            connect_msg = f"connect {my_ip} {callback_port}"
            control_socket.sendall(connect_msg.encode())
            control_socket.close()

            # Receive response on callback listener
            client_callback, _ = callback_listener.accept()
            reply = recv_frame(client_callback).decode()
            client_callback.close()
            callback_listener.close()

            lines = reply.split("\n")
            if lines[0] == "200":
                data_port = int(lines[1])
                server_pem = "\n".join(lines[2:])
                server_public_key = serialization.load_pem_public_key(server_pem.encode())

                # Connect to server's DATA PORT
                data_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                data_socket.connect((server_ip, data_port))

                connected = True
                print(f"200 status code received. Starting data connection on port {data_port}")

                # Start receiving loop thread
                threading.Thread(target=listen_server, daemon=True).start()

        elif command == "login" and connected:
            if len(parts) < 2:
                continue
            my_username = parts[1]
            msg = f"login\n{my_username}\n{client_public_key_pem}"
            send_encrypted(data_socket, msg)

        elif command == "who" and connected:
            send_encrypted(data_socket, "who")

        elif command == "broadcast" and connected:
            text = line[len("broadcast"):].strip()
            msg = f"broadcast\n{text}"
            send_encrypted(data_socket, msg)

        elif command == "private" and connected:
            subparts = line.split(maxsplit=2)
            if len(subparts) < 3:
                continue
            target = subparts[1]
            text = subparts[2]
            msg = f"private\n{target}\n{text}"
            send_encrypted(data_socket, msg)

        elif command == "quit" and connected:
            send_encrypted(data_socket, "quit")
            break


if __name__ == "__main__":
    main()