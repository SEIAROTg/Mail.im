new Vue({
    el: 'app',
    data: {
        credentials: {
            email: '',
            masterKey: '',
            smtp: {
                host: '',
                port: '',
                username: '',
                password: '',
            },
            imap: {
                host: '',
                port: '',
                username: '',
                password: '',
            },
        },
        chat: {
            contacts: [],
            addContact: {
                email: '',
                active: false,
            },
            currentContact: null,
        },
        status: 'init',
        ready: false,
        error: null,
    },
    created() {
        this.ws = new WebSocket('ws://localhost:3000');
        this.ws.addEventListener('open', () => this.ready = true);
        this.ws.addEventListener('close', () => this.ready = false);
        this.ws.addEventListener('message', (event) => {
           this.processResponse(JSON.parse(event.data));
        });
    },
    methods: {
        onConnect() {
            switch (this.status) {
                case 'init':
                    this.ws.send(JSON.stringify({type: 'join', address: this.credentials.email}));
                    break;
                case 'login':
                    this.ws.send(JSON.stringify({type: 'login', master_key: this.credentials.masterKey}));
                    break;
                case 'register':
                    this.ws.send(JSON.stringify({
                        type: 'register',
                        credentials: {
                            master_key: this.credentials.masterKey,
                            smtp: {
                                host: this.credentials.smtp.host,
                                port: parseInt(this.credentials.smtp.port),
                                username: this.credentials.smtp.username,
                                password: this.credentials.smtp.password,
                            },
                            imap: {
                                host: this.credentials.imap.host,
                                port: parseInt(this.credentials.imap.port),
                                username: this.credentials.imap.username,
                                password: this.credentials.smtp.password,
                            },
                        },
                    }));
                    break;
                default:
            }
        },
        processResponse(data) {
            switch (data.type) {
                case 'error':
                    this.error = data.msg;
                    break;
                case 'contacts':
                    for (const contact of data.contacts) {
                        this.chat.contacts.push({
                            name: contact.split('@')[0],
                            email: contact,
                            last: null,
                            typing: '',
                            messages: [],
                        });
                    }
                    break;
                case 'msg':
                    for (const contact of this.chat.contacts) {
                        if (contact.email === data.from) {
                            contact.messages.push({from: 'other', body: data.msg});
                            contact.last = Date.now();
                            break;
                        }
                    }
                    break;
                case 'status':
                    switch (data.status) {
                        case 'register':
                            this.credentials.masterKey = '';
                            const host = this.credentials.email.slice(this.credentials.email.indexOf('@') + 1);
                            this.credentials.smtp.host = 'smtp.' + host;
                            this.credentials.smtp.port = '587';
                            this.credentials.smtp.username = this.credentials.email;
                            this.credentials.smtp.password = '';
                            this.credentials.imap.host = 'imap.' + host;
                            this.credentials.imap.port = '993';
                            this.credentials.imap.username = this.credentials.email;
                            this.credentials.imap.password = '';
                            break;
                        case 'login':
                            this.credentials.masterKey = '';
                            break;
                        default:
                    }
                    this.status = data.status;
                    break;
                default:
            }
        },
        onAddContact() {
            this.chat.addContact.email = '';
            this.chat.addContact.active = true;
        },
        onCommitAddContact() {
            this.ws.send(JSON.stringify({type: 'add_contact', address: this.chat.addContact.email}));
            this.chat.addContact.active = false;
        },
        onSend() {
            const contact = this.chat.currentContact;
            this.ws.send(JSON.stringify({type: 'send', address: contact.email, msg: contact.typing}));
            contact.messages.push({from: 'own', body: contact.typing});
            contact.typing = '';
        },
        gravatarUrl(email) {
            return `https://www.gravatar.com/avatar/${md5(email)}?s=64`;
        }
    },
    watch: {
        email() {
            this.status = 'init';
        },
    },
    filters: {
        time(ts) {
            if (ts == null) {
                return '';
            }
            const d = new Date(ts);
            let hh = d.getHours().toString();
            let mm = d.getMinutes().toString();
            if (hh.length < 2) {
                hh = '0' + hh;
            }
            if (mm.length < 2) {
                mm = '0' + mm;
            }
            return hh + ':' + mm;
        },
    },
});
