[ general ]

^[G] / [F1]                   : help
^[F]                          : search
^[S]                          : resolve
^[Q] / [F10]                  : abort

[ search ]

[Enter]                       : next
^[R]                          : previous
[Esc]                         : close

[ issues ]

[Enter] / ^[N]                : next
^[R] / ^[P]                   : previous
[Esc]                         : close

[ autocomplete mentions ]

<@file:path>                  : file
<@file:path:range>            : sliced file

            first n           : head
            last n            : tail
            n-m               : ranged
            #n                : single

<@dir:path>                   : directory
<@tree:path>                  : tree view
<@tree:path:level>            : set depth
<@ext:list>                   : type
<@symbol:path:name>           : symbol
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

^[A]                          : select all
[Shift]                       : select
^[Z/Y]                        : undo / redo
^[C/X/V]                      : copy / cut / paste
[Tab]                         : indent / autocomplete
[Shift] + [Tab]               : unindent
[Alt]   + [^/v]               : shift cursor
^[/]                          : comment out
^[W/Del]                      : delete previous / next
[Enter]                       : newline / accept

[ navigation ]

[^/v/</>]                     : move
^[^/v/</>]                    : next / previous
[Home/End]                    : start / end
^[Home/End]                   : file start / end
^[PgUp/PgDn]                  : up / down (15x)

press [Enter], [F1] or ^[G] to close
