# TODO

1. fix the `^[C/V]` and `^[Shift] + [C/V]` issue regarding different terminals.

> older `conhost` terminals correctly receive these hotkeys,
>
> but the more modern ones like `msterminal` or `vscode` intercept these two hotkeys and pass the copied text directly,
>
> you can inspect the hotkey probes in the PROBE.

2. the `dir` mention AKA call does not show the paths like the `file` mention does, below is a demo with actual and expected results...

- the actual project structure looks like this...

```log
TREE /F
Folder PATH listing for volume win
Volume serial number is C6D9-6E83
C:.
└───this
    └───project
        └───does
            └───not
                └───contain
                    └───files

```

- the editor shows this in the suggestions when typing `<@dir`...

```md
<@dir<cursor>
    <suggestions>
        this
        project
        does
        not
        contain
        files
    </suggestions>

```

- the expected suggestions appearance...

```md
<suggestions>
    <left>
        this
        project
        does
        not
        contain
        files
    </left>
    <right>
        <blank>
        ...this
        ...oes/not
        ...contain
        ...ct/does
    </right>
</suggestions>

```

(in other words, copy the right side directory indicator from the `file` mention and incorporate it into `dir` mention)

3. implement a new hotkey `^[X]` to cut the current line like in vscode. below is a demo...

- position of a cursor does not matter when cutting, this is shown in a demo.

- before cut...

```md
# DEMO
<blank>
cut me<cursor>
line 2
line 3
```

- used `^[X]`...

```md
# DEMO
<blank>
<cursor>
line 2
line 3
```

- used `^[V]`... (1)

```md
# DEMO
<blank>
cut me
<cursor>line 2
line 3
```

- used `^[V]`... (2)

```md
# DEMO
<blank>
cut me
cut me
<cursor>line 2
line 3
```

- used `^[V]`... (3)

```md
# DEMO
<blank>
cut me
cut me
cut me
<cursor>line 2
line 3
```

4. there is a `#` override for markdown pygments, make that so all of the headings (`#`, `##`, `###` and others) get colored to the user specified color as well, just change the key name in the `.env.example` and modify the source code and update the docs to mention and modify the general headers colors (or just append to heading 2, 3, 4, 5, 6, not only 1 - simple approach)

5. `^[Alt] + {Enter does not work in replace mode, the text cursor just ges moved down. (fix this issue by analyzing PROBE as well - ensure all hotkeys are working and compatible theoretically)}
