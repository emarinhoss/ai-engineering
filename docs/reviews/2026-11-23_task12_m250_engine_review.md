# Review: M250-B17F engine model (2026-11-23)

Independent, read-only review (Fable) of commit bb6b463. The reviewer's probe scripts were kept in
the session scratchpad and are not committed. `pytest tests/task12`: 254 passed, 1 xfailed.

## Verdict

The calibration, numerics, the TP100 refactor and the report numbers are correct and
reproducible:

- The TP100 table regenerates byte-identical.
- The M250 table regenerates byte-identical.
- The calibrated point is exact: SFC 0.6130000 at 810.000 C.

The table can size the pusher at Stage 1 as a candidate engine, but only with bands. The cells the
mission uses are neither validated nor inside the choked-turbine assumption. The validation covers
70-100 % power at sea level only, and there it is close to automatic.

Recommended bands at h = 1:

- **SFC:** table x 1.05 allowance, with ±10 % on top.
- **Power:** ±10 %, applied as a cap on available power, not as a rescale of the part-power
  fraction axis.

## What checks out

- **MGT = Tt4.5:** correct for the M250, whose thermocouples sit at the gas-producer turbine
  outlet. With no cooling, tau_m1 = 1 exactly.
- **Control law:** the code holds pi_c only as a ceiling. pi_c falls with Tt4 at part power (6.22,
  5.81, 5.39 and 4.78 at 450, 380, 314 and 225 shp), which is how a free-turbine gas generator
  sheds power.
- **Uniqueness:** the root is unique; SFC is monotonic in pi_c for all members.
- **Convergence:** both solves are tightly converged.
- **Flight speed:** using M0 = 0.1 instead of static is immaterial; at M0 0.02 SFC is 0.6135 and
  Tt4.5 is 810.4 C.

## Findings

| ID | Severity | Finding | Fix |
|---|---|---|---|
| M-1 | high | The mission runs in unvalidated, unchoked cells. A probe sizing (not a recorded run) at the 2026-11-21f pusher point puts loiter at 30 % of full throttle at 20,000 ft, and 73 % of mission fuel burns in unchoked cells. Below 70 % power the model's fuel-flow curvature is opposite to the brochure's. The family spread at 30 % power is 5 %. | Report the unchoked shares. Carry the SFC band. Ask for part-power or altitude fuel-flow data. |
| M-2 | high near 450 hp, low at the current point | Altitude lapse with the pi_c ceiling is 0.44-0.46 at 20,000 ft (197-207 shp). The Tt4-only limit gives 0.71-0.73, with MGT 140 C under its limit. The true lapse lies between the two, and the table is the conservative end. `engine_power_mult` rescales the fraction axis, which is not physical for a control-limit uncertainty. | Report both lapses. Band power as a cap only. |
| M-3 | medium | The SFC validation is nearly automatic once take-off SFC is calibrated. Wrong MGT calibrations, and a constant-SFC model at 380 and 377 shp, also pass ±5 %. The 380 and 377 shp points are effectively one point. The MGT drop check (model 50.6 C, brochure 58 C) and the 420-column failure do discriminate. | Reword the claim to "consistent with the brochure from 70 to 100 % power at sea level". Add the SFC ratio form (model 1.049 and 1.110, brochure 1.036 and 1.098). |
| M-4 | medium | The TP100's 1.05 SFC allowance is applied to the M250 without a ruling. The M250 is calibrated to guaranteed maxima and already reads +0.7 to +1.7 % high, so sized SFC is about 6-7 % above the guaranteed maximum. | Owner ruling needed. |
| M-5 | low | "pi_c held at its rated value" is the wrong wording; it is a ceiling. | Reword. |
| M-6 | low | The report omits: the unchoked share, the lapse, 449.8 shp at 66 kt, a deviation summary, and the consequence of the label conflict (if the 420 column is the B17F, take-off SFC is 7 % worse and validation fails). | Add these items. |
| M-7 | low | Sea-level static power is 443-447 shp, and `bsfc()` refuses exactly 450 shp below about 66 kt. No caller is affected. Take-off is 1.2-1.5 % optimistic, which is negligible here. | One report sentence. |
| M-8 | low | In the 450 column, 377 and 314 shp are 90 % and 75 % of 419 shp; in the 420 column, the cruise rows are 90 % and 75 % of its normal-cruise power, 369 shp. | Recheck the transcription. |
| M-9 | low | Tests do not cover `validate()`, the table hash, or the 420-column failure. Two docstrings are stale. | Add the tests and fix the docstrings. |

## Owner questions

1. Are the MGT values limits or measured values?
2. Please recheck the 377 and 314 shp rows (M-8).
3. Are part-power or altitude fuel-flow data available?
4. Should the 1.05 allowance apply to the M250?
5. Is there an open source for the published pressure ratio and mass flow?
6. Should power be banded as a cap?

## Coordinator notes on the questions

- **Q2:** the transcription was rechecked against the brochure's p. 4 image on 2026-11-23. The
  450 column prints 377 and 314 shp beside "Cruise A (90%)" and "Cruise B (75%)". It is the
  brochure's own data, not a transcription error.
- **Q1, partly answered:** the brochure's footnote says take-off MGT up to 810 C is permitted
  provided maximum torque is not exceeded, so 810 C is a limit. The cruise MGT values are printed
  as rating values without a footnote.
