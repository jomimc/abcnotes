"""
Tests over the ABC files in tests/fixtures/: every tune must parse, validate
cleanly and expand its repeats, and a few are checked for the exact
playback order.
"""

import glob
import os
import re

import pytest

import abcnotes

FIXTURES = os.path.join(os.path.dirname(__file__), 'fixtures')


def load_fixtures():
    """pytest params (file name, X: number, ABC text) for every tune in
    every fixture file, with the X: number and T: title in the id.
    """
    params = []
    for path in sorted(glob.glob(os.path.join(FIXTURES, '*.abc'))):
        with open(path, encoding='utf-8') as f:
            text = f.read()
        name = os.path.basename(path)
        for abc in abcnotes.split_tunes(text):
            x = re.search(r'^X:\s*(\S+)', abc, re.M).group(1)
            title = re.search(r'^T:\s*(.*)$', abc, re.M).group(1).strip()
            params.append(pytest.param(name, x, abc, id='%s X:%s %s' % (name, x, title)))
    return params


FIXTURE_TUNES = load_fixtures()


def fixture(name, x):
    """The Tune with reference number x in fixture file name."""
    for n, ref, abc in (p.values for p in FIXTURE_TUNES):
        if n == name and ref == str(x):
            return abcnotes.Tune(abc=abc)
    raise KeyError((name, x))


def played(t):
    """Note letters in playback order, one string per bar with notes
    (grace notes left out).
    """
    out = []
    for bar in t.expand_repeats():
        letters = ''.join(tok.note for tok in bar if isinstance(tok, abcnotes.Note) and not tok.grace)
        if letters:
            out.append(letters)
    return ' '.join(out)


def test_fixtures_found():
    assert len(FIXTURE_TUNES) >= 9


# --- every tune ------------------------------------------------------------

@pytest.mark.parametrize('name, x, abc', FIXTURE_TUNES)
def test_parses(name, x, abc):
    t = abcnotes.Tune(abc=abc)
    assert str(t.reference) == x
    assert t.title
    assert t.notes
    assert len(t.bars) > 1


@pytest.mark.parametrize('name, x, abc', FIXTURE_TUNES)
def test_validates_cleanly(name, x, abc):
    assert abcnotes.validate(abc) == []


@pytest.mark.parametrize('name, x, abc', FIXTURE_TUNES)
def test_expands_repeats(name, x, abc):
    t = abcnotes.Tune(abc=abc)
    out = t.expand_repeats()
    assert out
    melody = [n for n in t.notes if not n.grace]
    expanded = [tok for bar in out for tok in bar if isinstance(tok, abcnotes.Note) and not tok.grace]
    assert len(expanded) >= len(melody)
    assert all(n.abs_duration > 0 for n in melody)
    assert all(isinstance(n.pitch.abs_value, int) for n in melody)


@pytest.mark.parametrize('name, x, abc', FIXTURE_TUNES)
def test_expansion_keeps_bar_objects(name, x, abc):
    # Tune.bars builds new lists on every call, so expand the one list
    # directly: every bar played must be one of its bars, by identity
    bars = abcnotes.Tune(abc=abc).bars
    out = abcnotes.expand_repeats(bars)
    assert all(any(bar is src for src in bars) for bar in out)
    assert len(set(id(bar) for bar in out)) <= len(bars)


# --- playback order ----------------------------------------------------------

def test_twinkle():
    # A with first and second ending, B repeated, A once more
    t = fixture('twinkle.abc', 1)
    assert t.header['key'] == 'C'
    assert played(t) == 'CCGG AAG FFEE DDC CCGG AAG FFEE DC GGFF EED GGFF EED CCGG AAG FFEE DDC'
    assert [n.pitch.abs_value for n in t.notes[:7]] == [0, 0, 7, 7, 9, 9, 7]
    assert [n.abs_duration for n in t.notes[:7]] == [0.25] * 6 + [0.5]


def test_standard_first_and_second_ending():
    # the 4.9 example: first ending, then the body again, then the second
    t = fixture('standard_examples.abc', 1)
    assert played(t) == 'fafgfe dfedBA fafgfe dedcB'


def test_standard_double_colon():
    t = fixture('standard_examples.abc', 2)
    assert played(t) == 'ABcd efga ABcd efga bagf edcB bagf edcB'


def test_standard_three_times():
    t = fixture('standard_examples.abc', 3)
    assert played(t) == ' '.join(['ABcd efga'] * 3)


def test_standard_four_passes():
    t = fixture('standard_examples.abc', 4)
    assert t.header['parts'] == 'A'
    assert played(t) == 'ABcd efga ABcd bagf ABcd efga ABcd edcB'


def test_standard_parts():
    t = fixture('standard_examples.abc', 5)
    assert t.header['parts'] == 'ABAB'
    assert [name for name, bars in t.parts] == ['A', 'B']
    assert played(t) == 'ABcd efga bagf edcB ABcd efga bagf edcB'


def test_jacobs_merry_coblers():
    # :: closes the first strain and opens the second, which has two endings
    t = fixture('jacobs.abc', 13)
    first = 'A FDFGAddf dfdeEEA FDFGAddg faefdDD'
    second = 'g fdefaeef fdgfeEEg'
    assert played(t) == ' '.join([first, first,
                                  second, 'fdfgaeeg fdecdDD',
                                  second, 'fdgeafge fdecdDD'])


def test_jacobs_drunken_friday():
    # no |: in the first strain: its :| repeats from the start of the tune
    t = fixture('jacobs.abc', 193)
    first = 'A dddfedAAB cdcAGFEDCD dddfedAAB cGcEDDDD'
    second = 'A FGAFDFGAdF EFGECEFGcE'
    assert played(t) == ' '.join([first, first,
                                  second, 'FGAFDFGAdF GFEDCEDDDD',
                                  second, 'dBcABGcE CEcEDDDD'])


def test_jacobs_the_feathers():
    # four repeated strains, the last with first and second endings
    t = fixture('jacobs.abc', 79)
    bars = played(t).split()
    assert len(bars) == 3 * 16 + 2 * 8
    last = 'BdB ecABcA BdB fedc BdB ecABcA'
    assert ' '.join(bars[48:]) == ' '.join([last, 'cdcd dc', last, 'FBdc cB'])
