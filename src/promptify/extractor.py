class SymbolExtractor:
    """
    A robust, language-agnostic symbol extractor that leverages Pygments tokenization
    to find and extract functions, classes, and structs from source code.
    It builds a lightweight symbol tree to support scoped names like 'Class.method'.
    """

    def __init__(self, code: str, filename: str):
        self.code = code
        self.filename = filename
        self.lines = code.splitlines(keepends=True)
        self.symbols: dict[str, str] = {}
        self._parse()

    def _parse(self) -> None:
        try:
            from pygments.lexers import get_lexer_for_filename
            from pygments.token import Token

            lexer = get_lexer_for_filename(self.filename)
        except Exception:
            return

        tokens = list(lexer.get_tokens(self.code))

        declarations = []
        char_pos = 0

        # 1. Identify all declarations
        for i, (ttype, tval) in enumerate(tokens):
            if ttype in (Token.Name.Function, Token.Name.Class, Token.Name.Namespace):
                line_idx = self.code.count("\n", 0, char_pos)
                declarations.append(
                    {
                        "name": tval,
                        "start_line": line_idx,
                        "token_idx": i,
                        "char_pos": char_pos,
                    }
                )
            elif ttype in Token.Name:
                # Lookback for declaration keywords
                for j in range(i - 1, max(-1, i - 5), -1):
                    if tokens[j][0] in Token.Keyword and tokens[j][1] in (
                        "def",
                        "class",
                        "function",
                        "func",
                        "struct",
                        "interface",
                    ):
                        line_idx = self.code.count("\n", 0, char_pos)
                        declarations.append(
                            {
                                "name": tval,
                                "start_line": line_idx,
                                "token_idx": i,
                                "char_pos": char_pos,
                            }
                        )
                        break
            char_pos += len(tval)

        # Remove duplicates on the same line
        unique_decls = {}
        for d in declarations:
            key = (d["start_line"], d["name"])
            if key not in unique_decls:
                unique_decls[key] = d
        declarations = list(unique_decls.values())

        is_python = self.filename.endswith((".py", ".pyx", ".gd", ".yaml", ".yml"))

        # 2. Find the end line for each declaration
        for d in declarations:
            start_line = d["start_line"]
            if is_python:
                if start_line >= len(self.lines):
                    d["end_line"] = start_line
                    continue
                decl_indent = len(self.lines[start_line]) - len(
                    self.lines[start_line].lstrip()
                )
                end_line = start_line
                for i in range(start_line + 1, len(self.lines)):
                    line = self.lines[i]
                    stripped = line.strip()
                    if not stripped or stripped.startswith("#"):
                        end_line = i
                        continue
                    indent = len(line) - len(line.lstrip())
                    if indent <= decl_indent:
                        break
                    end_line = i
                d["end_line"] = end_line
            else:
                brace_count = 0
                found_first_brace = False
                end_char_pos = d["char_pos"]
                for i in range(d["token_idx"], len(tokens)):
                    ttype, tval = tokens[i]
                    end_char_pos += len(tval)
                    if tval == "{":
                        brace_count += 1
                        found_first_brace = True
                    elif tval == "}":
                        brace_count -= 1
                        if found_first_brace and brace_count == 0:
                            break
                if found_first_brace and brace_count == 0:
                    d["end_line"] = self.code.count("\n", 0, end_char_pos)
                else:
                    d["end_line"] = start_line

        # 3. Build parent map to resolve scoped names (Class.method)
        parent_map = {}
        for d in declarations:
            parents = [
                p
                for p in declarations
                if p != d
                and p["start_line"] <= d["start_line"]
                and p["end_line"] >= d["end_line"]
            ]
            if parents:
                direct_parent = min(
                    parents, key=lambda p: p["end_line"] - p["start_line"]
                )
                parent_map[id(d)] = direct_parent

        def get_full_name(d):
            if id(d) in parent_map:
                return get_full_name(parent_map[id(d)]) + "." + d["name"]
            return d["name"]

        # 4. Populate the symbols dictionary (handles overloads by appending)
        for d in declarations:
            full_name = get_full_name(d)
            end_idx = min(d["end_line"] + 1, len(self.lines))
            snippet = "".join(self.lines[d["start_line"] : end_idx])

            if full_name in self.symbols:
                self.symbols[full_name] += "\n" + snippet
            else:
                self.symbols[full_name] = snippet

    def extract(self, symbol_name: str) -> str | None:
        return self.symbols.get(symbol_name)
