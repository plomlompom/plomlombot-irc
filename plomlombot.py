#!/usr/bin/python3

import argparse
import socket
import datetime
import select
import time
import re
import requests
import bs4
import random
import hashlib
import os

# Defaults, may be overwritten by command line arguments.
SERVER = "irc.freenode.net"
PORT = 6667
TIMEOUT = 240
USERNAME = "plomlombot"
NICKNAME = USERNAME


class ExceptionForRestart(Exception):
    pass


class IO:

    def __init__(self, server, port, timeout):
        self.timeout = timeout
        self.socket = socket.socket()
        self.socket.connect((server, port))
        self.socket.setblocking(0)
        self.line_buffer = []
        self.rune_buffer = ""
        self.last_pong = time.time()
        self.servername = self.recv_line(send_ping=False).split(" ")[0][1:]

    def _pingtest(self, send_ping=True):
        if self.last_pong + self.timeout < time.time():
            print("SERVER NOT ANSWERING")
            raise ExceptionForRestart
        if send_ping:
            self.send_line("PING " + self.servername)

    def send_line(self, msg):
        msg = msg.replace("\r", " ")
        msg = msg.replace("\n", " ")
        if len(msg.encode("utf-8")) > 510:
            print("NOT SENT LINE TO SERVER (too long): " + msg)
        print("LINE TO SERVER: "
              + str(datetime.datetime.now()) + ": " + msg)
        msg = msg + "\r\n"
        msg_len = len(msg)
        total_sent_len = 0
        while total_sent_len < msg_len:
            sent_len = self.socket.send(bytes(msg[total_sent_len:], "UTF-8"))
            if sent_len == 0:
                print("SOCKET CONNECTION BROKEN")
                raise ExceptionForRestart
            total_sent_len += sent_len

    def _recv_line_wrapped(self, send_ping=True):
        if len(self.line_buffer) > 0:
            return self.line_buffer.pop(0)
        while True:
            ready = select.select([self.socket], [], [], int(self.timeout / 2))
            if not ready[0]:
                self._pingtest(send_ping)
                return None
            self.last_pong = time.time()
            received_bytes = self.socket.recv(1024)
            try:
                received_runes = received_bytes.decode("UTF-8")
            except UnicodeDecodeError:
                received_runes = received_bytes.decode("latin1")
            if len(received_runes) == 0:
                print("SOCKET CONNECTION BROKEN")
                raise ExceptionForRestart
            self.rune_buffer += received_runes
            lines_split = str.split(self.rune_buffer, "\r\n")
            self.line_buffer += lines_split[:-1]
            self.rune_buffer = lines_split[-1]
            if len(self.line_buffer) > 0:
                return self.line_buffer.pop(0)

    def recv_line(self, send_ping=True):
        line = self._recv_line_wrapped(send_ping)
        if line:
            print("LINE FROM SERVER " + str(datetime.datetime.now()) + ": " +
                  line)
        return line


def init_session(server, port, timeout, nickname, username, channel):
    print("CONNECTING TO " + server)
    io = IO(server, port, timeout)
    io.send_line("NICK " + nickname)
    io.send_line("USER " + username + " 0 * : ")
    io.send_line("JOIN " + channel)
    return io


def lineparser_loop(io, nickname):

    def act_on_privmsg(tokens):

        def notice(msg):
            io.send_line("NOTICE " + target + " :" + msg)

        def url_check(msg):

            def handle_url(url, show_url=False):

                def mobile_twitter_hack(url):
                    re1 = 'https?://(mobile.twitter.com/)[^/]+(/status/)'
                    re2 = 'https?://mobile.twitter.com/([^/]+)/status/' \
                        + '([^\?/]+)'
                    m = re.search(re1, url)
                    if m and m.group(1) == 'mobile.twitter.com/' \
                            and m.group(2) == '/status/':
                        m = re.search(re2, url)
                        url = 'https://twitter.com/' + m.group(1) + '/status/' \
                                + m.group(2)
                        handle_url(url, True)
                        return True

                try:
                    r = requests.get(url, timeout=15)
                except (requests.exceptions.TooManyRedirects,
                        requests.exceptions.ConnectionError,
                        requests.exceptions.InvalidURL,
                        requests.exceptions.InvalidSchema) as error:
                    notice("TROUBLE FOLLOWING URL: " + str(error))
                    return
                if mobile_twitter_hack(url):
                    return
                title = bs4.BeautifulSoup(r.text).title
                if title:
                    prefix = "PAGE TITLE: "
                    if show_url:
                        prefix = "PAGE TITLE FOR <" + url + ">: "
                    notice(prefix + title.string.strip())
                else:
                    notice("PAGE HAS NO TITLE TAG")

            matches = re.findall("(https?://[^\s>]+)", msg)
            for i in range(len(matches)):
                handle_url(matches[i])

        def command_check(msg):
            if msg[0] != "!":
                return
            tokens = msg[1:].split()
            hash_string = hashlib.md5(target.encode("utf-8")).hexdigest()
            quotesfile_name = "quotes_" + hash_string
            if tokens[0] == "addquote":
                if not os.access(quotesfile_name, os.F_OK):
                    quotesfile = open(quotesfile_name, "w")
                    quotesfile.write("QUOTES FOR " + target + ":\n")
                    quotesfile.close()
                quotesfile = open(quotesfile_name, "a")
                quotesfile.write(str.join(" ", tokens[1:]) + "\n")
                quotesfile.close()
                quotesfile = open(quotesfile_name, "r")
                lines = quotesfile.readlines()
                quotesfile.close()
                notice("ADDED QUOTE #" + str(len(lines) - 1))
            elif tokens[0] == "quote":
                if len(tokens) > 2 or \
                    (len(tokens) == 2 and not tokens[1].isdigit()):
                    notice("SYNTAX: !quote [int]")
                    return
                if not os.access(quotesfile_name, os.F_OK):
                    notice("NO QUOTES AVAILABLE")
                    return
                quotesfile = open(quotesfile_name, "r")
                lines = quotesfile.readlines()
                quotesfile.close()
                lines = lines[1:]
                if len(tokens) == 2:
                    i = int(tokens[1])
                    if i == 0 or i > len(lines):
                        notice("THERE'S NO QUOTE OF THAT INDEX")
                        return
                    i = i - 1
                else:
                    i = random.randrange(len(lines))
                notice("QUOTE #" + str(i + 1) + ": " + lines[i])

        sender = ""
        for rune in tokens[0]:
            if rune == "!":
                break
            if rune != ":":
                sender += rune
        receiver = ""
        for rune in tokens[2]:
            if rune == "!":
                break
            if rune != ":":
                receiver += rune
        target = sender
        if receiver != nickname:
            target = receiver
        msg = str.join(" ", tokens[3:])[1:]
        command_check(msg)
        url_check(msg)

    while True:
        line = io.recv_line()
        if not line:
            continue
        tokens = line.split(" ")
        if len(tokens) > 1:
            if tokens[1] == "PRIVMSG":
                act_on_privmsg(tokens)
            if tokens[0] == "PING":
                io.send_line("PONG " + tokens[1])


def parse_command_line_arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument("-s, --server", action="store", dest="server",
                        default=SERVER,
                        help="server or server net to connect to (default: "
                        + SERVER + ")")
    parser.add_argument("-p, --port", action="store", dest="port", type=int,
                        default=PORT, help="port to connect to (default : "
                        + str(PORT) + ")")
    parser.add_argument("-t, --timeout", action="store", dest="timeout",
                        type=int, default=TIMEOUT,
                        help="timeout in seconds after which to attempt " +
                        "reconnect (default: " + str(TIMEOUT) + ")")
    parser.add_argument("-u, --username", action="store", dest="username",
                        default=USERNAME, help="username to use (default: "
                        + USERNAME + ")")
    parser.add_argument("-n, --nickname", action="store", dest="nickname",
                        default=NICKNAME, help="nickname to use (default: "
                        + NICKNAME + ")")
    parser.add_argument("CHANNEL", action="store", help="channel to join")
    opts, unknown = parser.parse_known_args()
    return opts

opts = parse_command_line_arguments()
while True:
    try:
        io = init_session(opts.server, opts.port, opts.timeout, opts.nickname,
                          opts.username, opts.CHANNEL)
        lineparser_loop(io, opts.nickname)
    except ExceptionForRestart:
        io.socket.close()
        continue
