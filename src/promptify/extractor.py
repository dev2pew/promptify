class SymbolExtractor:
    """
    A robust, language-agnostic symbol extractor that leverages Pygments tokenization
    to find and extract functions, classes, and structs from source code.
    """

    def __init__(self, code: str, filename: str):
        self.code = code
        self.filename = filename
        self.lines = code.splitlines(keepends=True)

    def extract(self, symbol_name: str) -> str | None:
        try:
            from pygments.lexers import get_lexer_for_filename
            from pygments.token import Token

            lexer = get_lexer_for_filename(self.filename)
        except Exception:
            return None

        tokens = list(lexer.get_tokens(self.code))

        decl_indices = []
        for i, (ttype, tval) in enumerate(tokens):
            if (
                ttype in (Token.Name.Function, Token.Name.Class, Token.Name.Namespace)
                and tval == symbol_name
            ):
                decl_indices.append(i)
            elif ttype in Token.Name and tval == symbol_name:
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
                        decl_indices.append(i)
                        break

        # Remove duplicates
        decl_indices = list(dict.fromkeys(decl_indices))

        if not decl_indices:
            return None
        if len(decl_indices) > 1:
            raise ValueError(f"duplicate symbol '{symbol_name}' found")

        decl_idx = decl_indices[0]

        char_pos = sum(len(tval) for _, tval in tokens[:decl_idx])
        start_line = self.code.count("\n", 0, char_pos)

        is_python = self.filename.endswith((".py", ".pyx", ".gd", ".yaml", ".yml"))

        if is_python:
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
            return "".join(self.lines[start_line : end_line + 1])

        brace_count = 0
        found_first_brace = False
        end_char_pos = sum(len(tval) for _, tval in tokens[:decl_idx])

        for i in range(decl_idx, len(tokens)):
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
            end_line = self.code.count("\n", 0, end_char_pos)
            return "".join(self.lines[start_line : end_line + 1])

        return self.lines[start_line]
