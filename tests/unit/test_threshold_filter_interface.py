"""
Unit Tests: IThresholdFilter contract (SCRUM-272)
--------------------------------------------------
Ensures ThresholdFilter explicitly implements the domain filtering interface.
"""

from src.domain.interfaces import IThresholdFilter
from src.domain.threshold_filter import ThresholdFilter


def test_threshold_filter_implements_interface():
    assert issubclass(ThresholdFilter, IThresholdFilter)


def test_threshold_filter_exposes_is_valid_contract():
    assert hasattr(ThresholdFilter, "is_valid")
    assert callable(ThresholdFilter.is_valid)
