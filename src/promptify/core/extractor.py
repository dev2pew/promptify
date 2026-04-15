"""
AST-like symbol extraction engine powered by Pygments.
Finds and extracts specific classes, methods, and functions from source files.
"""


class SymbolExtractor:
    """
    A robust, language-agnostic symbol extractor that leverages Pygments tokenization
    to find and extract functions, classes, and structs from source code.
    It builds a lightweight symbol tree to support scoped names like 'Class.method'.
    """

    def __init__(self, code: str, filename: str):
        """
        Initializes the extractor with code content and triggers parsing.

        Args:
            code (str): The raw string contents of the source file.
            filename (str): Defines syntax behavior via lexer guessing.
        """
        self.code = code
        self.filename = filename
        self.lines = code.splitlines(keepends=True)
        self.symbols: dict[str, str] = {}
        self._parse()

    def _parse(self) -> None:
        """
        Core logic identifying and mapping all scopes via token streams.
        Supports both Python-style (indentation) and C-style (brace block) syntax.
        """
        try:
            from pygments.lexers import get_lexer_for_filename
            from pygments.token import Token

            lexer = get_lexer_for_filename(self.filename)
        except Exception:
            return

        tokens = list(lexer.get_tokens(self.code))

        declarations = []
        char_pos = 0

        # 1. IDENTIFY ALL DECLARATIONS
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
                # LOOKBACK FOR DECLARATION KEYWORDS
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

        # REMOVE DUPLICATES ON THE SAME LINE
        unique_decls = {}
        for d in declarations:
            key = (d["start_line"], d["name"])
            if key not in unique_decls:
                unique_decls[key] = d
        declarations = list(unique_decls.values())

        is_python = self.filename.endswith((".py", ".pyx", ".gd", ".yaml", ".yml"))

        # 2. FIND THE END LINE FOR EACH DECLARATION
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

        # 3. BUILD PARENT MAP TO RESOLVE SCOPED NAMES (CLASS.METHOD)
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
                # ENSURE PARENT IS STRICTLY LARGER IN SCOPE, OR IF SAME SCOPE, APPEARED EARLIER IN THE FILE.
                valid_parents = [
                    p
                    for p in parents
                    if (
                        p["end_line"] - p["start_line"]
                        > d["end_line"] - d["start_line"]
                    )
                    or (
                        p["end_line"] - p["start_line"]
                        == d["end_line"] - d["start_line"]
                        and p["token_idx"] < d["token_idx"]
                    )
                ]
                if valid_parents:
                    direct_parent = min(
                        valid_parents,
                        key=lambda p: (
                            p["end_line"] - p["start_line"],
                            -p["token_idx"],
                        ),
                    )
                    parent_map[id(d)] = direct_parent

        def get_full_name(d):
            parts = [d["name"]]
            curr = d
            seen = {id(d)}
            while id(curr) in parent_map:
                curr = parent_map[id(curr)]
                if id(curr) in seen:
                    break
                seen.add(id(curr))
                parts.append(curr["name"])
            return ".".join(reversed(parts))

        # 4. POPULATE THE SYMBOLS DICTIONARY (HANDLES OVERLOADS BY APPENDING)
        for d in declarations:
            full_name = get_full_name(d)
            end_idx = min(d["end_line"] + 1, len(self.lines))
            snippet = "".join(self.lines[d["start_line"] : end_idx])

            if full_name in self.symbols:
                self.symbols[full_name] += "\n" + snippet
            else:
                self.symbols[full_name] = snippet

    def extract(self, symbol_name: str) -> str | None:
        """
        Retrieves the exact block for a requested symbol.

        Args:
            symbol_name (str): The desired symbol ID (e.g. `MyClass.method_a`).

        Returns:
            str | None: Code snippet if mapped, None otherwise.
        """
        return self.symbols.get(symbol_name)
