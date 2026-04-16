# TODO

## SEARCH

improve search user experience...

ensure the overall search experience is similar to `nano` text editor. ensure to add basic hotkeys and controls which user expects from a text editor. (related to search)

- [^F] triggers search;
- user can do basic editing in search field;
    + cut, copy, paste, select, select all, arrows;
- in search mode...
    + ENTER - find next;
    + SHIFT ENTER - find previous;
    + ESC - leave search mode;
- user can use HELP while in search mode.

## TOKEN

improve estimated token counter...

user noticed when using `tree` mod with adjusted depth, the token counter does not change...

- ensure token counter is accurate and respects parameters and produces actual estimated token count rather than ignoring parameters and other specifics.

## FILE

improve `file` mod...

- when picking file, suggest whether to close tag `>` or insert `:` to include line argument;
- implement line number suggestion, count the lines in the target file or record them in index and show them in the list;
- to be more clear, first suggest the available types...
    + first [n];
    + last [n];
    + [n]-[m];
    + #[n];
- then after user selections one or writes one, suggest only line numbers like this...

```md
1
2
3
4
5
...

```

## SPEED

ensure good performance and utilize caching and indexing.
