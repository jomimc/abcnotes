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
    # (the '[' is currently merged into the bar token as '|['; the notes
    # must still come through and no ending number must be captured)
    t = tune('|[CEG] A')
    assert [n.note for n in t.notes] == ['C', 'E', 'G', 'A']
    assert not any(c.isdigit() for c in ''.join(bars(t)))


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
    ('D exp ^f ^c', 'D', 'major', {'F': '#', 'C': '#'}),   # explicit accidentals not yet applied
    ('F ^f', 'F', 'major', {'B': 'b'}),                    # explicit accidentals not yet applied
])
def test_key_specifiers(key, root, mode, accidentals):
    k = pyabc.Key(key)
    assert (k.root.name, k.mode) == (root, mode)
    assert k.accidentals == accidentals


def test_key_field_with_comment():
    t = tune('A', K='D % and Dm')
    assert t.notes[0].key.root.name == 'D'


# --- note and rest lengths, broken rhythm ------------------------------------

def durations(body):
    return [tok.duration for tok in tune(body).tokens if isinstance(tok, (pyabc.Note, pyabc.Rest))]


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


def test_comment_in_json_body():
    rec = {'tune_id': '1', 'setting_id': '2', 'name': 't', 'meter': '4/4',
           'mode': 'Dmajor', 'abc': 'AB%comment\r\nC'}
    t = pyabc.Tune(json=rec)
    assert [n.note for n in t.notes] == ['A', 'B', 'C']
