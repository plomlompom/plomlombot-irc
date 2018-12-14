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
import signal
import plomsearch
import irclog

# Defaults, may be overwritten by command line arguments.
SERVER = "irc.freenode.net"
PORT = 6667
TIMEOUT = 240
USERNAME = "plomlombot"
NICKNAME = USERNAME
TWTFILE = ""
DBDIR = os.path.expanduser("~/plomlombot_db")


def write_to_file(path, mode, text):
    f = open(path, mode)
    f.write(text)
    f.close()


class ExceptionForRestart(Exception):
    pass


class Line:

    def __init__(self, line):
        self.line = line
        self.tokens = line.split(" ")
        self.sender = ""
        if self.tokens[0][0] == ":":
            for rune in self.tokens[0][1:]:
                if rune in {"!", "@"}:
                    break
                self.sender += rune
        self.receiver = ""
        if len(self.tokens) > 2:
            for rune in self.tokens[2]:
                if rune in {"!", "@"}:
                    break
                if rune != ":":
                    self.receiver += rune


class Log:

    def __init__(self, chandir, nickname, username, channel, rmlogs):
        self.nickname = nickname
        self.username = username
        self.channel = channel
        self.chandir = chandir
        self.rmlogcycle = rmlogs
        self.rawlogdir = chandir + "raw_logs/"
        self.logdir = chandir + "logs/"
        if not os.path.exists(self.logdir):
            os.makedirs(self.logdir)
        if not os.path.exists(self.rawlogdir):
            os.makedirs(self.rawlogdir)

    def log(self, line, sent=False):
        identity = ""
        separator = " > "
        if sent:
            separator = " "
            line = Line("< " + line)
            line.sender = self.nickname
            identity = self.username + "@localhost"
        else:
            if type(line) == str:
                line = Line(line)
        now = datetime.datetime.utcnow()
        form = "%Y-%m-%d %H:%M:%S UTC"
        write_to_file(self.rawlogdir + now.strftime("%Y-%m-%d") + ".txt", "a",
                      now.strftime(form) + separator + line.line + "\n")
        to_log = irclog.format_logline(line, self.channel, identity)
        if to_log != None:
            write_to_file(self.logdir + now.strftime("%Y-%m-%d") + ".txt", "a",
                          now.strftime(form) + " " + to_log + "\n")

    def rmlogs(self):
        if self.rmlogcycle > 0:
            for f in os.listdir(self.logdir):
                f = os.path.join(self.logdir, f)
                if os.path.isfile(f) and \
                        os.stat(f).st_mtime < time.time() - self.rmlogcycle:
                    os.remove(f)

    def separator_line(self):
        now = datetime.datetime.utcnow()
        write_to_file(self.logdir + now.strftime("%Y-%m-%d") + ".txt", "a",
                      "-----------------------\n")


class IO:

    def __init__(self, server, port, timeout):
        self.log = None
        self.timeout = timeout
        self.socket = socket.socket()
        try:
            self.socket.connect((server, port))
        except TimeoutError:
            raise ExceptionForRestart
        self.socket.setblocking(0)
        self.line_buffer = []
        self.rune_buffer = ""
        self.last_pong = time.time()
        line = self.recv_line(send_ping=False)
        if not line or len(line) < 1:
            raise ExceptionForRestart
        self.servername = line.split(" ")[0][1:]

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
        if self.log != None:
            self.log.log(msg, True)
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
            if self.log != None:
                self.log.log(line)
            print("LINE FROM SERVER " + str(datetime.datetime.now()) + ": " +
                  line)
        return line


def handle_command(command, argument, notice, target, session):

    def addquote():
        if not os.access(session.quotesfile, os.F_OK):
            write_to_file(session.quotesfile, "w",
                          "QUOTES FOR " + target + ":\n")
        write_to_file(session.quotesfile, "a", argument + "\n")
        quotesfile = open(session.quotesfile, "r")
        lines = quotesfile.readlines()
        quotesfile.close()
        notice("added quote #" + str(len(lines) - 1))

    def quote():

        def help():
            notice("syntax: !quote [int] OR !quote search QUERY")
            notice("QUERY may be a boolean grouping of quoted or unquoted " +
                   "search terms, examples:")
            notice("!quote search foo")
            notice("!quote search foo AND (bar OR NOT baz)")
            notice("!quote search \"foo\\\"bar\" AND ('NOT\"' AND \"'foo'\"" +
                   " OR 'bar\\'baz')")

        if "" == argument:
            tokens = []
        else:
            tokens = argument.split(" ")
        if (len(tokens) > 1 and tokens[0] != "search") or \
            (len(tokens) == 1 and
                (tokens[0] == "search" or not tokens[0].isdigit())):
            help()
            return
        if not os.access(session.quotesfile, os.F_OK):
            notice("no quotes available")
            return
        quotesfile = open(session.quotesfile, "r")
        lines = quotesfile.readlines()
        quotesfile.close()
        lines = lines[1:]
        if len(tokens) == 1:
            i = int(tokens[0])
            if i == 0 or i > len(lines):
                notice("there's no quote of that index")
                return
            i = i - 1
        elif len(tokens) > 1:
            query = str.join(" ", tokens[1:])
            try:
                results = plomsearch.search(query, lines)
            except plomsearch.LogicParserError as err:
                notice("failed query parsing: " + str(err))
                return
            if len(results) == 0:
                notice("no quotes matching query")
            else:
                if len(results) > 3:
                    notice("showing 3 of " + str(len(results)) + " quotes")
                for result in results[:3]:
                    notice("quote #" + str(result[0] + 1) + ": "
                           + result[1][:-1])
            return
        else:
            i = random.randrange(len(lines))
        notice("quote #" + str(i + 1) + ": " + lines[i][:-1])

    def markov():

        def help():
            notice("syntax: !markov [integer from 1 to infinite]")

        def markov(snippet):
            usable_selections = []
            for i in range(select_length, 0, -1):
                for selection in selections:
                    add = True
                    for j in range(i):
                        j += 1
                        if snippet[-j] != selection[-(j+1)]:
                            add = False
                            break
                    if add:
                        usable_selections += [selection]
                if [] != usable_selections:
                    break
            if [] == usable_selections:
                usable_selections = selections
            selection = choice(usable_selections)
            return selection[select_length]

        if "" == argument:
            tokens = []
        else:
            tokens = argument.split(" ")
        if (len(tokens) > 1 or (len(tokens) == 1 and not tokens[0].isdigit())):
            help()
            return

        from random import choice, shuffle
        select_length = 2
        if len(tokens) == 1:
            n = int(tokens[0])
            if n > 0:
                select_length = n
            else:
                notice("bad value, using default: " + str(select_length))
        selections = []

        if not os.access(session.markovfile, os.F_OK):
            notice("not enough text to markov for selection length")
            return

        # Lowercase incoming lines, ensure they end in a sentence end mark.
        file = open(session.markovfile, "r")
        lines = file.readlines()
        file.close()
        tokens = []
        sentence_end_markers = ".!?)("
        for line in lines:
            line = line.lower().replace("\n", "")
            if line[-1] not in sentence_end_markers:
                line += "."
            tokens += line.split()
        if len(tokens) - 1 <= select_length:
            notice("not enough text to markov")
            return

        # Replace URLs with escape string for now, so that the Markov selector
        # won't see them as different strings. Stash replaced URLs in urls.
        urls = []
        url_escape = "\nURL"
        url_starts = ["http://", "https://", "<http://", "<https://"]
        for i in range(len(tokens)):
            for url_start in url_starts:
                if tokens[i][:len(url_start)] == url_start:
                    length = len(tokens[i])
                    if url_start[0] == "<":
                        try:
                            length = tokens[i].index(">") + 1
                        except ValueError:
                            pass
                    urls += [tokens[i][:length]]
                    tokens[i] = url_escape + tokens[i][length:]
                    break

        # For each snippet of select_length, use markov() to find continuation
        # token from selections. Replace present users' names with malkovich.
        # Start snippets with the beginning of a sentence, if possible.
        for i in range(len(tokens) - select_length):
            token_list = []
            for j in range(select_length + 1):
                token_list += [tokens[i + j]]
            selections += [token_list]
        snippet = []
        for i in range(select_length):
            snippet += [""]
        shuffle(selections)
        for i in range(len(selections)):
            if selections[i][0][-1] in sentence_end_markers:
                for j in range(select_length):
                    snippet[j] = selections[j][j + 1]
                break
        msg = ""
        malkovich = "malkovich"
        while 1:
            new_end = markov(snippet)
            for name in session.users_in_chan:
                if new_end[:len(name)] == name.lower():
                    new_end = malkovich + new_end[len(name):]
                    break
            if len(msg) + len(new_end) > 200:
                break
            msg += new_end + " "
            for i in range(select_length - 1):
                snippet[i] = snippet[i + 1]
            snippet[select_length - 1] = new_end

        # Replace occurences of url escape string with random choice from urls.
        while True:
            index = msg.find(url_escape)
            if index < 0:
                break
            msg = msg.replace(url_escape, choice(urls), 1)

        # More meaningful ways to randomly end sentences.
        notice(msg + malkovich + ".")

    def twt():
        def try_open(mode):
            try:
                twtfile = open(session.twtfile, mode)
            except (PermissionError, FileNotFoundError) as err:
                notice("can't access or create twt file: " + str(err))
                return None
            return twtfile

        from datetime import datetime
        if not os.access(session.twtfile, os.F_OK):
            twtfile = try_open("w")
            if None == twtfile:
                return
            twtfile.close()
        twtfile = try_open("a")
        if None == twtfile:
            return
        twtfile.write(datetime.utcnow().isoformat() + "\t" + argument + "\n")
        twtfile.close()
        notice("wrote twt.")

    if "addquote" == command:
        addquote()
    elif "quote" == command:
        quote()
    elif "markov" == command:
        markov()
    elif "twt" == command:
        twt()


def handle_url(url, notice, show_url=False):

    def mobile_twitter_hack(url):
        re1 = 'https?://(mobile.twitter.com/)[^/]+(/status/)'
        re2 = 'https?://mobile.twitter.com/([^/]+)/status/([^\?/]+)'
        m = re.search(re1, url)
        if m and m.group(1) == 'mobile.twitter.com/' \
                and m.group(2) == '/status/':
            m = re.search(re2, url)
            url = 'https://twitter.com/' + m.group(1) + '/status/' + m.group(2)
            handle_url(url, notice, True)
            return True

    class TimeOut(Exception):
        pass

    def timeout_handler(ignore1, ignore2):
        raise TimeOut("timeout")

    signal.signal(signal.SIGALRM, timeout_handler)
    signal.alarm(15)
    try:
        r = requests.get(url, headers = {'User-Agent': 'plomlombot'}, stream=True)
        r.raw.decode_content = True
        text = r.raw.read(10000000+1)
        if len(text) > 10000000:
            raise ValueError('Too large a response')
    except (requests.exceptions.TooManyRedirects,
            requests.exceptions.ConnectionError,
            requests.exceptions.InvalidURL,
            TimeOut,
            UnicodeError,
            ValueError,
            requests.exceptions.InvalidSchema) as error:
        signal.alarm(0)
        notice("trouble following url: " + str(error))
        return False
    signal.alarm(0)
    if mobile_twitter_hack(url):
        return True
    title = bs4.BeautifulSoup(text, "html5lib").title
    if title and title.string:
        prefix = "page title: "
        if show_url:
            prefix = "page title for <" + url + ">: "
        notice(prefix + title.string.strip())
    else:
        notice("page has no title tag")
    return True


class Session:

    def __init__(self, io, username, nickname, channel, twtfile, dbdir, rmlogs,
                 markov_input):
        self.io = io
        self.nickname = nickname
        self.users_in_chan = []
        self.twtfile = twtfile
        hash_channel = hashlib.md5(channel.encode("utf-8")).hexdigest()
        chandir = dbdir + "/" + hash_channel + "/"
        self.markov_input = markov_input
        self.markovfile = chandir + "markovfeed"
        self.quotesfile = chandir + "quotes"
        self.log = Log(chandir, self.nickname, username, channel, rmlogs)
        self.io.send_line("NICK " + self.nickname)
        self.io.send_line("USER " + username + " 0 * : ")
        self.io.send_line("JOIN " + channel)
        self.io.log = self.log
        self.log.separator_line()

    def loop(self):

        def handle_privmsg(line):

            def notice(msg):
                line = "NOTICE " + target + " :" + msg
                self.io.send_line(line)

            target = line.sender
            if line.receiver != self.nickname:
                target = line.receiver
            msg = str.join(" ", line.tokens[3:])[1:]
            matches = re.findall("(https?://[^\s>]+)", msg)
            url_count = 0
            for i in range(len(matches)):
                if handle_url(matches[i], notice):
                    url_count += 1
                    if url_count == 3:
                        notice("maximum number of urls to parse per message "
                               "reached")
                        break
            if "!" == msg[0] and len(msg) > 1:
                tokens = msg[1:].split()
                argument = str.join(" ", tokens[1:])
                handle_command(tokens[0], argument, notice, target, self)
                return
            if self.markov_input:
                write_to_file(self.markovfile, "a", msg + "\n")

        while True:
            self.log.rmlogs()
            line = self.io.recv_line()
            if not line:
                continue
            line = Line(line)
            if len(line.tokens) > 1:
                if line.tokens[0] == "PING":
                    self.io.send_line("PONG " + line.tokens[1])
                elif line.tokens[1] == "PRIVMSG":
                    handle_privmsg(line)
                elif line.tokens[1] == "353":
                    names = line.tokens[5:]
                    names[0] = names[0][1:]
                    for i in range(len(names)):
                        names[i] = names[i].replace("@", "").replace("+", "")
                    self.users_in_chan += names
                elif line.tokens[1] == "JOIN" and line.sender != self.nickname:
                    self.users_in_chan += [line.sender]
                elif line.tokens[1] == "PART":
                    del(self.users_in_chan[self.users_in_chan.index(line.sender)])
                elif line.tokens[1] == "NICK":
                    del(self.users_in_chan[self.users_in_chan.index(line.sender)])
                    self.users_in_chan += [line.receiver]


def parse_command_line_arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument("-s, --server", action="store", dest="server",
                        default=SERVER,
                        help="server or server net to connect to (default: "
                        + SERVER + ")")
    parser.add_argument("-p, --port", action="store", dest="port", type=int,
                        default=PORT, help="port to connect to (default : "
                        + str(PORT) + ")")
    parser.add_argument("-w, --wait", action="store", dest="timeout",
                        type=int, default=TIMEOUT,
                        help="timeout in seconds after which to attempt "
                        "reconnect (default: " + str(TIMEOUT) + ")")
    parser.add_argument("-u, --username", action="store", dest="username",
                        default=USERNAME, help="username to use (default: "
                        + USERNAME + ")")
    parser.add_argument("-n, --nickname", action="store", dest="nickname",
                        default=NICKNAME, help="nickname to use (default: "
                        + NICKNAME + ")")
    parser.add_argument("-t, --twtxtfile", action="store", dest="twtfile",
                        default=TWTFILE, help="twtxt file to use (default: "
                        + TWTFILE + ")")
    parser.add_argument("-d, --dbdir", action="store", dest="dbdir",
                        default=DBDIR, help="directory to store DB files in")
    parser.add_argument("-r, --rmlogs", action="store", dest="rmlogs",
                        type=int, default=0,
                        help="maximum age in seconds for logfiles in logs/ "
                        "(0 means: never delete, and is default)")
    parser.add_argument("-m, --markov_store", action="store_true",
                        dest="markov_store",
                        help="log channel discussions for !markov input")
    parser.add_argument("CHANNEL", action="store", help="channel to join")
    opts, unknown = parser.parse_known_args()
    return opts


opts = parse_command_line_arguments()
while True:
    try:
        io = IO(opts.server, opts.port, opts.timeout)
        hash_server = hashlib.md5(opts.server.encode("utf-8")).hexdigest()
        dbdir = opts.dbdir + "/" + hash_server
        session = Session(io, opts.username, opts.nickname, opts.CHANNEL,
                          opts.twtfile, dbdir, opts.rmlogs, opts.markov_input)
        session.loop()
    except ExceptionForRestart:
        io.socket.close()
        continue
