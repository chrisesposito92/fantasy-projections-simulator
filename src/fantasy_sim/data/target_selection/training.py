"""Training helpers for the learned receiver target-selection model."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.optimize import minimize


@dataclass(frozen=True)
class TargetSelectionExample:
    """One historical pass target event with the full candidate set."""

    features: np.ndarray
    legacy_weights: np.ndarray
    label_index: int


@dataclass(frozen=True)
class TargetSelectionFitResult:
    coefficients: dict[str, float]
    objective: float
    converged: bool
    iterations: int
    num_examples: int


def fit_conditional_softmax(
    examples: list[TargetSelectionExample],
    feature_names: tuple[str, ...],
    *,
    l2: float = 1.0,
    max_iter: int = 200,
) -> TargetSelectionFitResult:
    """Fit a legacy-anchored conditional softmax with L2 regularization."""
    if not examples:
        raise ValueError("Cannot fit target-selection model with zero examples")
    if not feature_names:
        raise ValueError("feature_names must not be empty")

    n_features = len(feature_names)
    for example in examples:
        if example.features.ndim != 2 or example.features.shape[1] != n_features:
            raise ValueError("Each example feature matrix must be (candidates, features)")
        if example.legacy_weights.shape != (example.features.shape[0],):
            raise ValueError("legacy_weights length must match candidate count")
        if not 0 <= example.label_index < example.features.shape[0]:
            raise ValueError("label_index outside candidate range")

    def objective(beta: np.ndarray) -> tuple[float, np.ndarray]:
        loss = 0.5 * l2 * float(np.dot(beta, beta))
        grad = l2 * beta

        for example in examples:
            base = np.asarray(example.legacy_weights, dtype=float)
            base_sum = float(base.sum())
            if base_sum <= 0:
                base = np.ones_like(base) / len(base)
            else:
                base = base / base_sum
            logits = np.log(np.maximum(base, 1e-12)) + example.features @ beta
            logits -= float(np.max(logits))
            weights = np.exp(logits)
            probs = weights / float(weights.sum())
            label = example.label_index
            loss -= float(np.log(max(probs[label], 1e-12)))
            grad += example.features.T @ probs
            grad -= example.features[label]

        return loss, grad

    result = minimize(
        objective,
        np.zeros(n_features, dtype=float),
        method="L-BFGS-B",
        jac=True,
        options={"maxiter": max_iter},
    )
    coefficients = {
        name: float(value)
        for name, value in zip(feature_names, result.x, strict=True)
    }
    return TargetSelectionFitResult(
        coefficients=coefficients,
        objective=float(result.fun),
        converged=bool(result.success),
        iterations=int(result.nit),
        num_examples=len(examples),
    )
