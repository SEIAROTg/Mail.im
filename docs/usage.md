## Usage

This documentation provides a list of example usages of Mail.im.

### Initialize Mailbox

```python
from mailim.tom import Mailbox, Credential

smtp = Credential(host, port, username, password)
imap = Credential(host, port, username, password)

mailbox = Mailbox(smtp, imap)
```

### Connect

```python
from mailim.tom import Socket, Endpoint

socket = Socket(mailbox)
socket.connect(Endpoint('foo@local', 'foo'), Endpoint('bar@remote', 'bar'))
```

### Listen

```python
from mailim.tom import Socket

socket_listen = Socket(mailbox)
socket_listen.listen(Endpoint('bar@remote', 'bar'))
socket = socket_listen.accept(lambda local, remote, secure: local == Endpoint('bar@remote', 'bar') and\
                                                            remote == Endpoint('foo@local', 'foo'))
```

### Send Data

```python
socket.send(b'foo')
socket.send(b'bar')
socket.send(b'baz')
socket.send(b'qux')
```

### Receive Data

```python
socket.recv_exact(6)  # b'foobar'
socket.recv(6)        # may be any non-empty prefix of b'bazqux'
```

### Dump Connection 

```python
socket.shutdown()
dump = socket.dump()
socket.close()
# store dump somewhere
```

### Restore Connection

```python
socket = Socket.restore(dump)
```

### Epoll

```python
from mailim.tom import Epoll

epoll = Epoll(mailbox)
epoll.add({socket}, set())  # poll for read
epoll.wait()
socket.recv(1000)  # never blocks
epoll.remove({socket}, set())  # stop polling for read
epoll.add(set(), {socket})  # poll for exception
epoll.wait()
# socket has been shut down here
epoll.close()
```
