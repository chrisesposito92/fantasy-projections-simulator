"""Tests for _normalize_name() helper used in snap crosswalk Tier 2 matching."""

from __future__ import annotations

import pytest

from fantasy_sim.data.usage.engine import _normalize_name


class TestNormalizeName:
    """Unit tests for _normalize_name(): suffix stripping, case folding, middle names."""

    def test_lowercase(self):
        assert _normalize_name("Grant DuBose") == "grant dubose"

    def test_strip_jr_dot(self):
        assert _normalize_name("Kevin Austin Jr.") == "kevin austin"

    def test_strip_jr_no_dot(self):
        assert _normalize_name("Velus Jones Jr") == "velus jones"

    def test_strip_sr_dot(self):
        assert _normalize_name("Gary Smith Sr.") == "gary smith"

    def test_strip_ii(self):
        assert _normalize_name("Kwamie Lassiter II") == "kwamie lassiter"

    def test_strip_iii(self):
        assert _normalize_name("Kenneth Walker III") == "kenneth walker"

    def test_strip_iv(self):
        assert _normalize_name("John Doe IV") == "john doe"

    def test_strip_v(self):
        assert _normalize_name("Henry Thomas V") == "henry thomas"

    def test_middle_name_collapsed(self):
        """Middle names are dropped: first + last only."""
        assert _normalize_name("John Samuel Shenker") == "john shenker"

    def test_periods_stripped(self):
        assert _normalize_name("D.J. Turner") == "dj turner"

    def test_apostrophe_preserved(self):
        """Apostrophes in names like D'Vonte are preserved."""
        assert _normalize_name("D'Vonte Price") == "d'vonte price"

    def test_no_suffix_unchanged(self):
        assert _normalize_name("Rodney Williams") == "rodney williams"

    def test_two_word_name_unchanged(self):
        assert _normalize_name("Pat Mahomes") == "pat mahomes"

    def test_whitespace_trimmed(self):
        assert _normalize_name("  Kenneth Walker III  ") == "kenneth walker"

    def test_suffix_ii_not_stripped_from_middle(self):
        """II is only stripped at end of name, not from middle."""
        assert _normalize_name("II Smith Jones") == "ii jones"
