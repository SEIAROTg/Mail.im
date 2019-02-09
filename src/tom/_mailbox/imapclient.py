import sys
import socket
import select
import imapclient as _imapclient
from imapclient import *


class IMAPClient(_imapclient.IMAPClient):
    """
    This class provdes some extensions to `imapclient.IMAPClient`
    """

    @imapclient.require_capability('IDLE')
    def idle_check(self, timeout: float = None, selfpipe: int = None):
        """
        This extends imapclient.IMAPClient.idle_check with elegant exiting mechanism via selfpipe

        This will block until one of the following become true
        1. an IDLE response is received
        2. `timeout` seconds elapsed
        3. the file descriptor `selfpipe` becomes ready to read

        :param timeout: operation timeout
        :param selfpipe: a file descriptor
        :return: None if `selfpipe` is ready, otherwise same as `imapclient.IMAPClient.idle_check`
        """

        sock = self._sock

        # make the socket non-blocking so the timeout can be
        # implemented for this call
        sock.settimeout(None)
        sock.setblocking(0)
        try:
            resps = []
            rlist = [sock]
            if selfpipe is not None:
                rlist.append(selfpipe)
            rs, _, _ = select.select(rlist, [], [], timeout)
            if rs:
                if selfpipe in rs:
                    return
                while True:
                    try:
                        line = self._imap._get_line()
                    except (socket.timeout, socket.error):
                        break
                    except IMAPClient.AbortError:
                        # An imaplib.IMAP4.abort with "EOF" is raised
                        # under Python 3
                        err = sys.exc_info()[1]
                        if 'EOF' in err.args[0]:
                            break
                        else:
                            raise
                    else:
                        resps.append(imapclient._parse_untagged_response(line))
            return resps
        finally:
            sock.setblocking(1)
            self._set_read_timeout()
