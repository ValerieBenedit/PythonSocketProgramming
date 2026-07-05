import os
import socket
import sys
from pathlib import Path

BUFFER_SIZE = 4096


def parse_response(control_socket: socket.socket):
    """
    Parses responses from the server matching the f"{code}\n\n{data}" protocol.
    """
    try:
        data = control_socket.recv(BUFFER_SIZE)
    except Exception:
        return 500, ""

    if not data:
        return 500, ""
        
    decoded = data.decode("utf-8", errors="replace")
    
    if "\n\n" in decoded:
        parts = decoded.split("\n\n", 1)
        try:
            code = int(parts[0].strip())
        except ValueError:
            code = 500
        extra_data = parts[1].strip()
        return code, extra_data
    else:
        # Fallback if formatting doesn't match
        try:
            code = int(decoded.strip())
            return code, ""
        except ValueError:
            return 500, ""


def connect_data_socket(server_host: str, data_port: int) -> socket.socket:
    """Helper to spin up a connection to the data port for transfers."""
    data_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    data_socket.connect((server_host, data_port))
    return data_socket


def main():
    if len(sys.argv) != 4:
        print("Usage: python client.py <server_host> <server_port> <username>")
        sys.exit(1)

    host = sys.argv[1]
    control_port = int(sys.argv[2])
    username = sys.argv[3]

    print(f"Connecting to server {host}:{control_port}...")
    control_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    
    try:
        control_socket.connect((host, control_port))
        
        code, data_port_str = parse_response(control_socket)
        if code != 200 or not data_port_str.strip():
            print("Failed to initialize session with server.")
            return
        
        data_port = int(data_port_str.strip())
        print(f"Connected. Data port established at: {data_port}")

        control_socket.sendall(f"login {username}\n".encode("utf-8"))
        code, _ = parse_response(control_socket)
        if code == 200:
            print(f"Logged in successfully as '{username}'.")
        else:
            print("Login failed.")
            return

        while True:
            try:
                user_input = input("ftp> ").strip()
            except (KeyboardInterrupt, EOFError):
                user_input = "quit"

            if not user_input:
                continue

            parts = user_input.split(maxsplit=1)
            command = parts[0].lower()
            argument = parts[1] if len(parts) > 1 else ""

            if command == "quit":
                control_socket.sendall(b"quit\n")
                parse_response(control_socket)
                print("Goodbye!")
                break

            elif command == "list":
                control_socket.sendall(b"list\n")
                code, _ = parse_response(control_socket)
                
                if code == 200:
                    with connect_data_socket(host, data_port) as data_socket:
                        chunks = []
                        while True:
                            chunk = data_socket.recv(BUFFER_SIZE)
                            if not chunk:
                                break
                            chunks.append(chunk)
                        files_list = b"".join(chunks).decode("utf-8")
                        print(f"Server Files:\n{files_list}")
                else:
                    print("500: Failed to fetch directory list.")

            elif command == "stor":
                if not argument:
                    print("Usage: stor <filename>")
                    continue
                
                local_path = Path(argument)
                if not local_path.is_file():
                    print(f"Local file '{argument}' does not exist.")
                    continue
                control_socket.sendall(f"stor {argument}\n".encode("utf-8"))
                
                try:
                    file_bytes = local_path.read_bytes()
                    with connect_data_socket(host, data_port) as data_socket:
                        data_socket.sendall(file_bytes)

                    code, _ = parse_response(control_socket)
                    if code == 200:
                        print("200: File successfully uploaded.")
                    else:
                        print("500: Server failed to store the file.")
                except Exception as e:
                    print(f"Error during transfer: {e}")

            elif command == "retr":
                if not argument:
                    print("Usage: retr <filename>")
                    continue

                control_socket.sendall(f"retr {argument}\n".encode("utf-8"))
                code, _ = parse_response(control_socket)
                
                if code == 200:
                    with connect_data_socket(host, data_port) as data_socket:
                        chunks = []
                        while True:
                            chunk = data_socket.recv(BUFFER_SIZE)
                            if not chunk:
                                break
                            chunks.append(chunk)
                    out_path = Path(os.path.basename(argument))
                    out_path.write_bytes(b"".join(chunks))
                    print(f"200: File downloaded successfully as '{out_path}'.")
                else:
                    print("500: File not found or failed to fetch from server.")

            elif command == "dele":
                if not argument:
                    print("Usage: dele <filename>")
                    continue

                control_socket.sendall(f"dele {argument}\n".encode("utf-8"))
                code, _ = parse_response(control_socket)
                if code == 200:
                    print("200: File deleted successfully from server.")
                else:
                    print("500: Failed to delete file (or file doesn't exist).")

            else:
                print("Unknown command. Supported: list, stor, retr, dele, quit")

    except ConnectionRefusedError:
        print("Could not connect to the server. Make sure it is running.")
    finally:
        control_socket.close()


if __name__ == "__main__":
    main()