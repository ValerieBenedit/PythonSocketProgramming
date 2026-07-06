CNT4713 - File Transfer Project

Group Members
-------------
Name: Valerie Daniela   ID: 6106442

Name: Nicolas Cancino   ID: 6300609

Name: Maiko Patiag      ID: 6539756


Files Submitted
---------------
server.py   - TCP file transfer server (authored by Nicolas)
client.py   - TCP file transfer client (authored by Valerie)
readme.txt  - This file (authored by Maiko)


Video
-----
Link: https://youtu.be/ZvlI9VjsD3U

Notes
-----
- Python 3, no external libraries needed.
- Start the server before the client.
- Run server: python3 server.py 8991
- Run client: python3 client.py
- Once the client is running, use these commands at the ">" prompt:
    connect <127.0.0.1> <8991>
    login <alice>
    list
    stor <myfile.txt>
    retr <myfile.txt>
    dele <myfile.txt>
    quit
