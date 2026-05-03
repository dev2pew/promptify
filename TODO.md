# PROMPT

complete the task while adhering to the AGENTS and README from the repo.

## TASK

- analyze this repo's `cdx/hotkeys` branch- <https://github.com/dev2pew/promptify.git>;
- make sure to follow rules described in AGENTS and README;
- after planning your actions, perform the fixes of the issues listed below.

## ISSUES

1. user no longer is able to erase selected text using `[Shift] + [^/v/</>]` and `[Backspace]` or `[Del]` - but `^[W]` works;
2. all hotkeys related to multi-cursor editing does not work, below is the list of hotkeys that does not work...

- `^[Alt] + [^/v]`; (cursor above or below)
- `^[Shift] + [Alt] + [^/v]`; (cursor expand or shrink)
- `[Shift] + [Enter]`; (in the search pane for previous match)
- `[^/v]`; (in the replace pane for history)

3. closing "search" or "replace" pane takes a long time, including removing closed text cursors using `[Esc]` - why does this happen!? fix! (this problem persists for a long time now - in many modal windows or utilizing certain hotkeys take some time to be processed and if I interrupt it, it cancels, ex. cut action `^[X]` in the editor, if I wait - it cuts the selected text, but if I use cut hotkey and then write text, then it cancels out which is not suitable for fast editing - therefore sucks)

## NOTE

after trying to use hotfix to see if multi-cursor works...

1. cloned text cursors does not have visible indicators; (the real cursor has underline, make the cloned ones have some kind of visual element! like cursor block or line, which can be customized using `.env.example`)
2. hotkey for "cursor above or below" directions are wrong; (need to be swapped)
3. hotkey "cursor expand or shrink" directions are wrong. (need to be swapped)
