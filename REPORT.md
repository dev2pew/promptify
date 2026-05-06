# REPORT

## STATE

1. overall the project quality is now much higher and smoother.

## ISSUES

1. the alternative `Ctrl+Shift+Up/Down` also get intercepted by the MS Terminal, let's replace `Ctrl+Shift+Up/Down` with ``...

```log

```

(after done changing hotkeys, no need to reflect the documentation or the help docs, I will update them myself, just give me checklist for me to complete)

2. in the main menu, improve the experience by making the app ask for input again if user provides invalid case/path/mode continiously while keepiong the robust interrupt detection logic in place;

3. when typing triple backticks for code blocks, the auto close feature interferes and makes the experience worse, exclude backtick and quotes and double quotes from creating auto-closing parts and placing the cursor inside of it - while leaving all other symbols alone AKA unchanged - this means do not change the select special symbol action for all symbols, modify only no selection logic for 3 specials which are backtick, quote, double quote;

4. ensure the `parse.py` reverse script in the `tools/` is robust and properly extracts the project context and rebuilds it... (make changes only to the `parse.py` - do not apply changes to the project to satisfy `parse.py` reequirements)

- the script must rebuild only using outputs from `<@file:` and `<@dir:`, this means the script must be able to tell between mention outputs and custom user written codeblocks;
- if the parser encounter duplicate mention output; (i.e, the same file is mentioned twice in the prompt, then keep only one copy in the memory and use it - just display a warning that there are duplicate found at `:<line>:<pas>` with `:<line>:<pos>`)
- keep the behavior of creating project structure next to the prompt file;
- verify the existing logic of the script and ensure robustness;
- keep the CLI only logic so that the script only accepts files through arguments and will not ask for one if launched with no arguments at all.
