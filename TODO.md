# PROMPT

I will attach the project ZIP that contains... (`promptify_5mfop.zip`)

```md
scripts/
src/
strings/
tests/
.env.example
.gitignore
AGENTS.md
pyproject.toml
README.md
TODO.md
uv.lock

```

## TASK

1. analyze the rules and project contribution guide from `AGENTS.md` and project overview and description from `README.md `;
2. fix the listed issues in the `ISSUES` part of this document;
3. ensure the fixea and changes align with the rules and overall project guidelines.

## EXTRA

ensure to do these things before creating a `.zip` package to ensure best outcome...

1. initialize a `git repo` after unpacking the project I've sent you;
2. commit all the files as the initial commit;
3. after being done (fixing issues, resolving regression tests and formatting the codebase) commit the changes using `git`;
4. generate `.diff` patches for me to apply using `git`;
5. package to `.zip` the `.diff` patches instead of full project to ensure it fits within the limits.

## NOTES

## PRERUN

1. all regression tests pass;
2. `1` error from the `llc.(bat|sh)` type checking tool. (basedpyright)

## RUN

1. multi-cursor controls for typing now work as expected;
2. detached view scrolling using `^[^/v]` (Up/Down) works as expected;
3. progress auto-save now functions without disruption errors;
4. `pygments` synrax colors are now more comfortable to work with;
5. the smart cursor behavior works but is clunky.

(there are cases where the pos is restored, but the cursor skips 1 or more rows when navigating)

## ISSUES

1. triggering the following hotkeys exits (steals the user view/attention) from modals... (like "Help", "Search", "Replace", "Quit confirmation")

(the intended action is that all hotkeys/controls other than intended oves and basic navigation like `[^/v/</>]` (Up/Down/Left/Right) and `[Home/End]` and `^` modifier are prohibited)
(to this this more clearly, only `^[^/v/</>]` (Up/Down/Left/Right), `[^/v/</>]` (Up/Down/Left/Right), `^[Home/End]`, `[Home/End]` are allowed)

```md
^[Shift] + [Alt] + [^/v] (Up/Down)
^[Alt] + [^/v] (Up/Down)

```

(also make sure to check other possible potential offenders and problems in hotkeys and logic)

2. while being in multi-cursor mode, utilizing the following hotkeys breaks the feature...

```md
[Shift] + [Backspace]
^[W]

```

(also make sure to check other possible potential offenders and problems in hotkeys and logic)

- when trying to utilize `[Shift] + [Home]` -> `[Backspace]` in multi-cursor mode after hitting `^[Alt] + [^/v]` (2) times - state: 1 real, 2 cloned...

detailed steps...

1) create 2 clones of cursor;
2) type `multi-cursor text before \`[Shift] + [Home] and [Backspace]\`;
3) hit `[Shift] + [Home]`;
4) hit `[Backspace]`;
5) the cursors are not scattered like this...

- before...

```md
# DEMO MARKDOWN
<blank_line>
multi-cursor text before `^[Shift] + [Home] and [Backspace]`<cursor>
multi-cursor text before `^[Shift] + [Home] and [Backspace]`<clone>
multi-cursor text before `^[Shift] + [Home] and [Backspace]`<clone>
<blank_line>
## DEMO SUB
<blank_line>
sample text data int 01234.
<blank_line>
## DEMO SUB SUB
<blank_line>
sample float data 0.01234.
<blank_line>

```

- used `[Shift] + [Home]`...

```md
# DEMO MARKDOWN
<blank_line>
<cursor><select>multi-cursor text before `^[Shift] + [Home] and [Backspace]`</select>
multi-cursor text before `^[Shift] + [Home] and [Backspace]`<clone>
multi-cursor text before `^[Shift] + [Home] and [Backspace]`<clone>
<blank_line>
## DEMO SUB
<blank_line>
sample text data int 01234.
<blank_line>
## DEMO SUB SUB
<blank_line>
sample float data 0.01234.
<blank_line>

```

- used `[Backspace]`...

```md
# DEMO MARKDOWN
<blank_line>
<cursor>
multi-cursor text before `^[Shift] + [Home] and [Backspace]`
multi-cursor text before `^[Shift] + [Home] and [Backspace]`<clone>
<blank_line>
## DEMO SUB
<blank_line>
sample text data int 01234.
<blank_line>
## DEMO SUB SUB
<clone>
sample float data 0.01234.
<blank_line>

```

- when trying to utilize `^[W]` while in multi-cursor mode...

1) write a text using multi-cursor mode;
2) place cursor after any word, in this case `W`;
3) hit `^[W]`;
4) you get this..

- before...

```md
# DEMO MARKDOWN
<blank_line>
<blank_line>
multi-cursor text before `^[W]`<cursor>
multi-cursor text before `^[W]`<clone>
multi-cursor text before `^[W]`<clone>
<blank_line>
## DEMO SUB
<blank_line>
sample data int 01234
<blank_line>
### DEMO SUB SUB
<blank_line>
sample text data.
<blank_line>

```

- after...

```md
# DEMO MARKDOWN
<blank_line>
<blank_line>
multi-cursor text before `^[<cursor>]`
multi-cursor text before `^[W]`
multi-cursor text before<clone> `^[W]`
<blank_line>
## DE<clone>MO SUB
<blank_line>
sample data int 01234
<blank_line>
### DEMO SUB SUB
<blank_line>
sample text data.
<blank_line>

```

3. using `^[A]` and `[Backspace]` does not dispose cloned text cursors leading to unexpected results; (I have to use `[Esc]` to dismiss them which is not intuitive)

(the intended logic was if multiple cloned cursors move to the same pos, they will get merged into one meaning `^[A]` should have removed all cloned text cursors)

(also make sure to check other possible potential offenders and problems in hotkeys and logic)

4. hotkeys like `^[X]` do cut the text but the `^[V]` or `^[Shift] + [V]` pastes the system clipboard text instead of internal editor one.

(also make sure to check other possible potential offenders and problems in hotkeys and logic)
