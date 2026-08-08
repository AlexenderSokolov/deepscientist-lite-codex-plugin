---
name: ds-lite-engineering
description: Specify, run, or audit a bounded engineering analysis in Python, MATLAB, or Octave. Use for numerical analysis, FFT and signal processing, sampled time series, simulations, scientific plots, units, frequency resolution, windowing, scaling, aliasing, leakage, random seeds, and figure-axis validation. Do not assume MATLAB or Octave is installed and never invent physical parameters, material constants, or experimental measurements.
---

# DS Lite Engineering

Use this pack only with a DeepScientist Lite Core that satisfies this package's `compatibility.json`. Run `python <engineering-plugin>/scripts/ds_lite_engineering.py doctor --core-root <core-plugin>` before acting. Missing or incompatible Core is `blocked`.

## Route

1. Read the Core work unit, Graph, authorization, and Evidence Pack boundary.
2. Discover the actual backend. Python/NumPy/SciPy is the reference when observed. MATLAB and Octave remain `not-observed` until their executable and version are checked; this pack never installs them.
3. Before execution, state physical units, dimensions, sampling rate and duration, preprocessing, window, FFT resolution and scaling, simulation seed, command, and expected artifacts.
4. Execute one bounded analysis. Never fill missing physical parameters, material constants, boundary conditions, or measurements with plausible values.
5. Validate `ds-lite.engineering-analysis.v1`. Unit, dimension, aliasing, leakage, and figure-axis checks are mandatory. A simulation using randomness requires a seed.
6. Link the result to a Core Evidence Pack and stop at a checkpoint with unverified items and one next action.

For FFT work, check `resolution_hz = rate_hz / sample_count`, the Nyquist limit, window-dependent leakage, amplitude or power scaling, and axis units. Load [protocol.md](../../references/protocol.md) for the exact envelope.
