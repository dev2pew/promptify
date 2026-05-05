# PROMPT

complete the task while adhering to the AGENTS and README.

## TASK

address the issues in the TODO.

## NOTE

- choose one of the following fix paths or come up with a better one...

## FIRST

implement a different behavior AKA separate logic for different types of terminals by separating them using this category - kind of a simple, hacky-like, patch approach...

a) terminals with no interception capabilities;
b) terminals with interception capabilities;
c) do not use internal clipboard at all, save all the data to system clipboard to avoid hassle. (PREFERRED)

## SECOND

implement a terminal profile system which can identify the terminal the app is running on and based on that, create unique profiles with different hotkey and key signal definitions to help manage the hassle of wilderness of terminals - kind of a dynamic and more general solution approach...

- profiles will be stoed under `data/terms.dat`;
- each profile will contain...

1) `terms` array; (collected terminals)
2) `type` in `terms` array; (terminal type)
3) `signals` in . (hotkey with the key signal)

- below is an example of a JSOJN document that will be stored under `data/terms.dat`...

(modify the JSON if you can offer better structure)

```json
[
    {
        "terms": [
            {
                "type": "conhost",
                "signals": {
                    "<hotkey_definition_1>": "<captured_signal>",
                    "<hotkey_definition_2>": "<captured_signal>",
                    "<hotkey_definition_3>": "<captured_signal>"
                }
            },
            {
                "type": "msterminal",
                "signals": {
                    "<hotkey_definition_1>": "<captured_signal>",
                    "<hotkey_definition_2>": "<captured_signal>",
                    "<hotkey_definition_3>": "<captured_signal>"
                }
            },
            {
                "type": "<etc>",
                "signals": {
                    "<hotkey_definition_1>": "<captured_signal>",
                    "<hotkey_definition_2>": "<captured_signal>",
                    "<hotkey_definition_3>": "<captured_signal>"
                }
            }
        ]
    }
]

```

(note that terminal `type` are provided just an placeholder examples, you may use raw terminal type string got from the probes. for the hotkey definitions, you may use the definition names same as in the source code of the `promptify` project, i.e., `src/`. as for the captured signals, you may use any optimal format to ensure accuracy)

- below is the main menu logic if second approach is chosen...

1. create `data/terms.dat` if not exists;
2. during main menu initialization, check for terminal type, if it is not present in the `terms.dat`, then start probing process; (user-facing term will be "self-configuration" process)
3. using a method to gather all the hotkeys from the application which are defined, display one of them and ask use to press the shown hotkey combination to proceed;

(the process will look something like this. use the `src/promptify/ui/dialogs.py` to declare the modal. as for the modal - use something like `message_dialog` to both dynamically display text and capture the key signals. below is the modal window layout)

```md
<hfiller><title><hfiller><count>" out of "<total>
<viller>
"press the shown key combination: <combination>\n\n[Enter] to proceed, [Esc] to clear captured - press again to go back"
<vspace>
"captured keycode"<hfiller><keycode>
<viller>

```

1) <count> is the current progress, <total> is the total amount of "questions" that will be asked to press the keys;
2) pressing `[Esc]` will clear the captured keycode, pressing `[Esc]` while the captured keycode is empty will make user go back to the previous question.

(ensure robustness of implementation and ensure to use shared libs. ensure common sense like user cannot cause duplicates in the keycodes and cannot enter potentially conflicting keys)

## THIRD

the third method is the most straightforward, the script processes the selected part of text, reads in from the memory and writes the contents to the clipboard ensuring compatibility across all platforms.
