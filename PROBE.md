# OUTPUT

in all of the outputs, the combination were used in the following order...

```md
1. `Ctrl + C`;
2. `Ctrl + X`;
3. `Ctrl + V`;
4. `Ctrl + Shift + C`;
5. `Ctrl + Shift + V`;
6. `Shift + Insert`;
7. `Ctrl + Shift + Insert`;
8. `Alt + Up`;
9. `Alt + Down`;
10. `Ctrl + Alt + Up`;
11. `Ctrl + Alt + Down`;
12. `Ctrl + Shift + Alt + Up`;
13. `Ctrl + Shift + Alt + Down`.

```

## CONHOST

- everything works fine here.

```log
uv.exe run python tools\probe.py

Key probe started.
Press shortcuts. Exit with Ctrl+Q.
Recommended checks:
  Ctrl+C, Ctrl+X, Ctrl+V
  Ctrl+Shift+C, Ctrl+Shift+V
  Shift+Insert, Ctrl+Shift+Insert
  Alt+Up/Down, Ctrl+Alt+Up/Down, Ctrl+Shift+Alt+Up/Down
------------------------------------------------------------------------

[03:59:06.923]
bytes=b'\x03'
  hex: 03
  dec: 3
  names: ETX / Ctrl+C
  utf8: '\x03'
  likely: Ctrl+C reached the app as ETX
------------------------------------------------------------------------

[03:59:08.152]
bytes=b'\x18'
  hex: 18
  dec: 24
  names: CAN / Ctrl+X
  utf8: '\x18'
------------------------------------------------------------------------

[03:59:09.509]
bytes=b'\x16'
  hex: 16
  dec: 22
  names: SYN / Ctrl+V
  utf8: '\x16'
  likely: Ctrl+V reached the app as a keypress
------------------------------------------------------------------------

[03:59:12.105]
bytes=b'\x03'
  hex: 03
  dec: 3
  names: ETX / Ctrl+C
  utf8: '\x03'
  likely: Ctrl+C reached the app as ETX
------------------------------------------------------------------------

[03:59:13.549]
bytes=b'a'
  hex: 61
  dec: 97
  names: printable 'a'
  utf8: 'a'
------------------------------------------------------------------------

[03:59:18.608]
bytes=b'\xc3\xa0R'
  hex: C3 A0 52
  dec: 195 160 82
  names: non-printable, non-printable, printable 'R'
  utf8: 'àR'
------------------------------------------------------------------------

[03:59:25.599]
bytes=b'\xc3\xa0\xc2\x92'
  hex: C3 A0 C2 92
  dec: 195 160 194 146
  names: non-printable, non-printable, non-printable, non-printable
  utf8: 'à\x92'
------------------------------------------------------------------------

[03:59:30.670]
bytes=b'\x00\xc2\x98'
  hex: 00 C2 98
  dec: 0 194 152
  names: NUL / Ctrl+Space / Ctrl+@, non-printable, non-printable
  utf8: '\x00\x98'
------------------------------------------------------------------------

[03:59:31.648]
bytes=b'\x00\xc2\xa0'
  hex: 00 C2 A0
  dec: 0 194 160
  names: NUL / Ctrl+Space / Ctrl+@, non-printable, non-printable
  utf8: '\x00\xa0'
------------------------------------------------------------------------

[03:59:36.487]
bytes=b'\x00\xc2\x98'
  hex: 00 C2 98
  dec: 0 194 152
  names: NUL / Ctrl+Space / Ctrl+@, non-printable, non-printable
  utf8: '\x00\x98'
------------------------------------------------------------------------

[03:59:38.032]
bytes=b'\x00\xc2\xa0'
  hex: 00 C2 A0
  dec: 0 194 160
  names: NUL / Ctrl+Space / Ctrl+@, non-printable, non-printable
  utf8: '\x00\xa0'
------------------------------------------------------------------------

[03:59:57.594]
bytes=b'\x00\xc2\x98'
  hex: 00 C2 98
  dec: 0 194 152
  names: NUL / Ctrl+Space / Ctrl+@, non-printable, non-printable
  utf8: '\x00\x98'
------------------------------------------------------------------------

[03:59:58.039]
bytes=b'\x00\xc2\xa0'
  hex: 00 C2 A0
  dec: 0 194 160
  names: NUL / Ctrl+Space / Ctrl+@, non-printable, non-printable
  utf8: '\x00\xa0'
------------------------------------------------------------------------

```

## TERMINAL

- paste commands instead of sending Ctrl + V signal, just typed the `foobar` directly.

```log
uv.exe run python tools\probe.py

Key probe started.
Press shortcuts. Exit with Ctrl+Q.
Recommended checks:
  Ctrl+C, Ctrl+X, Ctrl+V
  Ctrl+Shift+C, Ctrl+Shift+V
  Shift+Insert, Ctrl+Shift+Insert
  Alt+Up/Down, Ctrl+Alt+Up/Down, Ctrl+Shift+Alt+Up/Down
------------------------------------------------------------------------

[04:05:18.762]
bytes=b'\x03'
  hex: 03
  dec: 3
  names: ETX / Ctrl+C
  utf8: '\x03'
  likely: Ctrl+C reached the app as ETX
------------------------------------------------------------------------

[04:05:19.058]
bytes=b'\x18'
  hex: 18
  dec: 24
  names: CAN / Ctrl+X
  utf8: '\x18'
------------------------------------------------------------------------

[04:05:19.563]
bytes=b'f'
  hex: 66
  dec: 102
  names: printable 'f'
  utf8: 'f'
------------------------------------------------------------------------

[04:05:19.564]
bytes=b'o'
  hex: 6F
  dec: 111
  names: printable 'o'
  utf8: 'o'
------------------------------------------------------------------------

[04:05:19.564]
bytes=b'o'
  hex: 6F
  dec: 111
  names: printable 'o'
  utf8: 'o'
------------------------------------------------------------------------

[04:05:19.564]
bytes=b'b'
  hex: 62
  dec: 98
  names: printable 'b'
  utf8: 'b'
------------------------------------------------------------------------

[04:05:19.565]
bytes=b'a'
  hex: 61
  dec: 97
  names: printable 'a'
  utf8: 'a'
------------------------------------------------------------------------

[04:05:19.565]
bytes=b'r'
  hex: 72
  dec: 114
  names: printable 'r'
  utf8: 'r'
------------------------------------------------------------------------

[04:05:22.887]
bytes=b'\x03'
  hex: 03
  dec: 3
  names: ETX / Ctrl+C
  utf8: '\x03'
  likely: Ctrl+C reached the app as ETX
------------------------------------------------------------------------

[04:05:23.895]
bytes=b'f'
  hex: 66
  dec: 102
  names: printable 'f'
  utf8: 'f'
------------------------------------------------------------------------

[04:05:23.895]
bytes=b'o'
  hex: 6F
  dec: 111
  names: printable 'o'
  utf8: 'o'
------------------------------------------------------------------------

[04:05:23.896]
bytes=b'o'
  hex: 6F
  dec: 111
  names: printable 'o'
  utf8: 'o'
------------------------------------------------------------------------

[04:05:23.896]
bytes=b'b'
  hex: 62
  dec: 98
  names: printable 'b'
  utf8: 'b'
------------------------------------------------------------------------

[04:05:23.896]
bytes=b'a'
  hex: 61
  dec: 97
  names: printable 'a'
  utf8: 'a'
------------------------------------------------------------------------

[04:05:23.897]
bytes=b'r'
  hex: 72
  dec: 114
  names: printable 'r'
  utf8: 'r'
------------------------------------------------------------------------

[04:05:26.981]
bytes=b'f'
  hex: 66
  dec: 102
  names: printable 'f'
  utf8: 'f'
------------------------------------------------------------------------

[04:05:26.981]
bytes=b'o'
  hex: 6F
  dec: 111
  names: printable 'o'
  utf8: 'o'
------------------------------------------------------------------------

[04:05:26.981]
bytes=b'o'
  hex: 6F
  dec: 111
  names: printable 'o'
  utf8: 'o'
------------------------------------------------------------------------

[04:05:26.982]
bytes=b'b'
  hex: 62
  dec: 98
  names: printable 'b'
  utf8: 'b'
------------------------------------------------------------------------

[04:05:26.982]
bytes=b'a'
  hex: 61
  dec: 97
  names: printable 'a'
  utf8: 'a'
------------------------------------------------------------------------

[04:05:26.982]
bytes=b'r'
  hex: 72
  dec: 114
  names: printable 'r'
  utf8: 'r'
------------------------------------------------------------------------

[04:05:33.380]
bytes=b'\xc3\xa0\xc2\x92'
  hex: C3 A0 C2 92
  dec: 195 160 194 146
  names: non-printable, non-printable, non-printable, non-printable
  utf8: 'à\x92'
------------------------------------------------------------------------

[04:05:38.293]
bytes=b'\x00\xc2\x98'
  hex: 00 C2 98
  dec: 0 194 152
  names: NUL / Ctrl+Space / Ctrl+@, non-printable, non-printable
  utf8: '\x00\x98'
------------------------------------------------------------------------

[04:05:39.621]
bytes=b'\x00\xc2\xa0'
  hex: 00 C2 A0
  dec: 0 194 160
  names: NUL / Ctrl+Space / Ctrl+@, non-printable, non-printable
  utf8: '\x00\xa0'
------------------------------------------------------------------------

[04:05:40.893]
bytes=b'\x00\xc2\x98'
  hex: 00 C2 98
  dec: 0 194 152
  names: NUL / Ctrl+Space / Ctrl+@, non-printable, non-printable
  utf8: '\x00\x98'
------------------------------------------------------------------------

[04:05:41.662]
bytes=b'\x00\xc2\xa0'
  hex: 00 C2 A0
  dec: 0 194 160
  names: NUL / Ctrl+Space / Ctrl+@, non-printable, non-printable
  utf8: '\x00\xa0'
------------------------------------------------------------------------

[04:05:43.539]
bytes=b'\x00\xc2\x98'
  hex: 00 C2 98
  dec: 0 194 152
  names: NUL / Ctrl+Space / Ctrl+@, non-printable, non-printable
  utf8: '\x00\x98'
------------------------------------------------------------------------

[04:05:44.435]
bytes=b'\x00\xc2\xa0'
  hex: 00 C2 A0
  dec: 0 194 160
  names: NUL / Ctrl+Space / Ctrl+@, non-printable, non-printable
  utf8: '\x00\xa0'
------------------------------------------------------------------------

```

## VSCODE

- paste commands instead of sending Ctrl + V signal, just typed the foobar directly;
- these hotkeys were not reacting in vscode terminal, likely they got swallowed by the IDE.

```md
- `Ctrl + Shift + C`;
- `Ctrl + Shift + Insert`;
- `Ctrl + Alt + Up`;
- `Ctrl + Alt + Down`;
- `Ctrl + Shift + Alt + Up`;
- `Ctrl + Shift + Alt + Down`.

```

```log
uv.exe run python tools\probe.py

Key probe started.
Press shortcuts. Exit with Ctrl+Q.
Recommended checks:
  Ctrl+C, Ctrl+X, Ctrl+V
  Ctrl+Shift+C, Ctrl+Shift+V
  Shift+Insert, Ctrl+Shift+Insert
  Alt+Up/Down, Ctrl+Alt+Up/Down, Ctrl+Shift+Alt+Up/Down
------------------------------------------------------------------------

[04:07:05.026]
bytes=b'\x03'
  hex: 03
  dec: 3
  names: ETX / Ctrl+C
  utf8: '\x03'
  likely: Ctrl+C reached the app as ETX
------------------------------------------------------------------------

[04:07:07.581]
bytes=b'\x18'
  hex: 18
  dec: 24
  names: CAN / Ctrl+X
  utf8: '\x18'
------------------------------------------------------------------------

[04:07:08.284]
bytes=b'f'
  hex: 66
  dec: 102
  names: printable 'f'
  utf8: 'f'
------------------------------------------------------------------------

[04:07:08.285]
bytes=b'o'
  hex: 6F
  dec: 111
  names: printable 'o'
  utf8: 'o'
------------------------------------------------------------------------

[04:07:08.286]
bytes=b'o'
  hex: 6F
  dec: 111
  names: printable 'o'
  utf8: 'o'
------------------------------------------------------------------------

[04:07:08.287]
bytes=b'b'
  hex: 62
  dec: 98
  names: printable 'b'
  utf8: 'b'
------------------------------------------------------------------------

[04:07:08.287]
bytes=b'a'
  hex: 61
  dec: 97
  names: printable 'a'
  utf8: 'a'
------------------------------------------------------------------------

[04:07:08.288]
bytes=b'r'
  hex: 72
  dec: 114
  names: printable 'r'
  utf8: 'r'
------------------------------------------------------------------------

[04:07:14.655]
bytes=b'f'
  hex: 66
  dec: 102
  names: printable 'f'
  utf8: 'f'
------------------------------------------------------------------------

[04:07:14.655]
bytes=b'o'
  hex: 6F
  dec: 111
  names: printable 'o'
  utf8: 'o'
------------------------------------------------------------------------

[04:07:14.656]
bytes=b'o'
  hex: 6F
  dec: 111
  names: printable 'o'
  utf8: 'o'
------------------------------------------------------------------------

[04:07:14.657]
bytes=b'b'
  hex: 62
  dec: 98
  names: printable 'b'
  utf8: 'b'
------------------------------------------------------------------------

[04:07:14.658]
bytes=b'a'
  hex: 61
  dec: 97
  names: printable 'a'
  utf8: 'a'
------------------------------------------------------------------------

[04:07:14.659]
bytes=b'r'
  hex: 72
  dec: 114
  names: printable 'r'
  utf8: 'r'
------------------------------------------------------------------------

[04:07:17.744]
bytes=b'f'
  hex: 66
  dec: 102
  names: printable 'f'
  utf8: 'f'
------------------------------------------------------------------------

[04:07:17.745]
bytes=b'o'
  hex: 6F
  dec: 111
  names: printable 'o'
  utf8: 'o'
------------------------------------------------------------------------

[04:07:17.745]
bytes=b'o'
  hex: 6F
  dec: 111
  names: printable 'o'
  utf8: 'o'
------------------------------------------------------------------------

[04:07:17.746]
bytes=b'b'
  hex: 62
  dec: 98
  names: printable 'b'
  utf8: 'b'
------------------------------------------------------------------------

[04:07:17.747]
bytes=b'a'
  hex: 61
  dec: 97
  names: printable 'a'
  utf8: 'a'
------------------------------------------------------------------------

[04:07:17.747]
bytes=b'r'
  hex: 72
  dec: 114
  names: printable 'r'
  utf8: 'r'
------------------------------------------------------------------------

[04:07:28.947]
bytes=b'\x00\xc2\x8d'
  hex: 00 C2 8D
  dec: 0 194 141
  names: NUL / Ctrl+Space / Ctrl+@, non-printable, non-printable
  utf8: '\x00\x8d'
------------------------------------------------------------------------

[04:07:30.428]
bytes=b'\x00\xc2\x91'
  hex: 00 C2 91
  dec: 0 194 145
  names: NUL / Ctrl+Space / Ctrl+@, non-printable, non-printable
  utf8: '\x00\x91'
------------------------------------------------------------------------

```
