abcnotes
========

A parser for tunes written in [ABC music notation](https://abcnotation.com/),
for analysing the music rather than typesetting it. It reads a tune into
tokens, gives each note a pitch and a duration, writes out repeats and
variant endings in playback order, and reports problems in a tune's ABC.

It is a single module, `abcnotes.py`, with no dependencies. Python 3.9 or
later. MIT licence.


Installation
------------

```bash
pip install abcnotes
```

or, from a clone of this repository:

```bash
pip install .
```


Quick start
-----------

### Parse a tune

```python
from abcnotes import Tune

abc = """X: 1
T: The Road To Lisdoonvarna
R: slide
M: 12/8
L: 1/8
K: Edor
E2B B2A B2c d2A|F2A ABA D2E FED|E2B B2A B2c d3|cdc B2A B2E E3:|
|:e2f gfe d2B Bcd|c2A ABc d2B B3|e2f gfe d2B Bcd|cdc B2A B2E E3:||
"""

tune = Tune(abc=abc)
print(tune.header['tune title'])
print(tune.header['key'], tune.header['meter'], tune.header['unit note length'])
print(len(tune.notes), len(tune.bars))
```

```
The Road To Lisdoonvarna
Edor 12/8 1/8
69 10
```

`tune.header` is keyed by the full field names from the ABC standard
(`'key'`, `'meter'`, `'unit note length'`, `'reference number'`, ...), with
the values as written. `tune.fields` keeps every field in order, including
repeated ones.

### Notes, pitches and durations

```python
for note in tune.notes[:6]:
    print(note.pitch.name, note.pitch.abs_value, note.duration, note.abs_duration)
```

```
E 4 2.0 0.25
B 11 1.0 0.125
B 11 2.0 0.25
A 9 1.0 0.125
B 11 2.0 0.25
C# 13 1.0 0.125
```

`note.pitch.abs_value` is the pitch in semitones relative to middle C, with
the key signature applied (the `c` in E dorian is a C sharp). `note.duration`
is in units of the `L:` field and `note.abs_duration` is a fraction of a
whole note. Broken rhythms (`A>B`), chords (`[DF]3`) and tuplets (`(3abc`)
are resolved in these values.

### Expand repeats

`tune.expand_repeats()` returns the bars in playback order. Each bar is a
list of tokens, so the notes of the tune as played are:

```python
from abcnotes import Note, Tune

abc = """X: 2
T: Endings
M: 4/4
L: 1/4
K: G
|: G A B c |1 d2 d2 :|2 g2 g2 |]
"""

tune = Tune(abc=abc)
for bar in tune.expand_repeats():
    names = [token.pitch.name for token in bar if isinstance(token, Note)]
    if names:
        print(' '.join(names))
```

```
G A B C
D D
G A B C
G G
```

If the repeat structure is ambiguous (an ending number that is missing or
repeated, a `|:` that is never closed, endings with no repeat sign, ...) a
`RepeatError` is raised. Pass `strict=False` to get the most likely reading
instead; `check_repeats(tune.bars)` lists the problems without raising.

### Validate a file

```python
import abcnotes

text = """X: 1
T: First
M: 4/4
L: 1/8
K: D
D2 FA d2 fd | A2 F2 e2 | d2-f2 a2 f2 | d4 z4 |]

X: 2
T: Second
K: G
GBd g |]
"""

for abc in abcnotes.split_tunes(text):
    for issue in abcnotes.validate(abc):
        print(issue)
```

```
Issue(line=6, char=26, message='tie from d2 to a different note f2 (a slur was probably meant)')
Issue(line=6, char=15, message='bar 2 has length 3/4, expected 1')
```

`split_tunes` cuts the text of an ABC file into one string per tune, with
any file-header fields prepended to each. `validate` returns a list of
`Issue(line, char, message)` namedtuples with 1-based positions in the
tune's text (`None` when the issue has no single position). It checks:

* required fields (`X:`, `T:`, `K:`) and header lines that are not fields;
* characters the tokenizer cannot read;
* unbalanced chord brackets, grace-note braces and slurs;
* ties between different notes;
* repeat structure (the same problems that make `expand_repeats` raise);
* `P:` parts in the header that are not in the body, and vice versa;
* bar lengths against the meter, tolerating pickups.


API overview
------------

Everything is in the `abcnotes` module.

| Name | What it is |
| --- | --- |
| `Tune(abc=text)` | Parse one tune from its ABC text. |
| `Tune(json=record)` | Parse a record from the [TheSession](https://thesession.org) data dump or API: a dict with keys `tune_id`, `setting_id`, `name`, `type`, `meter`, `mode` and `abc`. |
| `Tune(abc, strict=False)` | Unreadable characters become `Unknown` tokens instead of raising. |
| `tune.header` | Dict of header fields keyed by full name (`'key'`, `'meter'`, `'unit note length'`, ...). |
| `tune.fields` | All header fields in order, as `(name, value)` pairs. |
| `tune.tokens` | The body as a flat list of tokens. |
| `tune.notes` | The `Note` tokens only. |
| `tune.bars` | The tokens grouped by bar. Each bar starts with the `BarLine` that opens it, except for a pickup before the first bar line. |
| `tune.parts` | `(part name, bars)` pairs, split where a `P:` field appears in the body. |
| `tune.expand_repeats(strict=True)` | Bars in playback order, following the `P:` header field if there is one. |
| `tune.validate()` | Problems with the tune, as a list of `Issue`. |
| `Note` | `.pitch` (a `Pitch`, with `.name` and `.abs_value` in semitones from middle C), `.duration` (in units of `L:`), `.abs_duration` (fraction of a whole note), `.length` (as a `(numerator, denominator)` pair), `.tie`, `.grace`, `.accidental`, `.bar_accidental`, `.key`, `.time_sig`. |
| `Rest` | `.duration`, `.abs_duration` and `.length` as for `Note`; `.symbol` is one of `z Z x X`. |
| `BarLine` | `.repeat_start`, `.repeat_end`, `.endings` (list of pass numbers, or `None`) and `.double`. |
| `Key` | `Key('Edor')`: `.root`, `.mode`, `.key_signature`, `.accidentals` (including explicit ones such as `K:D ^g`), `.relative_ionian`. |
| `TimeSignature` | Meter, unit note length and tempo in force at a note (`note.time_sig`). |
| `expand_repeats(bars, strict=True)` | The module-level function behind `tune.expand_repeats`. |
| `check_repeats(bars)` | Repeat-structure problems as `(bar index, message)` pairs. |
| `RepeatError` | Raised by `expand_repeats` when the structure is ambiguous. |
| `validate(abc)` | Parse with `strict=False` and return `tune.validate()`. |
| `Issue` | `namedtuple('Issue', 'line char message')`. |
| `split_tunes(text)` | Cut the text of an ABC file into one string per tune. |
| `parse_parts(spec)` | Expand a `P:` field: `'(AB)2.C'` becomes `['A', 'B', 'A', 'B', 'C']`. |

Other token classes are `Space`, `Newline`, `Continuation`, `Slur`, `Tie`,
`Tuplet`, `ChordBracket`, `ChordSymbol`, `Annotation`, `Decoration`,
`GracenoteBrace`, `VoiceOverlay`, `BodyField`, `InlineField`, `Ignored` and
`Unknown`.

Some points of behaviour:

* An accidental lasts until the end of the bar, for the same note letter in
  every octave, as the standard says; `I:propagate-accidentals` is honoured.
* Explicit accidentals in the `K:` field (`K:D ^g`, `K:C exp ^f`) are
  applied.
* `K:`, `M:`, `L:` and `Q:` fields in the body, and inline fields such as
  `[K:G]`, take effect from where they appear.
* Repeat expansion follows sections 4.8 to 4.10 of the ABC 2.1 standard:
  `|1`, `[1,3` and `[1-3` endings, `::`, `|::` (three passes) and `P:`
  parts. A `:|` with no matching `|:` restarts from the latest of the start
  of the tune, a double bar and the previous `:|`.


Limitations
-----------

* Multi-voice tunes (`V:`) are parsed as a single line of music. Bar lengths
  are not checked for them and `expand_repeats` refuses them unless
  `strict=False`.
* `D.C.`, `D.S.`, coda and fine jumps are not followed.
* Lyrics (`w:`) are not aligned to notes.


Status
------

Alpha. The parser has been checked against the whole TheSession corpus and
the Norbeck, Cobbs, Nottingham and Chambers collections, and repeat
expansion has been cross-checked against music21. The API may still change.


Development
-----------

Run the tests from the root of the repository:

```bash
python -m pytest
```

`pyproject.toml` puts the repository root on the path for pytest, so no
install is needed.


History and credits
-------------------

abcnotes started as [pyabc](https://github.com/campagnola/pyabc), written by
Luke Campagnola in 2014 and released under the MIT licence as a pre-alpha.
John McBride forked it to read the TheSession data set and fixed and
extended it over several years. In September 2026, in
[issue #31](https://github.com/campagnola/pyabc/issues/31) of the original
repository, Luke Campagnola agreed that the fork becomes the maintained
version under a new name, published to PyPI, and that the original
repository will point here.


Licence
-------

MIT. See `LICENSE.txt`.
