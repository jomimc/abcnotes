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


def test_comment_in_json_body():
    rec = {'tune_id': '1', 'setting_id': '2', 'name': 't', 'meter': '4/4',
           'mode': 'Dmajor', 'abc': 'AB%comment\r\nC'}
    t = pyabc.Tune(json=rec)
    assert [n.note for n in t.notes] == ['A', 'B', 'C']
