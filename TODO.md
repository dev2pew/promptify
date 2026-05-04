# TODO

1. fix the `^[C/V]` and `^[Shift] + [C/V]` issue regarding different terminals.

> older `conhost` terminals correctly receive these hotkeys,
>
> but the more modern ones like `msterminal` or `vscode` intercept these two hotkeys and pass the copied text directly,
>
> you can inspect the hotkey probes in the PROBE.
