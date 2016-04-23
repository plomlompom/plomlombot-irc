#!/usr/bin/python3

def format_logline(line, channel, identity):
    if len(line.tokens) > 2:
        if line.tokens[1] == "JOIN":
            if identity == "":
                identity = line.tokens[0][len(line.sender) + 2:]
            return "-> " + line.sender + " (" + identity + ") joins"
        elif line.tokens[1] == "PART":
            msg = ""
            if len(line.tokens) > 3 and line.tokens[3][0] == ":":
                msg = " (" + str.join(" ", line.tokens[3:])[1:] + ")"
            return "<- " + line.sender + " parts" + msg 
        elif line.tokens[1] == "QUIT":
            msg = ""
            if len(line.tokens) > 2 and line.tokens[2][0] == ":":
                msg = " (" + str.join(" ", line.tokens[2:])[1:] + ")"
            return "<- " + line.sender + " quits server" + msg
        elif line.tokens[1] == "NICK":
            return "-- " + line.sender + " changes their name to " + line.receiver 
        elif len(line.tokens) > 3:
            if line.tokens[1] in {"PRIVMSG", "NOTICE"}:
                if line.tokens[3] == ":\u0001ACTION" and \
                        line.tokens[-1][-1] == "\u0001":
                    msg = str.join(" ", line.tokens[4:])[:-1]
                    if line.receiver == channel:
                        return " * " + line.sender + " " + msg 
                else:
                    msg = str.join(" ", line.tokens[3:])[1:]
                    if line.receiver == channel:
                        return "   <" + line.sender + "> " + msg 
            elif line.tokens[1] == "TOPIC":
                msg = str.join(" ", line.tokens[3:])[1:]
                if line.receiver == channel:
                    return "-- " + line.sender + " sets topic to: " + msg 
            elif line.tokens[1] == "KICK":
                operands = line.tokens[2:]
                pairs = {}
                for i in range(len(operands)):
                    if 0 == i % 2:
                        if operands[i][0] == ":":
                            msg = " (" + str.join(" ", operands[i:])[1:] + ")"
                            break
                    else:
                        pairs[operands[i - 1]] = operands[i]
                if channel in pairs:
                    return "-- " + line.sender + " kicks " + pairs[channel] + msg
            elif line.tokens[1] == "MODE":
                msg = str.join(" ", line.tokens[3:])
                if line.receiver == channel:
                    return "-- " + line.sender + " sets channel mode " + msg 
    return None
