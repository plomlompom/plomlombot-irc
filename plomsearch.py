class CompoundStatement:
    def __init__(self, or_list, negneg=True):
        self.or_list = or_list
        self.neg = False if negneg else True
    #def __repr__(self):
    #    return "<" + str(not self.neg) + ": OR'd " + str(self.or_list) + ">"

class LogicParserError(Exception):
    pass

def parseToCompoundStatement(string):
    parenthesis_in = "("
    parenthesis_out = ")"
    quotes = "'\""
    escape = '\\'
    space = " "
    meta_marker = "\0"
    not_words = ["NOT"]
    and_words = ["AND"]
    or_words = ["OR"]

    def tokenize(string):
        tokens = []
        string = string.replace(meta_marker, "")
        quote = ""
        token = ""
        parentheses = parenthesis_in + parenthesis_out
        escaped = False
        in_token = False
        for char in string:
            if in_token and quote == "" and char in quotes + parentheses \
                    and not escaped:
                in_token = False
                tokens += [token]
                token = ""
            if not in_token:
                if char in quotes:
                    in_token = True
                    quote = char
                    token = meta_marker 
                    continue
                elif char in parentheses:
                    tokens += [char]
                    continue
                elif char == space:
                    continue
                else:
                    in_token = True
            if in_token:
                if not escaped:
                    if char == escape:
                        escaped = True
                        continue
                    if char == quote or (quote == "" and char == space):
                        if char == quote:
                            quote = ""
                        in_token = False
                        tokens += [token]
                        token = ""
                        continue
                else:
                    escaped = False
                token += char
        if quote:
            raise LogicParserError("Token not properly closed.")
        if in_token:
            tokens += [token]
        return tokens

    def parenthesize(tokens):
        open_parentheses = 0
        compounds = []
        def group_by_parentheses(i):
            nonlocal open_parentheses
            compound = []
            while i < len(tokens):
                if tokens[i] == parenthesis_in:
                    open_parentheses += 1
                    i, token = group_by_parentheses(i + 1)
                    compound += [token]
                elif tokens[i] == parenthesis_out:
                    open_parentheses -= 1
                    if open_parentheses < 0:
                        raise LogicParserError("Improper parentheses.")
                    return i + 1, compound
                else:
                    compound += [tokens[i]]
                    i += 1
            return i, compound
        _, compounds = group_by_parentheses(0)
        if open_parentheses > 0:
            raise LogicParserError("Improper parentheses.")
        return compounds

    def group_by_negation(tree):
        i = 0
        while i < len(tree):
            if type(tree[i]) == str and tree[i] in not_words:
                if i > len(tree) - 2:
                    raise LogicParserError("Improper negation.")
                # NOT A = [False, A]
                tree[i] = [False, tree[i + 1]]
                tree.pop(i + 1)
                if type(tree[i][1]) == list:
                    group_by_negation(tree[i][1])
            elif type(tree[i]) == list:
                group_by_negation(tree[i])
            i += 1

    def group_by_and(tree):
        i = 0
        if type(tree[i]) == bool:
            i += 1
        if type(tree[i]) == list:
            group_by_and(tree[i])
        if tree[i] in or_words + and_words:
            raise LogicParserError("Improper AND/OR placement.")
        while len(tree[i:]) > 1:
            if tree[i + 1] not in or_words + and_words:
                raise LogicParserError("Improper token grouping.")
            elif len(tree[i:]) < 3 or \
                    tree[i + 2] in or_words + and_words:
                raise LogicParserError("Improper AND/OR placement.")
            if type(tree[i + 2]) == list:
                group_by_and(tree[i + 2])
            if tree[i + 1] in and_words:
                # A AND B = NOT (NOT A OR NOT B)
                tree[i] = [False, [[False, tree[i]], [False, tree[i + 2]]]]
                tree.pop(i + 2)
                tree.pop(i + 1)
            else:
                i += 2

    def group_by_or(tree):
        i = 0
        if type(tree[i]) == bool:
            i += 1
        if type(tree[i]) == list:
            group_by_or(tree[i])
        if tree[i] in or_words:
            raise LogicParserError("Improper OR placement.")
        while len(tree[i:]) > 1:
            if tree[i + 1] in or_words:
                if type(tree[i + 2]) == list:
                    group_by_or(tree[i + 2])
                tree[i + 1] = tree[i + 2]
                tree.pop(i + 2)
            else:
                if type(tree[i + 1]) == list:
                    group_by_or(tree[i + 1])
                i += 1

    def flatten(tree):
        i = 0
        while i < len(tree):
            if type(tree[i]) == list:
                tree[i] = flatten(tree[i])
            i += 1
        if len(tree) == 1 and type(tree[0]) == list:
            # ( A ) = A
            tree = tree[0]
        if len(tree) == 2 and tree[0] == False and type(tree[1]) == list \
                and len(tree[1]) == 2 and tree[1][0] == False:
            # NOT NOT A = A
            tree = tree[1][1]
        return tree

    def strip_meta_marker(tree):
        i = 0
        while i < len(tree):
            if type(tree[i]) == list:
                strip_meta_marker(tree[i])
            elif type(tree[i]) == str:
                tree[i] = tree[i].replace(meta_marker, "")
            i += 1

    def toCompoundStatement(compounds):
        def transform(tree):
            negneg = True
            i = 0
            or_group = []
            if tree[0] == False:
                negneg = False
                i = 1
            while i < len(tree):
                if type(tree[i]) == list:
                    or_group += [transform(tree[i])]
                else:
                    or_group += [tree[i]]
                i += 1
            return CompoundStatement(or_group, negneg)
        return transform(compounds)

    tokens = tokenize(string)
    compounds = parenthesize(tokens) 
    group_by_negation(compounds)
    group_by_and(compounds)
    group_by_or(compounds)
    flatten(compounds)
    strip_meta_marker(compounds)
    return toCompoundStatement(compounds)

def search(query, string_list):

    def testStringMatchLogic(statement, compare_value):
        if type(statement) == str:
            statement_true = statement in compare_value 
        elif type(statement) == CompoundStatement:
            or_list_true = False
            if len(statement.or_list) > 1:
                for i_statement in statement.or_list:
                    if testStringMatchLogic(i_statement, compare_value):
                        or_list_true = True
                        break
            else:
                or_list_true = testStringMatchLogic(statement.or_list[0],
                        compare_value)
            if statement.neg:
                statement_true = not or_list_true
            else:
                statement_true = or_list_true
        return statement_true 

    results = []
    statement = parseToCompoundStatement(query)
    for i in range(len(string_list)):
        if testStringMatchLogic(statement, string_list[i]):
            results += [[i, string_list[i]]]
    return results

#TEST:
#lines = [
#"Hallo Welt,",
#"wie geht es dir,",
#"ist heut nicht ein schöner Tag?"
#]
#query = "NOT (geht OR 'ö')"
#for line in search(query, lines):
#    print(line)
