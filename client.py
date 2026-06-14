import socket
import sys
import threading


running = True

def handle_data_stream(data_sock):
    """
    Background thread to listen continuously for incoming data/messages 
    sent from the server's DATA PORT.
    """
    global running
    try:
        
        file = data_sock.makefile("r", encoding="utf-8", newline="\n")
        while running:
            status_line = file.readline()
            if not status_line:
                break
            
            status_code = status_line.rstrip("\n")
            if not status_code:
                continue

            empty_line = file.readline()

            message_type_line = file.readline()
            if not message_type_line:
                print(f"{status_code} status code received.")
                continue
                
            message_type = message_type_line.rstrip("\n")

            if message_type == "join":
                username = file.readline().rstrip("\n")

            elif message_type == "quit":
                username = file.readline().rstrip("\n")

            elif message_type == "Broadcast":
                sender = file.readline().rstrip("\n")
                msg_body = file.readline().rstrip("\n")
                print(f"{status_code} status code received.")
                print(f"Broadcast message from {sender}: {msg_body}")

            elif message_type == "Private":
                sender = file.readline().rstrip("\n")
                msg_body = file.readline().rstrip("\n")
                print(f"{status_code} status code received.")
                print(f"{sender}: {msg_body}")
            else:
                print(f"{status_code} status code received. Users currently connected: {message_type}")
    except Exception:
        pass
    finally:
        try:
            data_sock.close()
        except:
            pass

def main():
    global running
    print("Starting client...")
    
    control_sock = None
    data_sock = None
    listen_sock = None
    data_thread = None

    try:
        while running:
            try:
                user_input = input("> ").strip()
            except (EOFError, KeyboardInterrupt):
                break

            if not user_input:
                continue

            parts = user_input.split(" ", maxsplit=2)
            command = parts[0].lower()

            if command == "connect":
                if control_sock:
                    print("Already connected.")
                    continue
                if len(parts) < 3:
                    print("Usage: connect <ip> <port>")
                    continue
                
                target_ip = parts[1]
                try:
                    target_port = int(parts[2])
                except ValueError:
                    print("Port must be an integer.")
                    continue

                try:
                    control_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    control_sock.connect((target_ip, target_port))
                    
                    listen_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    listen_sock.bind(("", 0)) 
                    local_listen_port = listen_sock.getsockname()[1]
                    listen_sock.listen(1)

                    my_local_ip = control_sock.getsockname()[0]
                    handshake = f"connect {my_local_ip} {local_listen_port}\n"
                    control_sock.sendall(handshake.encode())

                    data_sock, _ = listen_sock.accept()
                    listen_sock.close()

                    control_file = control_sock.makefile("r", encoding="utf-8", newline="\n")
                    status_code = control_file.readline().rstrip("\n")
                    _ = control_file.readline() # Empty space line
                    server_data_port = control_file.readline().rstrip("\n")

                    if status_code == "200":
                        print(f"200 status code received. Starting data connection on port {server_data_port}")
                        data_thread = threading.Thread(target=handle_data_stream, args=(data_sock,), daemon=True)
                        data_thread.start()
                    else:
                        print(f"{status_code} status code received. Connection failed.")
                        control_sock.close()
                        control_sock = None
                except Exception as e:
                    print(f"500 Connection failed: {e}")
                    if control_sock: control_sock.close(); control_sock = None
                    if listen_sock: listen_sock.close()

            elif command == "login":
                if not control_sock:
                    print("Error: Connect to server first.")
                    continue
                control_sock.sendall((user_input + "\n").encode())
                print("200 status code received. Login successful")

            elif command == "who":
                if not control_sock:
                    print("Error: Connect to server first.")
                    continue
                control_sock.sendall((user_input + "\n").encode())

            elif command == "broadcast":
                if not control_sock:
                    print("Error: Connect to server first.")
                    continue
                control_sock.sendall((user_input + "\n").encode())

            elif command == "private":
                if not control_sock:
                    print("Error: Connect to server first.")
                    continue
                control_sock.sendall((user_input + "\n").encode())

            elif command == "quit":
                running = False
                if control_sock:
                    try:
                        control_sock.sendall("quit\n".encode())
                    except:
                        pass
                print("200 status code received.")
                break

            else:
                if control_sock:
                    control_sock.sendall((user_input + "\n").encode())
                else:
                    print("Unknown command.")

    finally:
        running = False
        if control_sock:
            try: control_sock.close()
            except: pass
        if data_sock:
            try: data_sock.close()
            except: pass

if __name__ == "__main__":
    main()