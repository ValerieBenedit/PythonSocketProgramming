CNT4713 - Chat Project 3: Encrypted Chat

Group Members
-------------
Name: Valerie Daniela    Panther ID: 6106442
Name: Nicolas Cancino    Panther ID: 6300609
Name: Maiko Patiag       Panther ID: 6539756

Files Submisson
---------------
server.py - TCP encrypted chat server (authored by Nicolas)
client.py - TCP encrypted clients (authored by Valerie)
answers.txt, README.md - Written answers to the project questions and file (authored by Maiko)

Requirements
------------
- Python 3.8 or latest version
- The cryptography library required: pip install cryptography
- Program use RSA-2048 with OAEP/SHA-256 padding encryption

Notes
-----
- Everything from "login" onward is secured through encryption. The "connect" phase begins with an exchange of the data port and the server's public key, ensuruing both parties posses the necesssary keys.
- All processes should be executed on the same machine or within the same local network without a firewall interference. Follwing the "connect" step, the server establishes a brief connection to the client's callback port to send the data port and its publi key.
- Each message contains a SHA-256 hash that the recipient checks after decryption.

Video
-----
Link: https://www.youtube.com/watch?v=5Vg0MAeF2vA
