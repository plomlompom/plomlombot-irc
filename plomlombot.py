import socket
import datetime
import select
import time
import re
import urllib.request
import html

servernet = "irc.freenode.net"
port = 6667
servername = ""
timeout = 240
username = "plomlombot"
nickname = username
channel = "#zrolaps-test"

class IO:

    def __init__(self, server, port):
        self.socket = socket.socket()
        self.socket.connect((server, port))
        self.socket.setblocking(0)
        self.line_buffer = []
        self.rune_buffer = ""
        self.last_pong = time.time()

    def _pingtest(self):
        if self.last_pong + timeout < time.time():
            raise RuntimeError("server not answering")
        self.send_line("PING " + nickname + " " + servername)

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
                raise RuntimeError("socket connection broken")
            total_sent_len += sent_len

    def recv_line_wrapped(self):
        if len(self.line_buffer) > 0:
            return self.line_buffer.pop(0)
        while True:
            ready = select.select([self.socket], [], [], int(timeout / 2))
            if not ready[0]:
                self._pingtest()
                return None
            self.last_pong = time.time()
            received_runes = self.socket.recv(1024).decode("UTF-8")
            if len(received_runes) == 0:
                raise RuntimeError("socket connection broken")
            self.rune_buffer += received_runes 
            lines_split = str.split(self.rune_buffer, "\r\n")
            self.line_buffer += lines_split[:-1]
            self.rune_buffer = lines_split[-1]
            if len(self.line_buffer) > 0:
                return self.line_buffer.pop(0)

    def recv_line(self):
        line = self.recv_line_wrapped()
        if line:
            print("LINE FROM SERVER " + str(datetime.datetime.now()) + ": " +
            line)
        return line

def url_check(msg):
    matches = re.findall("(https?://[^\s]+)", msg)
    for i in range(len(matches)):
        url = matches[i]
        webpage = urllib.request.urlopen(url, timeout=15)
        content_type = webpage.info().get_content_type()
        charset = webpage.info().get_content_charset()
        if not charset or not content_type in ('text/html', 'text/xml',
                'application/xhtml+xml'):
            continue
        content = webpage.read().decode(charset)
        title = str(content).split('<title>')[1].split('</title>')[0]
        title = html.unescape(title)
        io.send_line("PRIVMSG " + target + " :page title for url: " + title)

io = IO(servernet, port)
io.send_line("NICK " + nickname)
io.send_line("USER " + username + " 0 * : ")
io.send_line("JOIN " + channel)
servername = io.recv_line().split(" ")[0][1:]
while 1:
    line = io.recv_line()
    if not line:
        continue
    tokens = line.split(" ")
    if len(tokens) > 1:
        if tokens[1] == "PRIVMSG":
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
            url_check(msg)
        if tokens[0] == "PING":
            io.send_line("PONG " + tokens[1])
