"""
Tests for parsing whole tunes from ABC text
"""

import pytest

import pyabc


def tune(body, **fields):
    """Build a minimal tune. Header fields are given as keyword arguments
    using the field letter, e.g. M='6/8'; K defaults to C.
    """
    fields.setdefault('K', 'C')
    header = ''.join('%s:%s\n' % (k, v) for k, v in fields.items())
    return pyabc.Tune(abc='X:1\nT:test\n' + header + body + '\n')


# --- meter and unit note length -------------------------------------------

@pytest.mark.parametrize('meter, expected', [
    ('4/4', (4, 4)),
    ('6/8', (6, 8)),
    ('C', (4, 4)),
    ('C|', (2, 2)),
    ('(2+3)/8', (5, 8)),
    ('2+2+2+3/16', (9, 16)),
    ('2 + 5/8', (7, 8)),
    ('none', None),
    (' 3/4 ', (3, 4)),
])
def test_parse_meter(meter, expected):
    assert pyabc.parse_meter(meter) == expected


def test_parse_meter_invalid():
    with pytest.raises(ValueError):
        pyabc.parse_meter('abc')


@pytest.mark.parametrize('fields, unit', [
    (dict(M='C'), [1, 8]),           # no L: with common time
    (dict(M='C|'), [1, 8]),
    (dict(M='6/8'), [1, 8]),
    (dict(M='2/4'), [1, 16]),        # meter < 0.75
    (dict(M='2+2+2+3/16'), [1, 16]),
    (dict(M='none'), [1, 8]),
    (dict(), [1, 8]),                # no M: at all
    (dict(M='none', L='1/4'), [1, 4]),
    (dict(L='1/16'), [1, 16]),
])
def test_default_unit_note_length(fields, unit):
    t = tune('A B', **fields)
    assert t.notes[0].time_sig._unit_len == unit


def test_free_meter_repr():
    assert repr(tune('A', M='none').notes[0].time_sig) == '<TimeSignature free>'


# --- comments ----------------------------------------------------------------

@pytest.mark.parametrize('line, expected', [
    ('AB%comment', 'AB'),
    ('AB|%comment', 'AB|'),
    ('%comment', ''),
    ('AB', 'AB'),
    ('A\\%B%c', 'A\\%B'),          # escaped percent is not a comment
])
def test_strip_comment(line, expected):
    assert pyabc.strip_comment(line) == expected


def test_comment_in_header_keeps_preceding_char():
    t = tune('A', K='Edor%comment')
    assert t.header['key'] == 'Edor'


def test_comment_in_body():
    t = tune('AB%comment\nC|%comment\nD')
    assert [n.note for n in t.notes] == ['A', 'B', 'C', 'D']
    assert any(isinstance(tok, pyabc.Beam) for tok in t.tokens)


# --- field lines -------------------------------------------------------------

def test_empty_body_field_line():
    # W: lyrics after the body, including an empty W: line
    t = tune('AB|\nW:some words\nW:\nw:\nCD|')
    assert [n.note for n in t.notes] == ['A', 'B', 'C', 'D']
    fields = [tok._text for tok in t.tokens if isinstance(tok, pyabc.BodyField)]
    assert fields == ['W:some words', 'W:', 'w:']


def test_one_char_header_line_is_ignored():
    t = pyabc.Tune(abc='X:1\nT:test\nZ\nK:C\nAB\n')
    assert [n.note for n in t.notes] == ['A', 'B']


def test_leading_continuation_line_is_ignored():
    t = pyabc.Tune(abc='+:stray\nX:1\nT:test\nK:C\nAB\n')
    assert t.header['tune title'] == 'test'


# --- bar lines and endings ---------------------------------------------------

def bars(t):
    return [tok._text for tok in t.tokens if isinstance(tok, pyabc.Beam)]


@pytest.mark.parametrize('body, expected', [
    ('|1 A :|2 B |]', ['|1', ':|2', '|]']),
    ('|: A [1 B :|[2 C ||', ['|:', '[1', ':|[2', '||']),
    ('[1,3 A :|[2,4 B |', ['[1,3', ':|[2,4', '|']),
    ('|1-3 A :|4 B |', ['|1-3', ':|4', '|']),
    ('[1,3-5 A :|', ['[1,3-5', ':|']),
])
def test_ending_lists(body, expected):
    assert bars(tune(body)) == expected


def test_chord_after_bar_is_not_an_ending():
    t = tune('|[CEG] A')
    assert [n.note for n in t.notes] == ['C', 'E', 'G', 'A']
    assert bars(t) == ['|']
    assert [tok._text for tok in t.tokens if isinstance(tok, pyabc.ChordBracket)] == ['[', ']']


@pytest.mark.parametrize('text, start, end, endings, double', [
    ('|', False, False, None, False),
    ('||', False, False, None, True),
    ('|]', False, False, None, True),
    ('[|', False, False, None, True),
    ('[|]', False, False, None, True),
    ('|:', True, False, None, False),
    (':|', False, True, None, False),
    ('::', True, True, None, False),
    (':|:', True, True, None, False),
    ('|::', True, False, None, False),
    (':|]', False, True, None, True),
    ('|1', False, False, [1], False),
    ('[2', False, False, [2], False),
    (':|2', False, True, [2], False),
    ('[1,3-5', False, False, [1, 3, 4, 5], False),
    (':|2,4', False, True, [2, 4], False),
])
def test_barline_attributes(text, start, end, endings, double):
    b = [tok for tok in tune('A %s B' % text).tokens if isinstance(tok, pyabc.BarLine)]
    assert len(b) == 1
    assert (b[0]._text, b[0].repeat_start, b[0].repeat_end, b[0].endings, b[0].double) == \
        (text, start, end, endings, double)


def test_beam_is_an_alias_for_barline():
    assert pyabc.Beam is pyabc.BarLine
    assert all(isinstance(tok, pyabc.Beam) for tok in tune('A|B').tokens if isinstance(tok, pyabc.BarLine))


def test_bars_grouping():
    t = tune('A B|:C D|E F:|G|]')
    groups = [[tok._text for tok in bar if not isinstance(tok, (pyabc.Space, pyabc.Newline))]
              for bar in t.bars]
    assert groups == [['A', 'B'], ['|:', 'C', 'D'], ['|', 'E', 'F'], [':|', 'G'], ['|]']]


# --- chords ------------------------------------------------------------------

@pytest.mark.parametrize('body, expected', [
    ('[CEG] A', [1, 1, 1, 1]),
    ('[CEG]2 A', [2, 2, 2, 1]),
    ('[CEG]/ [CE]// [CE]3/2', [0.5, 0.5, 0.5, 0.25, 0.25, 1.5, 1.5]),
    ('[C2E2]2', [4, 4]),
    ('[CE]>A', [1.5, 1.5, 0.5]),
    ('A>[CE]', [1.5, 0.5, 0.5]),
    ('[CE]<[DF]', [0.5, 0.5, 1.5, 1.5]),
    ('[CE]>>A', [1.75, 1.75, 0.25]),
])
def test_chord_lengths(body, expected):
    assert durations(body) == pytest.approx(expected)


def test_chord_tokens():
    t = tune('[CE]2|')
    close = [tok for tok in t.tokens if isinstance(tok, pyabc.ChordBracket)][1]
    assert close._text == ']2'
    assert [n.note for n in close.notes] == ['C', 'E']
    assert bars(t) == ['|']


def test_stray_closing_bracket_is_harmless():
    assert durations('A B]2 C') == [1, 1, 1]


def test_unclosed_chord_ends_at_bar_line():
    assert durations('[A|:B>C') == [1, 1.5, 0.5]


def test_chord_tie():
    t = tune('[CE]-[CE] A')
    assert [n.tie for n in t.notes] == [True, True, False, False, False]


# --- tuplets -----------------------------------------------------------------

@pytest.mark.parametrize('body, fields, expected', [
    ('(3ABC D', dict(), [2 / 3] * 3 + [1]),
    ('(3A2B2C2 D', dict(), [4 / 3] * 3 + [1]),
    ('(2AB C', dict(), [1.5, 1.5, 1]),
    ('(4ABCD E', dict(), [0.75] * 4 + [1]),
    ('(6ABCDEF G', dict(), [1 / 3] * 6 + [1]),
    ('(8ABCDEFGA B', dict(), [3 / 8] * 8 + [1]),
    ('(5ABCDE F', dict(M='4/4'), [2 / 5] * 5 + [1]),      # simple meter: in the time of 2
    ('(5ABCDE F', dict(M='6/8'), [3 / 5] * 5 + [1]),      # compound meter: in the time of 3
    ('(7ABCDEFG A', dict(M='9/8'), [3 / 7] * 7 + [1]),
    ('(3:2:2AB C', dict(), [2 / 3, 2 / 3, 1]),            # explicit p:q:r
    ('(3:2:4ABCD E', dict(), [2 / 3] * 4 + [1]),
    ('(3::2AB C', dict(), [2 / 3, 2 / 3, 1]),
    ('(3:4ABC D', dict(), [4 / 3] * 3 + [1]),
    ('(3AzC D', dict(), [2 / 3] * 3 + [1]),               # rests count
    ('(3A[CE]B D', dict(), [2 / 3] * 4 + [1]),            # a chord counts once
    ('(3A>BC D', dict(), [1, 1 / 3, 2 / 3, 1]),
])
def test_tuplets(body, fields, expected):
    assert durations(body, **fields) == pytest.approx(expected)


def test_tuplet_token_fields():
    t = [tok for tok in tune('(3:2:4ABCD').tokens if isinstance(tok, pyabc.Tuplet)][0]
    assert (t.num, t.p, t.q, t.r, t._text) == ('3', 3, 2, 4, '(3:2:4')
    assert bars(tune('(3:2:4ABCD')) == []


# --- robustness --------------------------------------------------------------

def test_strict_raises_on_unknown_character():
    with pytest.raises(Exception):
        tune('A \x01 B')


def test_non_strict_records_unknown_characters():
    t = pyabc.Tune(abc='X:1\nT:t\nK:C\nA \x01 B}\n', strict=False)
    unknown = [tok for tok in t.tokens if isinstance(tok, pyabc.Unknown)]
    assert [(u._text, u._line, u._char) for u in unknown] == [('\x01', 0, 2)]
    assert [n.note for n in t.notes] == ['A', 'B']


def test_grace_note_flag():
    t = tune('{g}A {/ab}B C')
    assert [(n.note, n.grace) for n in t.notes] == \
        [('g', True), ('A', False), ('a', True), ('b', True), ('B', False), ('C', False)]


def test_missing_reference_and_title():
    t = pyabc.Tune(abc='K:D\nF\n')
    assert (t.reference, t.title) == (None, None)
    assert [n.pitch.abs_value for n in t.notes] == [6]


def test_missing_key_field():
    # no K: means no tune body at all; nothing to parse, nothing raised
    t = pyabc.Tune(abc='X:1\nT:t\nM:4/4\n')
    assert t.notes == []


def test_unknown_header_lines_are_recorded():
    t = pyabc.Tune(abc='X:1\nT:t\nsome free text\nZZ:not a field\nK:C\nA\n')
    assert t.unknown_lines == [(2, 'some free text'), (3, 'ZZ:not a field')]


def test_bars_no_pickup():
    assert [bar[0]._text for bar in tune('|:A|B:|').bars] == ['|:', '|', ':|']


# --- chord symbols and annotations -------------------------------------------

@pytest.mark.parametrize('text', [
    '"G"', '"Em7"', '"G/B"', '"D/f+"', '"G(Em)"', '"N.C."', '"Reel."',
    '"Star of the County Down"', '""', '"D.C. to Allegro."',
])
def test_chord_symbol_liberal(text):
    t = tune('%sA B' % text)
    syms = [tok for tok in t.tokens if isinstance(tok, pyabc.ChordSymbol)]
    assert [s._text for s in syms] == [text]
    assert [n.note for n in t.notes] == ['A', 'B']


@pytest.mark.parametrize('text', ['"^above"', '"_below"', '"<left"', '">right"', '"@free"'])
def test_annotation_placement(text):
    t = tune('%sA' % text)
    assert [tok._text for tok in t.tokens if isinstance(tok, pyabc.Annotation)] == [text]
    assert not any(isinstance(tok, pyabc.ChordSymbol) for tok in t.tokens)


def test_unterminated_quote_still_fails():
    with pytest.raises(Exception):
        tune('"G A B')


# --- key field ---------------------------------------------------------------

@pytest.mark.parametrize('key, root, mode, accidentals', [
    ('none', 'C', 'major', {}),
    ('', 'C', 'major', {}),
    ('HP', 'D', 'major', {'F': '#', 'C': '#'}),
    ('Hp', 'D', 'major', {'F': '#', 'C': '#'}),
    ('D clef=bass', 'D', 'major', {'F': '#', 'C': '#'}),
    ('D clef=bass middle=d', 'D', 'major', {'F': '#', 'C': '#'}),
    ('Dmaj clef=treble', 'D', 'major', {'F': '#', 'C': '#'}),
    ('Am treble', 'A', 'minor', {}),
    ('G transpose=-2', 'G', 'major', {'F': '#'}),
    ('clef=bass', 'C', 'major', {}),
    ('clef=bass middle=d', 'C', 'major', {}),
])
def test_key_specifiers(key, root, mode, accidentals):
    k = pyabc.Key(key)
    assert (k.root.name, k.mode) == (root, mode)
    assert k.accidentals == accidentals


@pytest.mark.parametrize('key, accidentals', [
    ('D ^g', {'F': '#', 'C': '#', 'G': '#'}),
    ('D =c', {'F': '#', 'C': ''}),
    ('D _b', {'F': '#', 'C': '#', 'B': 'b'}),
    ('F ^f', {'B': 'b', 'F': '#'}),
    ('C ^^f __b', {'F': '##', 'B': 'bb'}),
    ('D exp ^f', {'F': '#'}),                    # exp: no key signature, only these
    ('D exp', {}),
    ('D clef=bass ^g', {'F': '#', 'C': '#', 'G': '#'}),
    ('Dmix ^g', {'F': '#', 'G': '#'}),
])
def test_key_explicit_accidentals(key, accidentals):
    assert pyabc.Key(key).accidentals == accidentals


@pytest.mark.parametrize('body, expected', [
    ('g c', [20, 13]),                  # K:D ^g: G# and C#
    ('f [K:=f] f', [18, 17]),           # accidentals-only inline key modifies the current key
    ('f [K:=f] c', [18, 13]),           # ...without touching the rest of the signature
    ('f [K:=f] [K:^c] c f', [18, 13, 17]),
    ('f [K:G] f', [18, 18]),            # a full inline key replaces it
    ('f [K:G] [K:=f] f', [18, 17]),
])
def test_key_accidentals_in_body(body, expected):
    assert pitches(body, K='D ^g') == expected


# --- fields in the tune body -------------------------------------------------

def test_body_key_line_changes_key():
    assert pitches('F\nK:D\nF\n[K:G]F', K='C') == [5, 6, 6]


def test_body_meter_and_length_fields():
    t = tune('A\nM:6/8\nA [M:3/4] A\nL:1/16\nA [L:1/4] A', M='4/4', L='1/8')
    assert [n.time_sig._meter for n in t.notes] == [(4, 4), (6, 8), (3, 4), (3, 4), (3, 4)]
    assert [n.time_sig._unit_len for n in t.notes] == [[1, 8], [1, 8], [1, 8], [1, 16], [1, 4]]


def test_body_tempo_field():
    t = tune('A [Q:1/4=80] A', Q='1/4=120')
    assert [n.time_sig._tempo[1] for n in t.notes] == [120, 80]


@pytest.mark.parametrize('body, fields, expected', [
    ('A A2 A/', dict(L='1/8'), [1 / 8, 1 / 4, 1 / 16]),
    ('A', dict(L='1/4'), [1 / 4]),
    ('A', dict(L='1'), [1.0]),
    ('A [L:1/16] A', dict(L='1/8'), [1 / 8, 1 / 16]),
    ('A z2', dict(M='2/4'), [1 / 16, 1 / 8]),          # default L: from the meter
    ('Z Z2 X', dict(M='6/8', L='1/8'), [6 / 8, 12 / 8, 6 / 8]),   # measure rests
    ('Z', dict(M='none', L='1/8'), [1 / 8]),           # no meter: fall back to L:
])
def test_abs_duration(body, fields, expected):
    toks = [tok for tok in tune(body, **fields).tokens if isinstance(tok, (pyabc.Note, pyabc.Rest))]
    assert [tok.abs_duration for tok in toks] == pytest.approx(expected)


def test_double_sharp_key_signature_pitch():
    assert pitches('f', K='C ^^f') == [19]


def test_key_field_with_comment():
    t = tune('A', K='D % and Dm')
    assert t.notes[0].key.root.name == 'D'


# --- note and rest lengths, broken rhythm ------------------------------------

def durations(body, **fields):
    return [tok.duration for tok in tune(body, **fields).tokens if isinstance(tok, (pyabc.Note, pyabc.Rest))]


@pytest.mark.parametrize('body, expected', [
    ('A A2 A3', [1, 2, 3]),
    ('A/ A// A/// A/4 A3/2 A2/3', [0.5, 0.25, 0.125, 0.25, 1.5, 2 / 3]),
    ('z z2 z/ z// z3/2 Z Z2 x x/', [1, 2, 0.5, 0.25, 1.5, 1, 2, 1, 0.5]),
])
def test_lengths(body, expected):
    assert durations(body) == pytest.approx(expected)


@pytest.mark.parametrize('body, expected', [
    ('A>B', [1.5, 0.5]),
    ('A<B', [0.5, 1.5]),
    ('A>>B', [1.75, 0.25]),
    ('A<<B', [0.25, 1.75]),
    ('A>>>B', [1.875, 0.125]),
    ('A2>B', [3, 0.5]),
    ('A>B2', [1.5, 1]),
    ('A > B', [1.5, 0.5]),
    ('A >B C< D', [1.5, 0.5, 0.5, 1.5]),
    ('A>B C<D', [1.5, 0.5, 0.5, 1.5]),      # a later < must not flip the first >
    ('z>A A>z', [1.5, 0.5, 1.5, 0.5]),
    ('A>B|C>D', [1.5, 0.5, 1.5, 0.5]),
])
def test_broken_rhythm(body, expected):
    assert durations(body) == pytest.approx(expected)


def test_rest_symbol_and_length():
    r = [tok for tok in tune('Z2 z/').tokens if isinstance(tok, pyabc.Rest)]
    assert [(x.symbol, x.length) for x in r] == [('Z', (2, 1)), ('z', (1, 2))]


# --- decorations and ignorable symbols ---------------------------------------

def kinds(body):
    return [type(tok).__name__ for tok in tune(body).tokens
            if not isinstance(tok, (pyabc.Space, pyabc.Newline))]


@pytest.mark.parametrize('body, expected', [
    ('.A ~B HC', ['Decoration', 'Note', 'Decoration', 'Note', 'Decoration', 'Note']),
    ('JA RB uC vD', ['Decoration', 'Note'] * 4),         # U:-definable letters
    ('!trill!A +trill+B', ['Decoration', 'Note', 'Decoration', 'Note']),
    ('A&B', ['Note', 'VoiceOverlay', 'Note']),
    ('A y B $ C`D', ['Note', 'Ignored', 'Note', 'Ignored', 'Note', 'Ignored', 'Note']),
    ('A # B * C ; D ? E @ F', ['Note', 'Ignored'] * 5 + ['Note']),
])
def test_decorations_and_ignored(body, expected):
    assert kinds(body) == expected


def test_old_style_line_break():
    t = tune('AB|!\nCD|!\n')
    assert [n.note for n in t.notes] == ['A', 'B', 'C', 'D']
    assert [tok._text for tok in t.tokens if isinstance(tok, pyabc.Ignored)] == ['!', '!']


def test_rests_and_spacer_are_not_decorations():
    assert kinds('x z y') == ['Rest', 'Rest', 'Ignored']


# --- header fields -----------------------------------------------------------

def test_fields_keep_every_field_in_order():
    t = pyabc.Tune(abc='X:1\nT:First\nT:Second\nI:linebreak $\n%%propagate-accidentals not\nK:C\nA\n')
    assert t.fields == [('reference number', '1'), ('tune title', 'First'),
                        ('tune title', 'Second'), ('instruction', 'linebreak $'),
                        ('instruction', 'propagate-accidentals not'), ('key', 'C')]
    assert t.header['tune title'] == 'First'
    assert t.title == 'First'


def test_fields_on_json_path():
    rec = {'tune_id': '1', 'setting_id': '2', 'name': 't', 'meter': '4/4',
           'mode': 'Dmajor', 'abc': 'A'}
    assert ('key', 'Dmajor') in pyabc.Tune(json=rec).fields


@pytest.mark.parametrize('q, expected', [
    ('1/4=120', ((1, 4), 120, '')),
    ('120', (None, 120, '')),
    ('"Allegro"', (None, None, 'Allegro')),
    ('"Slow" 1/4=60', ((1, 4), 60, 'Slow')),
    ('3/8 3/8 2/8=40', ((1, 1), 40, '')),
    ('1/4 3/8 1/4=40', ((7, 8), 40, '')),
    ('', (None, None, '')),
])
def test_parse_tempo(q, expected):
    assert pyabc.parse_tempo(q) == expected


def test_tempo_reaches_time_signature():
    t = tune('A', Q='1/4=120')
    assert t.notes[0].time_sig._tempo == ((1, 4), 120, '')


# --- accidentals within a bar ------------------------------------------------

def pitches(body, **fields):
    return [n.pitch.abs_value for n in tune(body, **fields).notes]


@pytest.mark.parametrize('body, fields, expected', [
    ('^F F =F F | F', dict(K='D'), [6, 6, 5, 5, 6]),
    ('c ^c c | c', dict(K='G'), [12, 13, 13, 12]),
    ('=F F | F', dict(K='D'), [5, 5, 6]),
    ('^^F F _F F', dict(), [7, 7, 4, 4]),
    ('^F f | f', dict(), [6, 18, 17]),                 # default: all octaves
    ('^F f | f', dict(I='propagate-accidentals octave'), [6, 17, 17]),
    ('^F F', dict(I='propagate-accidentals not'), [6, 5]),
    ('^F F G ^G G', dict(), [6, 6, 7, 8, 8]),
    ('^F F |1 F :|2 F', dict(), [6, 6, 5, 5]),         # endings are bar lines
])
def test_accidental_propagation(body, fields, expected):
    assert pitches(body, **fields) == expected


def test_propagate_directive_as_stylesheet_line():
    t = pyabc.Tune(abc='X:1\nT:t\n%%propagate-accidentals not\nK:C\n^F F\n')
    assert [n.pitch.abs_value for n in t.notes] == [6, 5]


@pytest.mark.parametrize('body, fields, expected', [
    ('^F- | F F', dict(), [6, 6, 5]),                   # tie carries over the bar line
    ('^F- | F', dict(I='propagate-accidentals not'), [6, 6]),
    ('^F- | G F', dict(), [6, 7, 5]),                    # tie only to the same note
    ('^F- | f', dict(), [6, 17]),                        # same note means same octave
    ('_B2- | B2 B', dict(K='G'), [10, 10, 11]),
])
def test_tie_carries_accidental(body, fields, expected):
    assert pitches(body, **fields) == expected


def test_tie_flag():
    assert [n.tie for n in tune('A-B A- B A B').notes] == [True, False, True, False, False, False]


def test_comment_in_json_body():
    rec = {'tune_id': '1', 'setting_id': '2', 'name': 't', 'meter': '4/4',
           'mode': 'Dmajor', 'abc': 'AB%comment\r\nC'}
    t = pyabc.Tune(json=rec)
    assert [n.note for n in t.notes] == ['A', 'B', 'C']
