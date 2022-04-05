#!/usr/bin/python3

import sys
import os
import time
import signal
import errno
import socket
import select
from log import log


class TCPServer:
    _socket_list = []
    _forward_dict = {}
    _callback_list = []
    BUFFSIZE = 1024

    def __init__(self, listen_ip, listen_port, forward_ip, forward_port, logger = None):
        self._log = log('TCP Server') if logger is None else logger
        self._listen_ip    = listen_ip
        self._forward_ip   = forward_ip
        self._forward_port = forward_port
        self._forward_timeout = 10
        self._listen_port  = listen_port
        self._listener     = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._listener.bind((listen_ip, listen_port))
        self._listener.listen(2)
        self._socket_list.append(self._listener)
        signal.signal(signal.SIGTERM, self.sigterm_handler)
        signal.signal(signal.SIGINT, self.sigterm_handler)

    def set_forward_timeout(self, ti):
        self._forward_timeout = ti

    def register_callback(self, callback):
        self._callback_list.append(callback)

    def create_forward(self, s_in):
        self._log.logMsg('create forwarder', log.DEBUG)
        try:
            s_out = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s_out.settimeout(self._forward_timeout)
            s_out.connect((self._forward_ip, self._forward_port))
        except Exception as e:
            self._log.logMsg(f'create forward failed {e}', log.WARN)
            return False
        else:
            if s_in in self._forward_dict:
                self.close_connection(self._forward_dict[s_in])
            self._forward_dict[s_in] = s_out
            self._forward_dict[s_out] = s_in
            self._socket_list.append(s_out)
        return s_out

    def delete_forward(self, s_in):
        if s_in in self._forward_dict:
            # close also associated forward if exists
            s_out = self._forward_dict[s_in]
            try:
                s_out.close()
            except Exception as e:
                self._log.logMsg(f'unable to close {s_out}: {e}', log.WARN)
            else:
                if s_out in self._forward_dict:
                    del self._forward_dict[s_out]
                if s_out in self._socket_list:
                    self._socket_list.remove(s_out)
                del self._forward_dict[s_in]

    def loop(self):
        while True:
            time.sleep(0.01)
            self._log.logMsg('main loop', log.DEBUG)
            try:
                inputready, _, _ = select.select(self._socket_list, [], [])
            except Exception as e:
                self._log.logMsg(f'select exception {e}', log.DEBUG)
                return
            for s_in in inputready:
                if s_in == self._listener:
                    self.accept_connection()
                else:
                    try:
                        data = s_in.recv(self.BUFFSIZE)
                        self._log.logMsg(f'received: {len(data)} bytes from {s_in.getpeername()} on fd {s_in.fileno()}', log.DEBUG)
                        if data and len(data) > 0:
                            data = self.handle_data(s_in, data)
                            if len(data) and not s_in in self._forward_dict:
                                # create forwarder
                                self.create_forward(s_in)
                            # forward data to proxy peer
                            if s_in in self._forward_dict and len(data):
                                self._forward_dict[s_in].send(data)
                                self._log.logMsg(f'Data forwarded to {self._forward_dict[s_in]}', log.DEBUG)
                        else: # no data means connection close
                            self._log.logMsg('socket closed ' + str(s_in), log.DEBUG)
                            self.close_connection(s_in)
                            self._log.logMsg('Remaining input list: ' + str(self._socket_list), log.DEBUG)
                    except OSError as e:
                        self._log.logMsg('socket read error on ' + str(s_in) + ' ' + str(e), log.WARN)
                        time.sleep(1) 
                        # Connection was closed abnormally
                        self.close_connection(s_in)
                        self._log.logMsg('Remaining input list: ' + str(self._socket_list), log.DEBUG)

    def accept_connection(self):
        self._log.logMsg('Entering accept', log.DEBUG)
        clientsock, clientaddr = self._listener.accept()
        self._log.logMsg(f'{clientaddr} has connected', log.DEBUG)
        self._socket_list.append(clientsock)
        self._log.logMsg('New connection list: ' + str(self._socket_list), log.DEBUG)

    def close_connection(self, s_in):
        self._log.logMsg('closeing ' + str(s_in), log.DEBUG)
        self._log.logMsg('Input list: ' + str(self._socket_list), log.DEBUG)
        self._log.logMsg('Forward dictionary: ' + str(self._forward_dict), log.DEBUG)
        if s_in == self._listener:
            # First connection  cannot be closed: proxy listening on its port
            self._log.logMsg('tried to close listener', log.ERROR)
            return
        self.delete_forward(s_in)
        try:
            s_in.close()
        except Exception as e:
            self._log.logMsg(f'unable to close {s_in}: {e}', log.WARN)
        else:    
            if s_in in self._socket_list:
                self._socket_list.remove(s_in)

    def close_all(self):
        # Close all connections
        self._log.logMsg('closeing all', 5)
        self._log.logMsg('Connections to close: ' + str(self._socket_list), log.DEBUG)
        while len(self._socket_list) > 1:
            self.close_connection(self._socket_list[1])
        self._listener.close()

    # handle the date, return the original data modify if needed 
    def handle_data(self, s_in, data):
        data_type = 'server'
        if s_in.getsockname()[1] == self._listen_port:
            data_type = 'client'
        self._log.logMsg(f'{data_type}data to handle ({len(data)})', log.DEBUG)
        for cb in self._callback_list:
            data = cb(data_type, data)
        return data

    def sigterm_handler(self, signal, frame):
        self._log.logMsg('Received SIGTERM, closing connections', log.INFO)
        self.close_all()
        self._log.logMsg('Stopping server', 1)



