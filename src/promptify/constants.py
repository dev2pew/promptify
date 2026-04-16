"""
CONSTANTS AND STATIC MAPPINGS FOR THE PROMPTIFY APPLICATION.
"""

# MAPS FILE EXTENSIONS TO THEIR RESPECTIVE SINGLE-LINE COMMENT SYNTAX
COMMENT_SYNTAX: dict[str, tuple[str, str]] = {
    "python": ("# ", ""),
    "py": ("# ", ""),
    "bash": ("# ", ""),
    "sh": ("# ", ""),
    "yaml": ("# ", ""),
    "yml": ("# ", ""),
    "ruby": ("# ", ""),
    "rb": ("# ", ""),
    "javascript": ("// ", ""),
    "js": ("// ", ""),
    "typescript": ("// ", ""),
    "ts": ("// ", ""),
    "java": ("// ", ""),
    "c": ("// ", ""),
    "cpp": ("// ", ""),
    "csharp": ("// ", ""),
    "cs": ("// ", ""),
    "go": ("// ", ""),
    "rust": ("// ", ""),
    "rs": ("// ", ""),
    "swift": ("// ", ""),
    "php": ("// ", ""),
    "html": ("<!-- ", " -->"),
    "xml": ("<!-- ", " -->"),
    "markdown": ("<!-- ", " -->"),
    "md": ("<!-- ", " -->"),
    "css": ("/* ", " */"),
    "scss": ("/* ", " */"),
    "sql": ("-- ", ""),
    "lua": ("-- ", ""),
}
