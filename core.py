#!/usr/bin/python

import random
import socket
import textwrap

# prints out a message if verbose output is enabled
def verbose(*args):
    if config.verbose:
        if len(args) == 0:
            return
        elif len(args) == 1:
            print(args[0])
        elif len(args) == 2:
            verbose_with_prefix(args[0], args[1])
        else:
            verbose_with_indent(args[0], args[1], args[2:])

# print out a message with specified prefix if verbose output is enabled
def verbose_with_prefix(prefix, message):
    if config.verbose:
        print_with_prefix(prefix, message)

# print out a message with specified prefix and indent if verbose output is enabled
def verbose_with_indent(prefix, first_message, other_messages):
    if config.verbose:
        print_with_indent(prefix, first_message, other_messages)

# print out a message with prefix
def print_with_prefix(prefix, message):
    print('[{0:s}] {1}'.format(prefix, message))

# print out a message with specified prefix
def print_with_indent(prefix, first_message, other_messages):
    formatted_prefix = '[{0:s}] '.format(prefix)
    print('{0:s}{1}'.format(formatted_prefix, first_message))
    if len(other_messages) > 0:
        indent = ' ' * len(formatted_prefix)
        wrapper = textwrap.TextWrapper(
            initial_indent=indent, subsequent_indent=indent, width=70)
        for message in other_messages:
            print(wrapper.fill(message))

# contains fuzzer configuration, parameters can be accessed as attributes
class Config:

    # read arguments returned by argparse.ArgumentParser
    def readargs(self, args):
        self.args = vars(args)

        # parse test range
        if args.test:
            parts = args.test.split(':')
            if len(parts) == 1:
                self.args['start_test'] = int(parts[0])
                self.args['end_test'] = int(parts[0])
            elif len(parts) == 2:
                self.args['start_test'] = int(parts[0])
                if parts[1] == '' or parts[1] == 'infinite':
                    self.args['end_test'] = float('inf')
                else:
                    self.args['end_test'] = int(parts[1])
            else:
                raise Exception('Could not parse --test value, too many colons')
        else:
            self.args['start_test'] = 0
            self.args['end_test'] = float('inf')

        # parse mutation ratio
        parts = args.ratio.split(':')
        if len(parts) == 1:
            self.args['min_ratio'] = float(parts[0])
            self.args['max_ratio'] = min_ratio
        elif len(parts) == 2:
            self.args['min_ratio'] = float(parts[0])
            self.args['max_ratio'] = float(parts[1])
        else:
            raise Exception('Could not parse --ratio value, too many colons')

    def __getattr__(self, name):
        return self.args[name]

# dumb fuzzer for a byte array
class DumbByteArrayFuzzer:

    def __init__(self, config, ignored_bytes = ()):
        self.start_test = config.start_test
        self.min_ratio = config.min_ratio
        self.max_ratio = config.max_ratio
        self.seed = config.seed
        self.ignored_bytes = ignored_bytes
        self.reset()

    def set_test(self, test):
        self.test = test

    def reset(self):
        self.test = self.start_test
        self.random = random.Random()
        self.random.seed(self.seed)
        self.random_n = random.Random()
        self.random_position = random.Random()
        self.random_byte = random.Random()

    def next(self, data):
        fuzzed = bytearray(data)
        min_bytes = int(float(self.min_ratio) * int(len(data)));
        max_bytes = int(float(self.max_ratio) * int(len(data)));

        seed = self.random.random() * self.test

        if min_bytes == max_bytes:
            n = min_bytes
        else:
            self.random_n.seed(seed)
            n = self.random_n.randrange(min_bytes, max_bytes)

        self.random_position.seed(seed)
        self.random_byte.seed(seed)

        i = 0
        while (i < n):
            pos = self.random_position.randint(0, len(fuzzed) - 1)
            if self.isignored(fuzzed[pos]):
                continue
            b = self.random_byte.randint(0, 255)
            fuzzed[pos] = b
            i += 1

        self.test += 1
        return fuzzed

    def isignored(self, symbol):
        return symbol in self.ignored_bytes

# TCP server which redirect incoming connections to remote server
# It calls a fuzzer to fuzz data from client and server
class Server:

    bufsize = 4096

    def __init__(self, config, client_fuzzer = None, server_fuzzer = None):
        self.local_host = config.local_host
        self.local_port = config.local_port
        self.remote_host = config.remote_host
        self.remote_port = config.remote_port
        self.timeout = config.timeout
        self.client_fuzzer = client_fuzzer
        self.server_fuzzer = server_fuzzer

    def start(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
            server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server.bind((self.local_host, self.local_port))
            server.listen(1)
            print_with_prefix('server', 'listening on {0:s}:{1:d}'.format(self.local_host, self.local_port))
            while True:
                print_with_prefix('server', 'waiting for connection')
                conn, addr = server.accept()
                print_with_prefix('server', 'accepted connection from: {0}'.format(addr))
                with conn:
                    conn.settimeout(self.timeout)
                    try:
                        self.handle_tcp_connection(conn)
                    except OSError as msg:
                        print_with_prefix('server', 'error occured while handling connection: {0}'.format(msg))

    def handle_tcp_connection(self, conn):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as remote:
            remote.settimeout(self.timeout)
            remote.connect((self.remote_host, self.remote_port))
            while True:
                print_with_prefix('connection', 'receive data from client')
                received = False
                try:
                    data = conn.recv(self.bufsize)
                    if not data:
                        print_with_prefix('connection', 'no data received from client, closing')
                        break
                    else:
                        received = True
                except OSError as msg:
                    print_with_prefix('connection', 'error occured while receiving data from client: {0}'.format(msg))

                if received:
                    print_with_prefix('connection', 'received {0:d} bytes from client'.format(len(data)))
                    if self.client_fuzzer:
                        data = self.client_fuzzer.next(data)
                        print_with_prefix('connection', 'send fuzzed data to server')
                    else:
                        print_with_prefix('connection', 'send data to server')

                    remote.sendall(data)
                    print_with_prefix('connection', 'sent {0:d} bytes to server'.format(len(data)))

                print_with_prefix('connection', 'receive data from server')
                received = False
                try:
                    data = remote.recv(self.bufsize)
                    if not data:
                        print_with_prefix('connection', 'no data received from server, closing')
                        break
                    else:
                        received = True
                except OSError as msg:
                    print_with_prefix('connection', 'error occured while receiving data from server: {0}'.format(msg))

                if received:
                    print_with_prefix('connection', 'received {0:d} bytes from server'.format(len(data)))
                    if self.server_fuzzer:
                        data = self.server_fuzzer.next(data)
                        print_with_prefix('connection', 'send fuzzed data to client')
                    else:
                        print_with_prefix('connection', 'send data to client')

                    conn.sendall(data)
                    print_with_prefix('connection', 'sent {0:d} bytes to client'.format(len(data)))

        print_with_prefix('connection', 'closed')


# global configuration
config = Config()
