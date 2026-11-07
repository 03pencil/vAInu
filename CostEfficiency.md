# Cost Efficiency

What vAInu saves compared with today's "run it until it breaks" approach, for one duty pump over one year. Figures come from the challenge business case (`RETROFIT_FEASIBILITY.md`, section 5) and are planning estimates on synthetic data, not a quote.

## Without vAInu

- 0.6 developing faults per year end in an unplanned stop.
- One unplanned stop costs 10 h of downtime (EUR 15,000) plus a EUR 9,000 repair.
- Expected cost: 0.6 x EUR 24,000 = **EUR 14,400 per year**.

## With vAInu

- Installation: **EUR 4,500 once**.
- About 89 % of faults are caught early, so 0.53 per year become planned repairs.
- Each early catch avoids 7 h of downtime (EUR 10,500) and EUR 5,000 of repair damage: EUR 15,500 saved.
- Saved per year: 0.53 x EUR 15,500 = **EUR 8,268**.
- False alarms: 0.071 per pump-day x 365 x EUR 120 = **EUR 3,110 per year**.
- Running costs: **EUR 700 per year**.
- Net saving: EUR 8,268 - EUR 3,110 - EUR 700 = **EUR 4,458 per year**.
- Payback: EUR 4,500 / EUR 4,458 = **about 1 year**.

## Side by side

| Cost | Without vAInu | With vAInu |
|---|---:|---:|
| Unplanned stops (downtime + repair) | EUR 14,400 | EUR 1,600 |
| Planned repairs | EUR 0 | EUR 4,533 |
| False-alarm checks | EUR 0 | EUR 3,110 |
| Running costs | EUR 0 | EUR 700 |
| **Total per year** | **EUR 14,400** | **EUR 9,943** |
| Installation (one time) | EUR 0 | EUR 4,500 |
| **First year** | **EUR 14,400** | **EUR 14,443** |
| **Five years** | **EUR 72,000** | **EUR 54,215** |

Five-year saving: **about EUR 17,800**.

## When it pays off, and when it does not

| Situation | Effect |
|---|---|
| Normal duty pump, about 0.6 faults per year | +EUR 4,458 per year, payback about 1 year |
| High downtime cost (EUR 5,000/h) | +EUR 17,526 per year, payback 0.3 year |
| Few faults (0.2 per year) | -EUR 1,054 per year, no payback |
| Noisy alerts (0.5 per pump-day) | -EUR 14,332 per year, no payback |
| Redundant pump with standby (downtime near EUR 0, 0.3 faults/year) | -EUR 2,476 per year, no payback |

## Notes

- The EUR 4,500 installation is the challenge's full retrofit figure. vAInu only taps data that already exists at the PLC, so it needs no new sensors and its own hardware is a fraction of that. The comparison is therefore conservative.
- False alarms matter: one extra alert per pump-day costs about EUR 43,800 per year in checks alone. vAInu's current false-alarm rate is still above its 2 % target, so this is the number to watch.
- All figures are planning estimates from the challenge brief. Replace the assumptions with real site data before making a purchase decision.
