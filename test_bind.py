import socket
s = socket.socket()
s.bind(('0.0.0.0', 8000))
s.listen(1)
print('Socket listening on port 8000')
input('Presiona Enter para cerrar')