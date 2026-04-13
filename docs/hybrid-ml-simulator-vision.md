# Hybrid ML Simulator Vision

Reference note for a future architecture pivot.

This document is intentionally high level. It is not an implementation plan,
task breakdown, or promotion artifact. Its purpose is to capture the intended
direction of a more ML-native version of this project while preserving what is
already strong about the current simulator.

## Core Idea

The long-term target is not "replace the simulator with a spreadsheet model"
and not "keep hand-tuning rules forever."

The target is a hybrid system:

- a simulation engine still runs the game forward play by play
- learned models drive the important football decisions inside the simulation
- Monte Carlo still produces full distributions, not just point estimates

In other words, the simulator remains the shell, but the transition logic
becomes increasingly learned.

## Why This Pivot Would Exist

The current system is good at:

- generating coherent stat lines
- producing weekly and season distributions
- supporting what-if overrides and counterfactuals
- preserving football structure across drives, possessions, and scoring flow

The current system is weaker at:

- adapting quickly to role drift
- learning complex interactions between offense, defense, player role, and game state
- capturing context-specific behavior without adding more and more manual rules
- learning from many weak signals at once

A hybrid ML simulator is meant to keep the first set of strengths while solving
more of the second set with learned behavior rather than additional heuristics.

## The Intended Hybrid Shape

The guiding idea is simple:

- the game state machine stays
- the random simulation stays
- more of the "what happens next?" logic becomes model-driven

Example:

1. The simulator reaches a state such as: Chiefs ball, 1st-and-10, own 50,
   5:00 left in Q1, tie game.
2. A learned play-call model estimates the probability of run, pass, scramble,
   or other relevant outcomes.
3. If pass is selected, another learned model estimates likely target
   distribution or pass concept family.
4. Additional learned models estimate air yards, catch probability, YAC, TD
   probability, turnover probability, and other conditional outcomes.
5. The sim samples from those predicted distributions and advances the game.

That is still Monte Carlo. The difference is that the simulation is no longer
mostly driven by hand-built bucket frequencies and fixed adjustment layers.

## What Should Stay

A pivot like this should preserve several things from the current repo:

- the play-by-play game loop
- the notion of explicit game state
- Monte Carlo simulation over many runs
- player-level box score accumulation
- scoring and projection aggregation
- the validation harness and A/B decision discipline
- the ability to inspect distributions instead of only point predictions
- the override system for hypothetical scenarios

Those are not accidental conveniences. They are part of the product value.

## What Should Change

Over time, the following logic should move from rules and empirical buckets
toward learned conditional models:

- play-call choice
- target selection
- ball-carrier selection
- pass depth / air yards
- catch probability
- YAC
- rushing gain distribution
- sack probability
- scramble probability
- turnover probability
- touchdown conversion behavior

Not all at once, and not in one rewrite.

## What "True ML" Means Here

For this project, "true ML" does not need to mean deep learning or a giant
black-box model.

The useful definition is:

- models are trained on historical data
- models learn conditional behavior from many features at once
- the simulator consumes those model outputs during play resolution

That could start with gradient-boosted trees, calibrated classifiers,
quantile models, mixture models, or other tabular methods. The important thing
is not the buzzword. The important thing is that the behavior is learned from
data rather than manually encoded.

## Recommended Starting Point

Recommended approach:

- do not replace the full simulator first
- do not start with a giant end-to-end player fantasy point model
- start by replacing a few high-leverage transition decisions inside the
  existing simulation

The best first candidates are:

1. play-call model
2. target / rusher selection model
3. pass outcome chain: air yards, catch, YAC

Why these first:

- they sit close to the core driver of weekly fantasy output
- they are easier to evaluate against observed football behavior
- they can improve projections without discarding the existing engine
- they let the project test the hybrid direction before committing to a full
  architectural rewrite

## Why Not Start With A Full Rewrite

A full rewrite would create too many moving parts at once:

- new model training pipelines
- new inference wiring
- new calibration problems
- new simulation drift risks
- weaker ability to isolate which changes actually helped

There is also compounding error risk. If ten learned sub-models are each a
little wrong, drives and game totals can drift in unrealistic ways.

That argues for gradual replacement of transition nodes, not a single cutover.

## Migration Philosophy

The right mental model is:

- keep the simulator as the control surface
- teach it better local decisions
- replace hand-built logic only where the learned version earns promotion

This keeps the project grounded in football structure while allowing ML to take
over the places where hand-tuned logic becomes brittle.

The simulator should become increasingly model-driven, not abruptly model-only.

## Weekly Vs Season Outlook

This approach is likely most valuable for weekly accuracy first.

Why:

- weekly outcomes are driven heavily by role, matchup, usage, and game context
- those are exactly the areas where learned conditional models can outperform
  static heuristics
- same-season drift is easier for ML to pick up than for fixed bucketed logic

Season accuracy should also improve, but mostly as a consequence of better
weekly behavior plus stronger availability and role modeling.

In other words:

- weekly is the first proof point
- season is the downstream payoff

## Ultimate End State

The long-term ideal is a simulator where:

- every major play-level decision is driven by trained models
- the simulator still enforces football structure and clock/possession flow
- outputs remain full player stat distributions, not just expected means
- scenario testing remains first-class
- model improvements can be promoted one layer at a time through the existing
  validation framework

At that point, the project is no longer "a simulator with a few adjustments."
It becomes a learned football simulation system.

## Practical North Star

If this pivot happens in the future, the north star should be:

- keep simulation
- move decision-making inside simulation toward learned models
- start with the highest-leverage transition points
- validate incrementally
- preserve interpretability and controllability

That is the version of "hybrid" most aligned with the original intent of the
project.

