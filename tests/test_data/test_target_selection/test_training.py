import numpy as np
import pytest

from fantasy_sim.data.target_selection.training import (
    TargetSelectionExample,
    fit_conditional_softmax,
)


def test_fit_conditional_softmax_learns_positive_feature_for_label():
    examples = [
        TargetSelectionExample(
            features=np.array([[1.0], [0.0]]),
            legacy_weights=np.array([0.5, 0.5]),
            label_index=0,
        )
        for _ in range(20)
    ]

    fit = fit_conditional_softmax(examples, ("winner_feature",), l2=0.1, max_iter=100)

    assert fit.num_examples == 20
    assert fit.coefficients["winner_feature"] > 0


def test_fit_conditional_softmax_rejects_empty_examples():
    with pytest.raises(ValueError, match="zero examples"):
        fit_conditional_softmax([], ("feature",))


def test_fit_conditional_softmax_validates_feature_shape():
    example = TargetSelectionExample(
        features=np.array([[1.0, 0.0]]),
        legacy_weights=np.array([1.0]),
        label_index=0,
    )

    with pytest.raises(ValueError, match="feature matrix"):
        fit_conditional_softmax([example], ("one_feature",))
