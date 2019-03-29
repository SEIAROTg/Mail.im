#!/usr/bin/env python

from typing import Dict, Optional
import uuid
import os
import asyncio
import threading
from aiohttp import web
from src.tom import Mailbox, Socket, Credential, Endpoint, Epoll
from src.key import KeyStore
from xeddsa.implementations.xeddsa25519 import XEdDSA25519


class Conversation:
    status: str = 'init'
    websocket: web.WebSocketResponse
    mailbox: Optional[Mailbox] = None
    sockets: Optional[Dict[str, Socket]] = None
    store: Optional[KeyStore] = None
    address: Optional[str] = None
    epoll: Optional[Epoll] = None
    socket_listener: Optional[Socket] = None
    mutex: Optional[threading.RLock] = None
    thread: Optional[threading.Thread] = None

    def __init__(self, websocket):
        self.mutex = threading.RLock()
        self.websocket = websocket

    async def loop(self):
        try:
            while True:
                msg = await self.websocket.receive_json()
                with self.mutex:
                    if msg['type'] == 'join':
                        await self.join(msg['address'])
                    elif self.status == 'login':
                        if msg['type'] == 'login':
                            await self.login(msg['master_key'])
                    elif self.status == 'register':
                        if msg['type'] == 'register':
                            await self.register(msg['credentials'])
                    elif self.status == 'joined':
                        if msg['type'] == 'send':
                            await self.send(msg['address'], msg['msg'])
                        elif msg['type'] == 'add_contact':
                            await self.add_contact(msg['address'])
        except Exception as e:
            print(e)
        finally:
            if self.mailbox is not None:
                for socket in self.sockets.values():
                    socket.shutdown()
                    dump = socket.dump()
                    self.store.set_socket_context(socket.endpoints, dump)
                    socket.close()
                self.mailbox.close()

    async def join(self, address):
        path = os.path.join('stores', address)
        os.makedirs('stores', exist_ok=True)
        self.address = address
        self.store = KeyStore(path)
        if os.path.isfile(path):
            self.status = 'login'
            await self.websocket.send_json({'type': 'status', 'status': 'login'})
        else:
            self.status = 'register'
            await self.websocket.send_json({'type': 'status', 'status': 'register'})

    async def login(self, master_key):
        try:
            self.store.unlock(master_key)
            smtp = self.store.get_email_credential('smtp')
            imap = self.store.get_email_credential('imap')
            self.mailbox = Mailbox(smtp, imap)
            await self.init_mailbox()
            for dump in self.store.get_socket_contexts().values():
                socket = Socket.restore(self.mailbox, dump)
                self.epoll.add({socket}, {socket})
                self.sockets[socket.endpoints[1].address] = socket
            self.status = 'joined'
            await self.websocket.send_json({'type': 'status', 'status': 'joined'})
            await self.websocket.send_json({'type': 'contacts', 'contacts': [remote.address for local, remote in self.store.get_socket_contexts().keys()]})
        except ValueError:
            await self.websocket.send_json({'type': 'error', 'msg': 'incorrect master key'})

    async def register(self, credentials):
        self.store.initialize(credentials['master_key'])
        smtp = Credential(**credentials['smtp'])
        imap = Credential(**credentials['imap'])
        self.mailbox = Mailbox(smtp, imap)
        await self.init_mailbox()
        self.store.set_email_credential('smtp', smtp)
        self.store.set_email_credential('imap', imap)
        own_priv = XEdDSA25519.generate_mont_priv()
        self.store.set_user_keys('local', [((Endpoint('', ''), Endpoint('', '')), own_priv)])
        self.status = 'joined'
        await self.websocket.send_json({'type': 'status', 'status': 'joined'})

    async def send(self, address, msg):
        socket = self.sockets.get(address)
        if socket is None:
            for eps, dump in self.store.get_socket_contexts().items():
                if eps[1].address == address:
                    socket = Socket.restore(self.mailbox, dump)
                    self.epoll.add({socket}, {socket})
                    self.sockets[address] = socket
                    break
        if socket is not None:
            socket.send(msg.encode('utf-8'))

    async def add_contact(self, address):
        socket = Socket(self.mailbox)
        conn_id = str(uuid.uuid4())
        socket.connect(
            Endpoint(self.address, 'mail.im-demo-add-contact-' + conn_id),
            Endpoint(address, 'mail.im-demo-add-contact-' + conn_id))
        endpoints = (
            Endpoint(self.address, 'mail.im-demo-msg-' + conn_id), Endpoint(address, 'mail.im-demo-msg-' + conn_id))
        own_priv = self.store.get_user_key('local', endpoints)
        own_pub = XEdDSA25519.mont_pub_from_mont_priv(own_priv)
        socket.send(own_pub)
        print('active add contact - key sent')
        other_pub = socket.recv(1000)
        all_keys = self.store.get_user_keys('remote')
        all_keys = [(endpoints, other_pub)] + all_keys
        self.store.set_user_keys('remote', all_keys)
        socket = Socket(self.mailbox)
        print('active add contact - establish conn')
        socket.connect(*endpoints, (own_priv, other_pub))
        print('active add contact - got conn')
        self.epoll.add({socket}, {socket})
        self.sockets[address] = socket
        await self.websocket.send_json({'type': 'contacts', 'contacts': [address]})

    async def init_mailbox(self):
        self.sockets = {}
        self.socket_listener = Socket(self.mailbox)
        self.socket_listener.listen(Endpoint(self.address, ''))
        self.epoll = Epoll(self.mailbox)
        self.epoll.add({self.socket_listener}, set())
        self.thread = threading.Thread(target=self.listener)
        self.thread.start()

    def listener(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        while True:
            rrset, rxset = self.epoll.wait()
            print('epoll wait', rrset, rxset)
            if not rrset and not rxset:
                return
            with self.mutex:
                for socket in rxset:
                    dump = socket.dump()
                    self.store.set_socket_context(socket.endpoints, dump)
                    self.epoll.remove({socket}, {socket})
                    socket.close()
                for socket in rrset:
                    if socket == self.socket_listener:
                        def should_accept(local, remote, secure):
                            print('should accept', local, remote, secure)
                            if not secure:
                                return True
                            own_priv = self.store.get_user_key('local', (local, remote))
                            other_pub = self.store.get_user_key('remote', (local, remote))
                            print('key', own_priv, other_pub)
                            if not own_priv or not other_pub:
                                return False
                            return own_priv, other_pub
                        socket = socket.accept(should_accept, 0)
                        if socket is None:
                            print('socket is none!!!')
                        if socket is not None:
                            print('accepted socket = ', socket.id, socket.endpoints)
                        if socket is None:
                            pass
                        elif socket.endpoints[0].port.startswith('mail.im-demo-add-contact-'):
                            other_pub = socket.recv(1000)
                            own_priv = self.store.get_user_key('local', socket.endpoints)
                            own_pub = XEdDSA25519.mont_pub_from_mont_priv(own_priv)
                            all_keys = self.store.get_user_keys('remote')
                            conn_id = socket.endpoints[0].port.split('mail.im-demo-add-contact-', 1)[1]
                            port = 'mail.im-demo-msg-' + conn_id
                            endpoints = (
                                Endpoint(self.address, port), Endpoint(socket.endpoints[1].address, port))
                            all_keys = [(endpoints, other_pub)] + all_keys
                            self.store.set_user_keys('remote', all_keys)
                            socket.send(own_pub)
                            print('passive add contact - key sent')
                        elif socket.endpoints[0].port.startswith('mail.im-demo-msg-'):
                            self.sockets[socket.endpoints[1].address] = socket
                            self.epoll.add({socket}, {socket})
                            req = self.websocket.send_json({'type': 'contacts', 'contacts': [socket.endpoints[1].address]})
                            loop.run_until_complete(req)
                    else:
                        msg = socket.recv(1000).decode('utf-8')
                        req = self.websocket.send_json({'type': 'msg', 'from': socket.endpoints[1].address, 'msg': msg})
                        loop.run_until_complete(req)


async def handler(request):
    if 'upgrade' in request.headers:
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        conversation = Conversation(ws)
        await conversation.loop()
    path = request.path
    if path == '/':
        path = 'index.html'
    if path.startswith('/'):
        path = path[1:]
    root = os.path.join(os.path.dirname(__file__), 'static')
    file = os.path.join(root, path)
    if os.path.commonpath((root, file)) != root or not os.path.isfile(file):
        return web.HTTPNotFound()
    return web.FileResponse(file)


if __name__ == '__main__':
    app = web.Application()
    app.add_routes([web.get('/{path:.*}', handler)])
    web.run_app(app, host='127.0.0.1', port=3000)
