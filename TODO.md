# PROMPT

i will attach the current state of `src/` and `/tests/`, move and overwrite your current state of project root with my version.

ensure to remember AGENTS and README.

## PROBLEMS

1. fix the smart cursor behavior...

- the cursor position preservance works correctly;
- make the [Home/End] buttons or other navigation buttons update the cursor pos;
- currently pressing Home or End when the cursor is at the row which has nothing does nothing, meaning the cursor will pop back into the pos when navigating betweens the rows.

2. the multi-cursor typing is weird, below are the human tests and the demos...

CTRL + ALT + UP (1) DOWN (1)

```md
abcde       <- clone
edecdbcab   <- cursor
a           <- clone

```

CTRL + SHIFT + ALT + UP (3)

```md
abcdef      <- clone
fedcba      <- cursor

```

CTRL + SHIFT + ALT + DOWN (3)

```md
abcdef      <- cursor
fedcba      <- clone
```

3. this happened while typing in the editor...

seems like, this happens randomly when I type or when I am typing more often, seems like if I am typing during backup save it triggers the error but I am not sure.

```log
Unhandled exception in event loop:
  File "C:\Users\lucky\Documents\vscode\python\tools\dirs\ai\promptify\src\promptify\ui\editor\runtime.py", line 332, in _flush
    await session_store.save(
    ...<5 lines>...
    )
  File "C:\Users\lucky\Documents\vscode\python\tools\dirs\ai\promptify\src\promptify\shared\state.py", line 188, in save
    await _write_text_atomic(
    ...<2 lines>...
    )
  File "C:\Users\lucky\Documents\vscode\python\tools\dirs\ai\promptify\src\promptify\shared\state.py", line 25, in _write_text_atomic
    temp_path.replace(path)
    ~~~~~~~~~~~~~~~~~^^^^^^
  File "C:\Users\lucky\AppData\Roaming\uv\python\cpython-3.13-windows-x86_64-none\Lib\pathlib\_local.py", line 780, in replace
    os.replace(self, target)
    ~~~~~~~~~~^^^^^^^^^^^^^^

Exception [WinError 5] Access is denied: 'C:\\Users\\lucky\\Documents\\vscode\\python\\tools\\dirs\\ai\\promptify\\data\\state.dat.tmp' -> 'C:\\Users\\lucky\\Documents\\vscode\\python\\tools\\dirs\\ai\\promptify\\data\\state.dat'

```

4. the brackets highlight color in the editor is weird, change the default colors for highlighting to be bright, instead of dark? (in both source and env example)

5. the pygments default markdown style for headings in too dark, override with with something more vibrant? (in both source and env example - add a new option)

6. navigating while text is selected must place the cursor at the start or end of selection - currently the cursor just moves normally; (ensure this new feature won't clash with other components)

7. navigating with word wrap on is weird, and not intuitive, for example, if the wrapped row has like 6 lines of height, the cursor just skips 5 lines when navigating up or down - make te cursor navigate through the wrapped rows as well - ensure the position is restored correctly when toggling the word wrap in this way;

8. when moving the view using `^[^/v]` (Up/Down) - do not restrict the view range to the cursor, make the cursor be able to not be visible - in other words, let the user go far and not be "chained" to the real cursor.
