## Development

This documentation provides a high level overview of the project structure. For details, please refer to the inline documentations in relevant source files.

### Protocol Implementation

Relevant source code is in [src/tom/](../src/tom/).

* Models
    * [`Credential`](../src/tom/credential.py) is a model for email login credentials, currently specific for SMTP and IMAP.
    * [`Endpoint`](../src/tom/endpoint.py) is a model for Mail.im endpoint, comprising address and port.
    * [`SocketContext`](../src/tom/_mailbox/socket_context.py) is a model for internal data structures of sockets.
    * [`EpollContext`](../src/tom/_mailbox/epoll_context.py) is a model for internal data structures of epoll objects.
* [`Socket`](../src/tom/socket.py) provides socket interfaces for applications, which are implemented inside `Mailbox`.
* [`Epoll`](../src/tom/epoll.py) provides epoll interfaces for applications, which are implemented inside `Mailbox`.
* Mailbox
    * [`Mailbox`](../src/tom/_mailbox/mailbox.py) provides mailbox interface for applications, which is a composition of multiple classes below.
    * [`MailboxBase`](../src/tom/_mailbox/mailbox_base.py) maintains core data structures if mailbox.
    * [`MailboxSocketInterface`](../src/tom/_mailbox/mailbox_socket_interface.py) implements socket related interfaces.
    * [`MailboxEpollInterface`](../src/tom/_mailbox/mailbox_epoll_interface.py) implements epoll related interfaces.
    * [`MailboxListener`](../src/tom/_mailbox/mailbox_listener.py) manages process of incoming emails.
    * [`MailboxTasks`](../src/tom/_mailbox/mailbox_tasks.py) manages sending emails and scheduling tasks.
* Packet
    * [`Packet`](../src/tom/_mailbox/packet/packet.py) is the base class of `PlainPacket` and `SecurePacket`.
    * [`PlainPacket`](../src/tom/_mailbox/packet/plain_packet.py) manages email encoding and decoding for non-secure connections.
    * [`SecurePacket`](../src/tom/_mailbox/packet/secure_packet.py) manages email encoding and decoding for secure connections, as well as provides encryption and decryption interfaces.

### Key Storage

Relevant source code is in [src/key/](../src/key/).

* Models
    * [`Keys`](../src/key/keys.py) is a model for data in the storage.
* [`EncryptedFile`](../src/key/encrypted_file.py) provides a general purpose encrypted storage in files.
* [`KeyStore`](../src/key/key_store.py) provides a Mail.im specific interfaces on top of `EncryptedFile`.
