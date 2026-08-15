"""A small stdlib-only JavaScript/TypeScript tokenizer and recursive-descent parser.

The parser is deliberately best-effort: it recognises just enough of the
JavaScript/TypeScript surface to locate import/require declarations and to skip
the rest of the file safely. Malformed, partial or type-heavy input never
raises; on any syntax problem the parser recovers to the next statement
boundary and keeps going.
"""

from __future__ import annotations


class Node:
    """Generic AST node."""

    def __init__(self, type, start, end, children=None, **attrs):
        self.type = type
        self.start = start
        self.end = end
        self.children = children if children is not None else []
        for name, value in attrs.items():
            setattr(self, name, value)


class Token:
    __slots__ = ("type", "value", "raw", "start", "end", "source", "parts")

    def __init__(self, type, value, raw, start, end, source=None, parts=None):
        self.type = type
        self.value = value
        self.raw = raw
        self.start = start
        self.end = end
        self.source = source
        self.parts = parts


class _ParseError(Exception):
    pass


_OPERATORS = (
    ">>>=", "===", "!==", "**=", "<<=", ">>=", "&&=", "||=", "??=", ">>>",
    "==", "!=", "&&", "||", "??", "?.", "=>", "++", "--", "+=", "-=", "*=",
    "/=", "%=", "&=", "|=", "^=", "<<", ">>", "<=", ">=", "**", "...",
    "{", "}", "(", ")", "[", "]", ";", ",", ".", ":", "?", "=", "<", ">",
    "!", "~", "+", "-", "*", "/", "%", "&", "|", "^", "@", "#",
)
_SORTED_OPERATORS = tuple(sorted(_OPERATORS, key=len, reverse=True))

_OPERAND_ENDING = {"}", ")", "]", "++", "--"}

_OPERAND_KEYWORDS = {
    "as", "await", "case", "delete", "do", "else", "export", "extends", "for",
    "if", "import", "in", "instanceof", "new", "of", "return", "satisfies",
    "switch", "throw", "typeof", "void", "while", "with", "yield",
}

BINARY_PRECEDENCE = {
    "??": 1, "||": 2, "&&": 3, "|": 4, "^": 5, "&": 6,
    "==": 7, "!=": 7, "===": 7, "!==": 7,
    "<": 8, ">": 8, "<=": 8, ">=": 8,
    "<<": 9, ">>": 9, ">>>": 9,
    "+": 10, "-": 10,
    "*": 11, "/": 11, "%": 11,
    "**": 12,
}
BINARY_KEYWORDS = {"in": 8, "instanceof": 8, "as": 8, "satisfies": 8}

ASSIGNMENT_OPS = {
    "=", "+=", "-=", "*=", "/=", "%=", "<<=", ">>=", ">>>=", "&=", "|=",
    "^=", "&&=", "||=", "??=", "**=",
}

_SIMPLE_ESCAPES = {
    "n": "\n", "t": "\t", "r": "\r", "b": "\b", "f": "\f", "v": "\v",
    "0": "\0", "\\": "\\", "'": "'", '"': '"', "`": "`", "/": "/",
    "a": "\a", "e": "\x1b",
}


def _decode_string(raw, quote):
    if len(raw) < 2:
        return raw
    body = raw[1:-1] if raw.endswith(quote) else raw[1:]
    out = []
    i = 0
    n = len(body)
    while i < n:
        char = body[i]
        if char == "\\" and i + 1 < n:
            nxt = body[i + 1]
            if nxt in _SIMPLE_ESCAPES:
                out.append(_SIMPLE_ESCAPES[nxt])
                i += 2
                continue
            if nxt == "x" and i + 3 < n:
                try:
                    out.append(chr(int(body[i + 2:i + 4], 16)))
                    i += 4
                    continue
                except ValueError:
                    pass
            if nxt == "u" and i + 5 < n:
                try:
                    out.append(chr(int(body[i + 2:i + 6], 16)))
                    i += 6
                    continue
                except ValueError:
                    pass
            if nxt == "\r" or nxt == "\n":
                if nxt == "\r" and i + 2 < n and body[i + 2] == "\n":
                    i += 3
                else:
                    i += 2
                continue
            out.append(nxt)
            i += 2
            continue
        out.append(char)
        i += 1
    return "".join(out)


class Tokenizer:
    """Tokenises a source string, hiding comments/strings/templates/regexes.

    ``base`` offsets the reported token positions so that tokens produced from
    a template-literal ``${...}`` substring still carry absolute offsets into
    the original source.
    """

    def __init__(self, source, base=0):
        self.src = source
        self.base = base
        self.n = len(source)
        self.i = 0
        self._start = 0
        self._operand_expected = True
        self.tokens = []

    # ---- scanning helpers -------------------------------------------------

    def _line_comment_end(self, i):
        n = self.n
        while i < n and self.src[i] not in "\n\r":
            i += 1
        return i

    def _block_comment_end(self, i):
        n = self.n
        i += 2
        while i + 1 < n:
            if self.src[i] == "*" and self.src[i + 1] == "/":
                return i + 2
            i += 1
        return n

    def _string_end(self, i):
        n = self.n
        quote = self.src[i]
        i += 1
        while i < n:
            char = self.src[i]
            if char == "\\":
                i += 2
                continue
            if char == quote:
                return i + 1
            i += 1
        return n

    def _template_end(self, i):
        n = self.n
        i += 1
        while i < n:
            char = self.src[i]
            if char == "\\":
                i += 2
                continue
            if char == "`":
                return i + 1
            if char == "$" and i + 1 < n and self.src[i + 1] == "{":
                i = self._skip_balanced(i + 1, "{", "}")
                continue
            i += 1
        return n

    def _skip_balanced(self, start, open_ch, close_ch):
        n = self.n
        depth = 0
        i = start
        while i < n:
            char = self.src[i]
            if char == open_ch:
                depth += 1
            elif char == close_ch:
                depth -= 1
                if depth == 0:
                    return i + 1
            elif char == "'" or char == '"':
                i = self._string_end(i)
                continue
            elif char == "`":
                i = self._template_end(i)
                continue
            elif char == "/" and i + 1 < n and self.src[i + 1] == "/":
                i = self._line_comment_end(i)
                continue
            elif char == "/" and i + 1 < n and self.src[i + 1] == "*":
                i = self._block_comment_end(i)
                continue
            i += 1
        return n

    # ---- token readers ----------------------------------------------------

    def _after_token(self, tok):
        if tok.type == "name":
            self._operand_expected = tok.value in _OPERAND_KEYWORDS
        elif tok.type == "punct":
            self._operand_expected = tok.value not in _OPERAND_ENDING
        else:
            self._operand_expected = True

    def _emit(self, type, value, raw, **extra):
        tok = Token(
            type,
            value,
            raw,
            self.base + self._start,
            self.base + self.i,
            **extra,
        )
        self.tokens.append(tok)
        self._after_token(tok)

    def _read_string(self):
        start = self.i
        quote = self.src[start]
        i = start + 1
        n = self.n
        while i < n:
            char = self.src[i]
            if char == "\\":
                if i + 1 >= n:
                    i = n
                else:
                    nxt = self.src[i + 1]
                    if nxt == "\r":
                        i += 2
                        if i < n and self.src[i] == "\n":
                            i += 1
                    elif nxt == "\n":
                        i += 2
                    else:
                        i += 2
                continue
            if char == quote:
                i += 1
                break
            i += 1
        self.i = i
        raw = self.src[start:i]
        decoded = _decode_string(raw, quote)
        tok = Token(
            "string",
            decoded,
            raw,
            self.base + start,
            self.base + i,
            source=decoded,
        )
        self.tokens.append(tok)
        self._operand_expected = True

    def _read_template(self):
        start = self.i
        i = start + 1
        n = self.n
        parts = []
        buf = []
        while i < n:
            char = self.src[i]
            if char == "\\":
                if i + 1 < n:
                    buf.append(self.src[i:i + 2])
                    i += 2
                else:
                    buf.append(char)
                    i += 1
                continue
            if char == "`":
                i += 1
                break
            if char == "$" and i + 1 < n and self.src[i + 1] == "{":
                parts.append(("text", "".join(buf)))
                buf = []
                end = self._skip_balanced(i + 1, "{", "}")
                inner = self.src[i + 2:end - 1] if end - 1 > i + 2 else ""
                inner_tokens = (
                    Tokenizer(inner, base=self.base + i + 2).tokenize()
                    if inner
                    else []
                )
                parts.append(("expr", inner_tokens))
                i = end
                continue
            buf.append(char)
            i += 1
        parts.append(("text", "".join(buf)))
        self.i = i
        raw = self.src[start:i]
        tok = Token(
            "template",
            raw,
            raw,
            self.base + start,
            self.base + i,
            parts=parts,
        )
        self.tokens.append(tok)
        self._operand_expected = True

    def _try_read_regex(self):
        start = self.i
        i = start + 1
        n = self.n
        in_class = False
        while i < n:
            char = self.src[i]
            if char == "\\":
                i += 2
                continue
            if char == "\n" or char == "\r":
                return False
            if char == "[":
                in_class = True
            elif char == "]":
                in_class = False
            elif char == "/" and not in_class:
                i += 1
                while i < n and self.src[i].isalpha():
                    i += 1
                self.i = i
                raw = self.src[start:i]
                tok = Token(
                    "regex",
                    raw,
                    raw,
                    self.base + start,
                    self.base + i,
                )
                self.tokens.append(tok)
                self._operand_expected = True
                return True
            i += 1
        return False

    def _read_number(self):
        start = self.i
        src = self.src
        n = self.n
        i = start
        if src[i] == "0" and i + 1 < n and src[i + 1] in "xXbBoO":
            i += 2
            while i < n and (
                src[i].isdigit() or src[i].lower() in "abcdef" or src[i] == "_"
            ):
                i += 1
        else:
            while i < n and (src[i].isdigit() or src[i] == "_"):
                i += 1
            if i < n and src[i] == "." and i + 1 < n and src[i + 1].isdigit():
                i += 1
                while i < n and (src[i].isdigit() or src[i] == "_"):
                    i += 1
            if i < n and src[i] in "eE":
                j = i + 1
                if j < n and src[j] in "+-":
                    j += 1
                if j < n and src[j].isdigit():
                    i = j
                    while i < n and src[i].isdigit():
                        i += 1
        if i < n and src[i] == "n":
            i += 1
        self.i = i
        self._emit("number", src[start:i], src[start:i])

    def _read_name(self):
        start = self.i
        src = self.src
        n = self.n
        i = start
        while i < n and (src[i].isalnum() or src[i] in "_$"):
            i += 1
        self.i = i
        text = src[start:i]
        self._emit("name", text, text)

    def _read_operator(self):
        src = self.src
        for op in _SORTED_OPERATORS:
            if src.startswith(op, self.i):
                self.i += len(op)
                self._emit("punct", op, op)
                return
        char = src[self.i]
        self.i += 1
        self._emit("punct", char, char)

    # ---- entry point ------------------------------------------------------

    def tokenize(self):
        src = self.src
        n = self.n
        while self.i < n:
            char = src[self.i]
            if char == "\ufeff":
                self.i += 1
                continue
            if char.isspace():
                self.i += 1
                continue
            self._start = self.i
            if char == "/" and self.i + 1 < n:
                nxt = src[self.i + 1]
                if nxt == "/":
                    self.i = self._line_comment_end(self.i)
                    continue
                if nxt == "*":
                    self.i = self._block_comment_end(self.i)
                    continue
            if char == "'" or char == '"':
                self._read_string()
                continue
            if char == "`":
                self._read_template()
                continue
            if char == "/" and self._operand_expected:
                if self._try_read_regex():
                    continue
            if char.isdigit() or (
                char == "." and self.i + 1 < n and src[self.i + 1].isdigit()
            ):
                self._read_number()
                continue
            if char.isalpha() or char in "_$":
                self._read_name()
                continue
            self._read_operator()
        return self.tokens


def parse(source):
    """Parse ``source`` and return a ``Node`` of type ``"Module"``."""
    source = str(source)
    try:
        tokens = Tokenizer(source).tokenize()
        parser = Parser(source, tokens)
        return parser.parse()
    except Exception:
        return Node("Module", 0, len(source), children=[])


class Parser:
    def __init__(self, source, tokens):
        self.source = source
        self.tokens = tokens
        self.pos = 0
        self._eof = Token("eof", "", "", len(source), len(source))

    @property
    def current(self):
        if self.pos < len(self.tokens):
            return self.tokens[self.pos]
        return self._eof

    def peek(self, k=1):
        idx = self.pos + k
        if idx < len(self.tokens):
            return self.tokens[idx]
        return self._eof

    def advance(self):
        tok = self.current
        self.pos += 1
        return tok

    def _at(self, type, value=None):
        tok = self.current
        if tok.type != type:
            return False
        if value is not None and tok.value != value:
            return False
        return True

    def _last_end(self):
        if self.pos > 0:
            return self.tokens[self.pos - 1].end
        return 0

    def _node(self, type, start, end, children=None, **attrs):
        return Node(type, start, end, children=children, **attrs)

    def _matching_paren(self, pos):
        depth = 0
        i = pos
        n = len(self.tokens)
        while i < n:
            tok = self.tokens[i]
            if tok.type == "punct":
                if tok.value == "(":
                    depth += 1
                elif tok.value == ")":
                    depth -= 1
                    if depth == 0:
                        return i
            i += 1
        return None

    def _scan_arrow_after(self, pos):
        i = pos + 1
        n = len(self.tokens)
        if i >= n:
            return False
        tok = self.tokens[i]
        if tok.type == "punct" and tok.value == "=>":
            return True
        if tok.type == "punct" and tok.value == ":":
            i += 1
            while i < n:
                t = self.tokens[i]
                if t.type == "punct":
                    if t.value == "=>":
                        return True
                    if t.value in (";", "}", "=", ","):
                        return False
                i += 1
            return False
        return False

    # ---- recovery helpers -------------------------------------------------

    def _recover_statement(self):
        while True:
            tok = self.current
            if tok.type == "eof":
                return
            if tok.type == "punct":
                if tok.value == ";":
                    self.advance()
                    return
                if tok.value == "}":
                    return
            self.advance()

    def _skip_to_matching(self, close):
        depth = 0
        while True:
            tok = self.current
            if tok.type == "eof":
                return
            if tok.type == "punct":
                v = tok.value
                if v in ("(", "[", "{"):
                    depth += 1
                elif v in (")", "]", "}"):
                    depth -= 1
                    if depth <= 0:
                        self.advance()
                        return
            self.advance()

    def _skip_balanced_brace(self):
        self._skip_to_matching("}")

    def _skip_until_colon(self):
        depth = 0
        while True:
            tok = self.current
            if tok.type == "eof":
                return
            if tok.type == "punct":
                v = tok.value
                if v in ("(", "[", "{"):
                    depth += 1
                elif v in (")", "]", "}"):
                    if depth > 0:
                        depth -= 1
                    else:
                        return
                elif v == ":" and depth == 0:
                    self.advance()
                    return
            self.advance()

    def _skip_to_comma_or_close(self):
        while True:
            tok = self.current
            if tok.type == "eof":
                return
            if tok.type == "punct" and tok.value in (",", ")", "]", "}"):
                return
            self.advance()

    def _skip_until_brace(self):
        while True:
            tok = self.current
            if tok.type == "eof":
                return
            if tok.type == "punct" and tok.value in ("{", ";"):
                return
            self.advance()

    def _skip_type_annotation(self):
        """Skip a TS type annotation; ``self.current`` is the leading ``:``."""
        self.advance()
        if self._at("punct", "{"):
            self._skip_balanced_brace()
            return
        depth = 0
        while True:
            tok = self.current
            if tok.type == "eof":
                return
            if tok.type == "punct":
                v = tok.value
                if v == "{":
                    if depth == 0:
                        return
                    depth += 1
                elif v in ("(", "["):
                    depth += 1
                elif v == "<":
                    depth += 1
                elif v in (")", "]", "}", ">"):
                    if depth > 0:
                        depth -= 1
                    else:
                        return
                elif depth == 0 and v in (";", "=", "=>", ":", ","):
                    return
            self.advance()

    def _skip_generic_type_params(self):
        depth = 0
        while True:
            tok = self.current
            if tok.type == "eof":
                return
            if tok.type == "punct":
                v = tok.value
                if v == "<":
                    depth += 1
                elif v == ">":
                    depth -= 1
                    if depth <= 0:
                        self.advance()
                        return
            self.advance()

    def _skip_semi(self):
        if self._at("punct", ";"):
            self.advance()

    # ---- statements -------------------------------------------------------

    def parse(self):
        module = self._node("Module", 0, len(self.source), children=[])
        while True:
            if self._at("eof"):
                break
            prev = self.pos
            try:
                stmt = self.parse_statement()
            except _ParseError:
                self._recover_statement()
                stmt = None
            if stmt is not None:
                module.children.append(stmt)
            if self.pos <= prev:
                self.advance()
        module.end = self._last_end()
        return module

    def parse_statement(self):
        tok = self.current
        if tok.type == "eof":
            return None
        if tok.type == "punct":
            if tok.value == ";":
                self.advance()
                return None
            if tok.value == "}":
                return None
        try:
            return self._parse_statement_inner()
        except _ParseError:
            self._recover_statement()
            return None

    def _parse_statement_inner(self):
        tok = self.current
        if tok.type == "punct":
            if tok.value == "{":
                return self.parse_block()
        elif tok.type == "name":
            v = tok.value
            if v == "import":
                if self.peek(1).type == "punct" and self.peek(1).value == "(":
                    return self.parse_import_expression()
                return self._parse_import_statement()
            if v == "export":
                return self.parse_export_declaration()
            if v in ("var", "let", "const"):
                return self.parse_variable_declaration()
            if v == "function":
                return self._parse_function_like(tok.start, "FunctionDeclaration")
            if (
                v == "async"
                and self.peek(1).type == "name"
                and self.peek(1).value == "function"
            ):
                self.advance()
                return self._parse_function_like(self.current.start, "FunctionDeclaration")
            if v == "class":
                return self._parse_class_like(tok.start, "ClassDeclaration")
            if v in ("interface", "type", "enum", "declare", "abstract"):
                return self.skip_ts_declaration()
            if v == "return":
                return self.parse_return_statement()
            if v == "throw":
                return self.parse_throw_statement()
            if v in ("break", "continue"):
                return self.parse_break_continue()
            if v in ("if", "while"):
                return self.parse_if_while()
            if v == "for":
                return self.parse_for()
            if v == "do":
                return self.parse_do()
            if v == "switch":
                return self.parse_switch()
            if v == "try":
                return self.parse_try()
            if v in ("case", "default"):
                self._skip_until_colon()
                return None
            if (
                self.peek(1).type == "punct"
                and self.peek(1).value == ":"
                and not (self.peek(2).type == "punct" and self.peek(2).value == ":")
            ):
                self.advance()
                self.advance()
                return self._parse_statement_inner()
        return self.parse_expression_statement()

    def parse_block(self):
        start = self.current.start
        self.advance()
        node = self._node("BlockStatement", start, self._last_end(), children=[])
        while True:
            if self._at("eof"):
                break
            if self._at("punct", "}"):
                self.advance()
                break
            prev = self.pos
            try:
                stmt = self.parse_statement()
            except _ParseError:
                self._recover_statement()
                stmt = None
            if stmt is not None:
                node.children.append(stmt)
            if self.pos <= prev:
                self.advance()
        node.end = self._last_end()
        return node

    # ---- declarations -----------------------------------------------------

    def _parse_import_statement(self):
        start = self.current.start
        self.advance()  # import
        if self._at("punct", "("):
            return self.parse_import_expression()
        if self._at("punct", "."):
            ident = self._node("Identifier", start, start + len("import"), name="import")
            try:
                return self._postfix_tail(ident)
            except _ParseError:
                return ident
        node = self._node("ImportDeclaration", start, self._last_end(), source=None, children=[])
        if self.current.type == "string":
            strnode = self._advance_string_node()
            node.source = strnode.source
            node.children.append(strnode)
            node.end = self._last_end()
            self._skip_semi()
            return node
        depth = 0
        while True:
            tok = self.current
            if tok.type == "eof":
                break
            if tok.type == "punct":
                v = tok.value
                if v == "{":
                    depth += 1
                elif v == "}":
                    if depth == 0:
                        break
                    depth -= 1
                elif v == "(":
                    depth += 1
                elif v == ")":
                    if depth > 0:
                        depth -= 1
                elif v == ";":
                    if depth == 0:
                        break
                elif v == "=" and depth == 0:
                    self.advance()
                    if (
                        self._at("name", "require")
                        and self.peek(1).type == "punct"
                        and self.peek(1).value == "("
                    ):
                        call = self._parse_require_call()
                        node.children.append(call)
                    continue
            elif tok.type == "name":
                if depth == 0 and tok.value == "from":
                    self.advance()
                    if self.current.type == "string":
                        strnode = self._advance_string_node()
                        node.source = strnode.source
                        node.children.append(strnode)
                    break
            self.advance()
        node.end = self._last_end()
        self._skip_semi()
        return node

    def parse_import_expression(self):
        start = self.current.start
        self.advance()  # import
        node = self._node("ImportExpression", start, self._last_end(), children=[])
        if self._at("punct", "("):
            args = self._parse_arguments()
            node.children.extend(args)
            node.end = self._last_end()
        return node

    def _parse_require_call(self):
        tok = self.current
        self.advance()  # require
        callee = self._node("Identifier", tok.start, tok.end, name="require")
        args = []
        if self._at("punct", "("):
            args = self._parse_arguments()
        return self._node(
            "CallExpression",
            tok.start,
            self._last_end(),
            children=[callee] + args,
        )

    def _advance_string_node(self):
        tok = self.current
        self.advance()
        return self._node(
            "StringLiteral",
            tok.start,
            tok.end,
            value=tok.value,
            source=tok.source,
            raw=tok.raw,
        )

    def parse_export_declaration(self):
        start = self.current.start
        self.advance()  # export
        if (
            self._at("name", "type")
            and self.peek(1).type == "punct"
            and self.peek(1).value in ("{", "*")
        ):
            self.advance()
        if self._at("punct", "*"):
            self.advance()
            node = self._node(
                "ExportAllDeclaration", start, self._last_end(), source=None, children=[]
            )
            if self._at("name", "as"):
                self.advance()
                if self._at("name"):
                    self.advance()
            if self._at("name", "from"):
                self.advance()
                if self.current.type == "string":
                    strnode = self._advance_string_node()
                    node.source = strnode.source
                    node.children.append(strnode)
            node.end = self._last_end()
            self._skip_semi()
            return node
        if self._at("punct", "{"):
            node = self._node(
                "ExportNamedDeclaration", start, self._last_end(), source=None, children=[]
            )
            self._skip_to_matching("}")
            if self._at("name", "from"):
                self.advance()
                if self.current.type == "string":
                    strnode = self._advance_string_node()
                    node.source = strnode.source
                    node.children.append(strnode)
            node.end = self._last_end()
            self._skip_semi()
            return node
        if self._at("punct", "="):
            return self.parse_expression_statement()
        if self._at("name"):
            v = self.current.value
            if v == "default":
                self.advance()
                if self._at("name", "function"):
                    return self._parse_function_like(self.current.start, "FunctionDeclaration")
                if self._at("name", "class"):
                    return self._parse_class_like(self.current.start, "ClassDeclaration")
                if (
                    self._at("name", "async")
                    and self.peek(1).type == "name"
                    and self.peek(1).value == "function"
                ):
                    self.advance()
                    return self._parse_function_like(self.current.start, "FunctionDeclaration")
                if self._at("name", "interface"):
                    return self.skip_ts_declaration()
                return self.parse_expression_statement()
            if v in ("var", "let", "const"):
                return self.parse_variable_declaration()
            if v == "function":
                return self._parse_function_like(self.current.start, "FunctionDeclaration")
            if (
                v == "async"
                and self.peek(1).type == "name"
                and self.peek(1).value == "function"
            ):
                self.advance()
                return self._parse_function_like(self.current.start, "FunctionDeclaration")
            if v == "class":
                return self._parse_class_like(self.current.start, "ClassDeclaration")
            if v in ("interface", "type", "enum", "declare", "abstract"):
                return self.skip_ts_declaration()
        return self.parse_expression_statement()

    def parse_variable_declaration(self):
        start = self.current.start
        self.advance()  # var/let/const
        node = self._node("VariableDeclaration", start, self._last_end(), children=[])
        while True:
            if self._at("eof") or self._at("punct", ";"):
                break
            declarator = self._node(
                "VariableDeclarator", self.current.start, self.current.start, children=[]
            )
            self._skip_binding()
            if self._at("punct", ":"):
                self._skip_type_annotation()
            if self._at("punct", "="):
                self.advance()
                try:
                    init = self.parse_assignment()
                except _ParseError:
                    init = None
                if init is not None:
                    declarator.children.append(init)
                declarator.end = self._last_end()
            node.children.append(declarator)
            if self._at("punct", ","):
                self.advance()
                continue
            break
        node.end = self._last_end()
        self._skip_semi()
        return node

    def _skip_binding(self):
        if self._at("punct", "{"):
            self._skip_to_matching("}")
            return
        if self._at("punct", "["):
            self._skip_to_matching("]")
            return
        if self._at("name"):
            self.advance()
            return
        self.advance()

    def _parse_function_like(self, start, node_type):
        self.advance()  # function
        if self._at("punct", "*"):
            self.advance()
        if self._at("name"):
            self.advance()
        if self._at("punct", "<"):
            self._skip_generic_type_params()
        if self._at("punct", "("):
            self._skip_to_matching(")")
        if self._at("punct", ":"):
            self._skip_type_annotation()
        children = []
        if self._at("punct", "{"):
            body = self.parse_block()
            children.append(body)
        return self._node(node_type, start, self._last_end(), children=children)

    def _parse_class_like(self, start, node_type):
        self.advance()  # class
        if self._at("name"):
            self.advance()
        if self._at("name", "extends"):
            self.advance()
            try:
                self.parse_postfix()
            except _ParseError:
                pass
        if self._at("name", "implements"):
            self.advance()
            self._skip_until_brace()
        if self._at("punct", "{"):
            self._skip_balanced_brace()
        return self._node(node_type, start, self._last_end(), children=[])

    def skip_ts_declaration(self):
        start = self.current.start
        self.advance()
        depth = 0
        while True:
            tok = self.current
            if tok.type == "eof":
                break
            if tok.type == "punct":
                v = tok.value
                if v in ("(", "[", "{"):
                    depth += 1
                elif v == "<":
                    depth += 1
                elif v in (")", "]", "}"):
                    if depth > 0:
                        depth -= 1
                    else:
                        break
                elif v == ">":
                    if depth > 0:
                        depth -= 1
                elif depth == 0 and v == ";":
                    self.advance()
                    break
            self.advance()
        return self._node("TypeAliasDeclaration", start, self._last_end(), children=[])

    # ---- control flow -----------------------------------------------------

    def parse_return_statement(self):
        start = self.current.start
        self.advance()  # return
        node = self._node("ReturnStatement", start, self._last_end(), children=[])
        if self._at("punct", ";") or self._at("punct", "}") or self._at("eof"):
            if self._at("punct", ";"):
                self.advance()
            return node
        try:
            arg = self.parse_assignment()
        except _ParseError:
            arg = None
        if arg is not None:
            node.children.append(arg)
        node.end = self._last_end()
        self._skip_semi()
        return node

    def parse_throw_statement(self):
        start = self.current.start
        self.advance()  # throw
        node = self._node("ThrowStatement", start, self._last_end(), children=[])
        try:
            arg = self.parse_assignment()
        except _ParseError:
            arg = None
        if arg is not None:
            node.children.append(arg)
        node.end = self._last_end()
        self._skip_semi()
        return node

    def parse_break_continue(self):
        start = self.current.start
        value = self.current.value
        self.advance()
        node = self._node(
            "BreakStatement" if value == "break" else "ContinueStatement",
            start,
            self._last_end(),
            children=[],
        )
        if self._at("name"):
            self.advance()
        node.end = self._last_end()
        self._skip_semi()
        return node

    def parse_if_while(self):
        start = self.current.start
        kind = self.current.value
        self.advance()
        if self._at("punct", "("):
            self._skip_to_matching(")")
        node = self._node(
            "IfStatement" if kind == "if" else "WhileStatement",
            start,
            self._last_end(),
            children=[],
        )
        body = self.parse_statement()
        if body is not None:
            node.children.append(body)
        if kind == "if" and self._at("name", "else"):
            self.advance()
            alternative = self.parse_statement()
            if alternative is not None:
                node.children.append(alternative)
        node.end = self._last_end()
        return node

    def parse_for(self):
        start = self.current.start
        self.advance()  # for
        if self._at("name", "await"):
            self.advance()
        if self._at("punct", "("):
            self._skip_to_matching(")")
        node = self._node("ForStatement", start, self._last_end(), children=[])
        body = self.parse_statement()
        if body is not None:
            node.children.append(body)
        node.end = self._last_end()
        return node

    def parse_do(self):
        start = self.current.start
        self.advance()  # do
        node = self._node("DoWhileStatement", start, self._last_end(), children=[])
        body = self.parse_statement()
        if body is not None:
            node.children.append(body)
        if self._at("name", "while"):
            self.advance()
            if self._at("punct", "("):
                self._skip_to_matching(")")
        self._skip_semi()
        node.end = self._last_end()
        return node

    def parse_switch(self):
        start = self.current.start
        self.advance()  # switch
        if self._at("punct", "("):
            self._skip_to_matching(")")
        node = self._node("SwitchStatement", start, self._last_end(), children=[])
        if self._at("punct", "{"):
            block = self.parse_block()
            node.children.append(block)
        node.end = self._last_end()
        return node

    def parse_try(self):
        start = self.current.start
        self.advance()  # try
        node = self._node("TryStatement", start, self._last_end(), children=[])
        body = self.parse_statement()
        if body is not None:
            node.children.append(body)
        while True:
            if self._at("name", "catch"):
                self.advance()
                if self._at("punct", "("):
                    self._skip_to_matching(")")
                clause = self.parse_statement()
                if clause is not None:
                    node.children.append(clause)
            elif self._at("name", "finally"):
                self.advance()
                clause = self.parse_statement()
                if clause is not None:
                    node.children.append(clause)
            else:
                break
        node.end = self._last_end()
        return node

    # ---- expressions ------------------------------------------------------

    def parse_expression_statement(self):
        try:
            expr = self.parse_assignment()
        except _ParseError:
            self._recover_statement()
            return None
        self._skip_semi()
        return expr

    def parse_assignment(self):
        if self._looks_like_arrow():
            return self.parse_arrow_function()
        start = self.current.start
        left = self.parse_conditional()
        tok = self.current
        if tok.type == "punct" and tok.value in ASSIGNMENT_OPS:
            self.advance()
            try:
                right = self.parse_assignment()
            except _ParseError:
                right = None
            children = [c for c in (left, right) if c is not None]
            return self._node("AssignmentExpression", start, self._last_end(), children=children)
        return left

    def _looks_like_arrow(self):
        tok = self.current
        if tok.type == "name":
            if self.peek(1).type == "punct" and self.peek(1).value == "=>":
                return True
            if tok.value == "async":
                n1 = self.peek(1)
                if n1.type == "punct" and n1.value == "(":
                    end = self._matching_paren(self.pos + 1)
                    if end is not None:
                        return self._scan_arrow_after(end)
                if (
                    n1.type == "name"
                    and self.peek(2).type == "punct"
                    and self.peek(2).value == "=>"
                ):
                    return True
            return False
        if tok.type == "punct" and tok.value == "(":
            end = self._matching_paren(self.pos)
            if end is not None:
                return self._scan_arrow_after(end)
        return False

    def parse_arrow_function(self):
        start = self.current.start
        if self._at("name", "async"):
            self.advance()
            if self._at("punct", "("):
                self._skip_to_matching(")")
            elif self._at("name"):
                self.advance()
        elif self._at("punct", "("):
            self._skip_to_matching(")")
        elif self._at("name"):
            self.advance()
        if self._at("punct", ":"):
            self._skip_type_annotation()
        if self._at("punct", "=>"):
            self.advance()
        body = None
        if self._at("punct", "{"):
            body = self.parse_block()
        else:
            try:
                body = self.parse_assignment()
            except _ParseError:
                body = None
        children = [body] if body is not None else []
        return self._node("ArrowFunctionExpression", start, self._last_end(), children=children)

    def parse_conditional(self):
        start = self.current.start
        condition = self.parse_binary(0)
        if self._at("punct", "?"):
            self.advance()
            try:
                then_expr = self.parse_assignment()
            except _ParseError:
                then_expr = None
            if self._at("punct", ":"):
                self.advance()
                try:
                    else_expr = self.parse_assignment()
                except _ParseError:
                    else_expr = None
            else:
                else_expr = None
            children = [c for c in (condition, then_expr, else_expr) if c is not None]
            return self._node("ConditionalExpression", start, self._last_end(), children=children)
        return condition

    def _binary_precedence(self, tok):
        if tok.type == "punct":
            return BINARY_PRECEDENCE.get(tok.value)
        if tok.type == "name":
            return BINARY_KEYWORDS.get(tok.value)
        return None

    def parse_binary(self, min_prec):
        left = self.parse_unary()
        while True:
            tok = self.current
            prec = self._binary_precedence(tok)
            if prec is None or prec < min_prec:
                break
            op = tok.value
            self.advance()
            next_prec = prec + (0 if op == "**" else 1)
            try:
                right = self.parse_binary(next_prec)
            except _ParseError:
                right = None
            children = [c for c in (left, right) if c is not None]
            left = self._node(
                "BinaryExpression",
                left.start,
                self._last_end(),
                children=children,
                operator=op,
            )
        return left

    def parse_unary(self):
        tok = self.current
        if tok.type == "punct" and tok.value in ("!", "~", "+", "-", "++", "--"):
            self.advance()
            try:
                operand = self.parse_unary()
            except _ParseError:
                operand = None
            children = [operand] if operand is not None else []
            return self._node(
                "UnaryExpression", tok.start, self._last_end(), children=children,
                operator=tok.value,
            )
        if tok.type == "name" and tok.value in ("typeof", "void", "delete", "await", "yield"):
            self.advance()
            if tok.value == "yield" and self._at("punct", "*"):
                self.advance()
            try:
                operand = self.parse_unary()
            except _ParseError:
                operand = None
            children = [operand] if operand is not None else []
            return self._node(
                "UnaryExpression", tok.start, self._last_end(), children=children,
                operator=tok.value,
            )
        if tok.type == "name" and tok.value == "new":
            return self.parse_new()
        return self.parse_postfix()

    def parse_new(self):
        start = self.current.start
        self.advance()  # new
        try:
            callee = self.parse_postfix()
        except _ParseError:
            callee = None
        args = []
        if self._at("punct", "("):
            args = self._parse_arguments()
        children = [c for c in [callee] + args if c is not None]
        return self._node("NewExpression", start, self._last_end(), children=children)

    def parse_postfix(self):
        return self._postfix_tail(self.parse_primary())

    def _postfix_tail(self, expr):
        while True:
            tok = self.current
            if tok.type == "punct":
                v = tok.value
                if v == ".":
                    self.advance()
                    try:
                        prop = self._parse_property_name()
                    except _ParseError:
                        break
                    expr = self._node(
                        "MemberExpression", expr.start, prop.end, children=[expr, prop]
                    )
                    continue
                if v == "?.":
                    self.advance()
                    if self._at("punct", "("):
                        args = self._parse_arguments()
                        expr = self._node(
                            "CallExpression",
                            expr.start,
                            self._last_end(),
                            children=[expr] + args,
                        )
                    elif self._at("punct", "["):
                        self.advance()
                        self._skip_to_matching("]")
                        expr = self._node(
                            "MemberExpression", expr.start, self._last_end(), children=[expr]
                        )
                    else:
                        try:
                            prop = self._parse_property_name()
                        except _ParseError:
                            break
                        expr = self._node(
                            "MemberExpression", expr.start, prop.end, children=[expr, prop]
                        )
                    continue
                if v == "[":
                    self.advance()
                    self._skip_to_matching("]")
                    expr = self._node(
                        "MemberExpression", expr.start, self._last_end(), children=[expr]
                    )
                    continue
                if v == "(":
                    args = self._parse_arguments()
                    expr = self._node(
                        "CallExpression", expr.start, self._last_end(), children=[expr] + args
                    )
                    continue
                if v in ("++", "--"):
                    self.advance()
                    expr = self._node(
                        "UpdateExpression", expr.start, self._last_end(), children=[expr]
                    )
                    continue
                break
            else:
                break
        return expr

    def _parse_property_name(self):
        tok = self.current
        if tok.type == "name":
            self.advance()
            return self._node("Identifier", tok.start, tok.end, name=tok.value)
        if tok.type in ("string", "number"):
            self.advance()
            return self._node("Literal", tok.start, tok.end)
        if tok.type == "punct" and tok.value == "#":
            self.advance()
            name_tok = self.current
            if name_tok.type == "name":
                self.advance()
                return self._node("Identifier", tok.start, name_tok.end, name=name_tok.value)
            return self._node("Identifier", tok.start, self._last_end(), name="#")
        raise _ParseError("expected property name")

    def _parse_arguments(self):
        self.advance()  # (
        args = []
        while True:
            tok = self.current
            if tok.type == "eof":
                break
            if tok.type == "punct":
                if tok.value == ")":
                    self.advance()
                    break
                if tok.value == ",":
                    self.advance()
                    continue
                if tok.value == "...":
                    self.advance()
            try:
                arg = self.parse_assignment()
                args.append(arg)
            except _ParseError:
                self._skip_to_comma_or_close()
                continue
            if self._at("punct", ")"):
                self.advance()
                break
            if self._at("punct", ","):
                self.advance()
                continue
            self.advance()
        return args

    def parse_primary(self):
        tok = self.current
        t = tok.type
        if t == "string":
            self.advance()
            return self._node(
                "StringLiteral",
                tok.start,
                tok.end,
                value=tok.value,
                source=tok.source,
                raw=tok.raw,
            )
        if t == "number":
            self.advance()
            return self._node("NumericLiteral", tok.start, tok.end, value=tok.value)
        if t == "regex":
            self.advance()
            return self._node("RegExpLiteral", tok.start, tok.end, value=tok.value)
        if t == "template":
            return self._parse_template()
        if t == "name":
            v = tok.value
            if v == "import" and self.peek(1).type == "punct" and self.peek(1).value == "(":
                return self.parse_import_expression()
            if v == "this":
                self.advance()
                return self._node("ThisExpression", tok.start, tok.end)
            if v == "super":
                self.advance()
                return self._node("Super", tok.start, tok.end)
            if v == "function":
                return self._parse_function_like(tok.start, "FunctionExpression")
            if v == "class":
                return self._parse_class_like(tok.start, "ClassExpression")
            if v == "async":
                return self._parse_async_primary()
            if v == "new":
                return self.parse_new()
            self.advance()
            return self._node("Identifier", tok.start, tok.end, name=v)
        if t == "punct":
            v = tok.value
            if v == "(":
                return self._parse_paren_or_group()
            if v == "[":
                return self.parse_array()
            if v == "{":
                return self.parse_object()
            if v == "<":
                if self._looks_like_jsx():
                    return self._skip_jsx_element()
        raise _ParseError("expected expression")

    def _parse_async_primary(self):
        if self._looks_like_arrow():
            return self.parse_arrow_function()
        start = self.current.start
        self.advance()  # async
        if self._at("name", "function"):
            return self._parse_function_like(start, "FunctionExpression")
        return self._node("Identifier", start, self._last_end(), name="async")

    def _parse_paren_or_group(self):
        start = self.current.start
        self.advance()  # (
        if self._at("punct", ")"):
            self.advance()
            return self._node("ParenthesizedExpression", start, self._last_end(), children=[])
        try:
            expr = self.parse_assignment()
        except _ParseError:
            self._skip_to_matching(")")
            return self._node("ParenthesizedExpression", start, self._last_end(), children=[])
        if not self._at("punct", ")"):
            self._skip_to_matching(")")
        else:
            self.advance()
        return self._node("ParenthesizedExpression", start, self._last_end(), children=[expr])

    def parse_array(self):
        start = self.current.start
        self.advance()  # [
        node = self._node("ArrayExpression", start, self._last_end(), children=[])
        while True:
            if self._at("eof"):
                break
            if self._at("punct", "]"):
                self.advance()
                break
            if self._at("punct", ","):
                self.advance()
                continue
            if self._at("punct", "..."):
                self.advance()
            try:
                expr = self.parse_assignment()
                node.children.append(expr)
            except _ParseError:
                self._skip_to_comma_or_close()
                continue
            if self._at("punct", "]"):
                self.advance()
                break
            if self._at("punct", ","):
                self.advance()
        node.end = self._last_end()
        return node

    def parse_object(self):
        start = self.current.start
        self.advance()  # {
        node = self._node("ObjectExpression", start, self._last_end(), children=[])
        while True:
            if self._at("eof"):
                break
            if self._at("punct", "}"):
                self.advance()
                break
            if self._at("punct", ","):
                self.advance()
                continue
            if self._at("name", "async") and (
                self.peek(1).type == "name"
                or (
                    self.peek(1).type == "punct"
                    and self.peek(1).value in ("[", "*")
                )
            ):
                self.advance()
            if self._at("name", "get") or self._at("name", "set"):
                nxt = self.peek(1)
                if nxt.type == "name" or (
                    nxt.type == "punct" and nxt.value in ("[", "{")
                ):
                    self.advance()
            if self._at("punct", "*"):
                self.advance()
            if self._at("punct", "..."):
                self.advance()
                try:
                    self.parse_assignment()
                except _ParseError:
                    pass
                continue
            if not self._consume_property_key():
                self.advance()
                continue
            tok = self.current
            if tok.type == "punct":
                if tok.value == ":":
                    self.advance()
                    try:
                        value = self.parse_assignment()
                        node.children.append(value)
                    except _ParseError:
                        self._skip_to_member_boundary()
                elif tok.value == "(":
                    self._skip_method_body()
                elif tok.value == "=":
                    self.advance()
                    try:
                        value = self.parse_assignment()
                        node.children.append(value)
                    except _ParseError:
                        pass
            if self._at("punct", ","):
                self.advance()
        node.end = self._last_end()
        return node

    def _consume_property_key(self):
        tok = self.current
        if tok.type in ("name", "string", "number"):
            self.advance()
            return True
        if tok.type == "punct" and tok.value == "[":
            self._skip_to_matching("]")
            return True
        if tok.type == "punct" and tok.value == "#":
            self.advance()
            if self._at("name"):
                self.advance()
            return True
        return False

    def _skip_method_body(self):
        if self._at("punct", "("):
            self._skip_to_matching(")")
        if self._at("punct", ":"):
            self._skip_type_annotation()
        if self._at("punct", "{"):
            self._skip_balanced_brace()

    def _skip_to_member_boundary(self):
        while True:
            tok = self.current
            if tok.type == "eof":
                return
            if tok.type == "punct" and tok.value in (",", "}", ";"):
                return
            self.advance()

    # ---- templates and JSX ------------------------------------------------

    def _parse_template(self):
        tok = self.current
        self.advance()
        node = self._node("TemplateLiteral", tok.start, tok.end, children=[])
        for kind, data in tok.parts:
            if kind == "expr":
                inner = self._parse_inner_expression(data)
                if inner is not None:
                    node.children.append(inner)
        return node

    def _parse_inner_expression(self, tokens):
        if not tokens:
            return None
        parser = Parser(self.source, tokens)
        try:
            return parser.parse_assignment()
        except _ParseError:
            return None

    def _looks_like_jsx(self):
        nxt = self.peek(1)
        if nxt.type == "name":
            return True
        if nxt.type == "punct" and nxt.value == ">":
            return True
        return False

    def _skip_jsx_element(self):
        start = self.current.start
        self.advance()  # <
        if self._at("punct", "/"):
            self.advance()
            if self._at("name"):
                self.advance()
            if self._at("punct", ">"):
                self.advance()
            return self._node("JSXElement", start, self._last_end(), children=[])
        open_name = None
        if self._at("punct", ">"):
            self.advance()
            self._skip_jsx_children(None)
            return self._node("JSXElement", start, self._last_end(), children=[])
        if self._at("name"):
            open_name = self.current.value
            self.advance()
        while True:
            tok = self.current
            if tok.type == "eof":
                break
            if tok.type == "punct":
                if tok.value == ">":
                    self.advance()
                    break
                if tok.value == "{":
                    self._skip_balanced_brace()
                    continue
                if (
                    tok.value == "/"
                    and self.peek(1).type == "punct"
                    and self.peek(1).value == ">"
                ):
                    self.advance()
                    self.advance()
                    return self._node("JSXElement", start, self._last_end(), children=[])
            prev = self.pos
            self.advance()
            if self.pos <= prev:
                break
        self._skip_jsx_children(open_name)
        return self._node("JSXElement", start, self._last_end(), children=[])

    def _skip_jsx_children(self, open_name):
        while True:
            tok = self.current
            if tok.type == "eof":
                return
            if tok.type == "punct" and tok.value == "<":
                nxt = self.peek(1)
                if nxt.type == "punct" and nxt.value == "/":
                    self.advance()
                    self.advance()
                    if self._at("name"):
                        self.advance()
                    if self._at("punct", ">"):
                        self.advance()
                    return
                self._skip_jsx_element()
                continue
            prev = self.pos
            self.advance()
            if self.pos <= prev:
                return
