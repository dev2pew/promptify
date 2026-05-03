[ general ]

^[G] / [F1]                   : help
^[F]                          : search
^[R]                          : replace
^[S]                          : resolve

^[^/v]                        : scroll view
[Alt] + [G]                   : jump to line
[Alt] + [Z]                   : word wrap

[Esc]                         : close pane
^[Q] / [F10]                  : abort

[ search ]

[Enter]                       : next
[Shift] + [Enter]             : previous
[^/v]                         : history
[F6] / [F7] / [F8]            : case / word / regex

[ replace ]

[Enter]                       : replace
^[Alt] + [Enter]              : replace all
^[F6]                         : preserve case

[ jump ]

[Enter]                       : jump

[ issues ]

[Enter] / ^[N]                : next
^[R] / ^[P]                   : previous

[ autocomplete mentions ]

<@file:path>                  : file
<@symbol:path:name>           : symbol

<@file:path:range>            : slice file
            first n           : head
            last n            : tail
            n-m               : ranged
            #n                : single

<@dir:path>                   : directory

<@tree:path>                  : tree
<@tree:path:level>            : set depth

<@ext:list>                   : type

<@git:diff>                   : work tree diff
<@git:diff:path>              : work tree file diff

<@git:status>                 : work tree status

<@git:log>                    : recent log (20)
<@git:log:count>              : set length

<@git:history>                : recent log w/diff (5)
<@git:history:count>          : set length

<@git:[branch]:subcommand>    : set branch-scope
<@git:[branch]:diff:path>     : ex.
<@git:[branch]:log:count>     : ex.
<@git:[branch]:history:count> : ex.

[@project]                    : project structure

[ editing ]

[Shift]                       : select
^[A]                          : select all
^[D]                          : select next occurrence
^[Shift] + [L]                : select all occurrences

^[Z/Y]                        : undo / redo
^[C/X/V]                      : copy / cut / paste

[Tab]                         : indent / autocomplete
[Shift] + [Tab]               : unindent

[Alt] + [^/v]                 : shift up / down

^[/]                          : comment out
^[W/Del]                      : delete previous / next

^[Alt] + [^/v]                : cursor above / below
^[Shift] + [Alt] + [^/v]      : cursor expand / shrink

[ navigation ]

[^/v/</>]                     : move
^[^/v/</>]                    : next / previous
[Home/End]                    : start / end
^[Home/End]                   : file start / end
^[PgUp/PgDn]                  : up / down (15)

press [Enter], [F1] or ^[G] to close
