import shutil
import math
import re
from prompt_toolkit import print_formatted_text, HTML


def format_index(i: int) -> str:
    s = str(i)
    if len(s) == 1:
        return f"<ansicyan>[-{s}]</ansicyan>"
    return f"<ansicyan>[{s}]</ansicyan>"


def print_columnized(items: list[str]) -> None:
    term_width, _ = shutil.get_terminal_size((80, 20))

    formatted_items = [f"{format_index(i + 1)} {item}" for i, item in enumerate(items)]

    strip_tags = re.compile(r"<[^>]+>")
    max_width = (
        max(len(strip_tags.sub("", item)) for item in formatted_items)
        if formatted_items
        else 0
    )

    col_width = max_width + 4
    num_cols = max(1, term_width // col_width)
    num_rows = math.ceil(len(formatted_items) / num_cols)

    for row in range(num_rows):
        row_str = ""
        for col in range(num_cols):
            idx = col * num_rows + row
            if idx < len(formatted_items):
                item = formatted_items[idx]
                visible_len = len(strip_tags.sub("", item))
                padding = " " * (col_width - visible_len)
                row_str += item + padding
        print_formatted_text(HTML(row_str))


def print_modes(modes: list[tuple[str, str]]) -> None:
    formatted_prefixes = [
        f"{format_index(i + 1)} {name}" for i, (name, _) in enumerate(modes)
    ]
    strip_tags = re.compile(r"<[^>]+>")
    max_prefix_len = (
        max(len(strip_tags.sub("", p)) for p in formatted_prefixes)
        if formatted_prefixes
        else 0
    )

    for i, (name, desc) in enumerate(modes):
        prefix = formatted_prefixes[i]
        visible_len = len(strip_tags.sub("", prefix))
        padding = " " * (max_prefix_len - visible_len + 4)
        print_formatted_text(HTML(f"{prefix}{padding}{desc}"))
