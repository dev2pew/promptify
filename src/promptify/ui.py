import shutil
import math


def format_index(i):
    s = str(i)
    if len(s) == 1:
        return f"[-{s}]"
    return f"[{s}]"


def print_columnized(items):
    term_width, _ = shutil.get_terminal_size((80, 20))

    formatted_items = [f"{format_index(i+1)} {item}" for i, item in enumerate(items)]
    max_width = max(len(item) for item in formatted_items) if formatted_items else 0

    col_width = max_width + 4
    num_cols = max(1, term_width // col_width)
    num_rows = math.ceil(len(formatted_items) / num_cols)

    for row in range(num_rows):
        row_str = ""
        for col in range(num_cols):
            idx = col * num_rows + row
            if idx < len(formatted_items):
                row_str += formatted_items[idx].ljust(col_width)
        print(row_str)


def print_modes(modes):
    formatted_prefixes = [
        f"{format_index(i+1)} {name}" for i, (name, _) in enumerate(modes)
    ]
    max_prefix_len = (
        max(len(p) for p in formatted_prefixes) if formatted_prefixes else 0
    )

    for i, (name, desc) in enumerate(modes):
        prefix = formatted_prefixes[i]
        padding = " " * (max_prefix_len - len(prefix) + 4)
        print(f"{prefix}{padding}{desc}")
