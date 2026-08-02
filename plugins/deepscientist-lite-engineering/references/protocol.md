# Engineering analysis protocol

`ds-lite.engineering-analysis.v1` records the minimum information needed to reproduce or reject a numerical analysis: backend and observed version, units, sampling, preprocessing, FFT configuration, simulation seed, mandatory physical and plotting checks, commands, artifacts, and Core Evidence Pack reference.

Python/NumPy/SciPy is the reference backend when present. MATLAB and Octave are optional, capability-discovered backends. The protocol is backend-neutral and does not deploy either environment.

For sampled signals, declared frequencies must remain below Nyquist, `duration_s` must agree with sample count and rate, and FFT bin resolution must equal `rate_hz / sample_count`. A passed label does not override an inconsistent numeric contract.
