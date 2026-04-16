# TODO

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

- ...and on other number select, automatically close the tag.

## SPEED

ensure good performance and utilize caching and indexing.
