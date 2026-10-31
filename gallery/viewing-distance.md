# 14-inch / 10-foot viewing assessment

Assumptions: full-screen 1920 × 1200, 16:10 active panel, 14-inch diagonal, no overscan, viewing distance 10 feet (3,048 mm). The active area is approximately 301.6 × 188.5 mm: each pixel is 0.1571 mm. These are calculated dimensions, not a physical viewing test. Measurements below use actual rendered glyph ink in `DejaVuSans.ttf`, rather than treating font em size as letter height.

| Element | Font px before → after | Ink height px | Physical height mm | Angular height arcminutes |
| --- | --- | --- | --- | --- |
| Forecast time | 30 → 72 | 22 → 54 | 3.5 → 8.5 | 3.9 → 9.6 |
| Forecast temperature | 60 → 112 | 45 → 84 | 7.1 → 13.2 | 8.0 → 14.9 |
| Rain probability | 27 → 48 | 21 → 37 | 3.3 → 5.8 | 3.7 → 6.6 |
| Detailed metric value | 34 → 48 | 33 → 46 | 5.2 → 7.2 | 5.8 → 8.1 |
| Update / warning text | 23 → 44 | 17 → 33 | 2.7 → 5.2 | 3.0 → 5.8 |

Forecast icon boxes grow from 95 px (14.9 mm) to 180 px (28.3 mm) in minimal and 160 px (25.1 mm) in detailed. The drawing occupies part of each box. Main temperature stays at 235 px; it remains the dominant element. Forecast times grow 2.4× in nominal type size and temperatures 1.87×. Four columns are retained.

## What this means from the sofa

The main temperature, four future temperatures, times and icons are the primary two-to-three-second reading target. Their physical size is substantially larger in both layouts. Repeated condition sentences and low-risk precipitation labels are removed. Precipitation probability appears at 20% or above, or for a wet/snow/storm weather code even below 20%. Detailed pressure is omitted so four useful metrics can have larger values. Wind/gust/rain/humidity labels and values remain secondary; they are smaller than the forecast and may still require more attention or a closer view. Source attribution intentionally remains close-reading text. The offline/stale message is larger, with a 36 px red dot instead of 24 px.

This assessment does not guarantee comfortable reading for every viewer: eyesight, panel contrast, glare and room lighting matter. A large PNG or contact sheet on a computer monitor cannot establish ten-foot readability. The numeric comparison supports a material improvement; confirm it on the actual 14-inch frame before treating sofa-distance readability as verified.

## Equivalent-angle review before updating the Pi

At 60 cm viewing distance, display a complete card at **59.4 mm wide** (measure the image with a ruler; browser zoom and CSS millimetres are not reliable physical calibration). This approximates the angular size of a 301.6 mm-wide frame at ten feet. Compare full-resolution before/after files at exactly the same measured width. This is an angular-size check, not a substitute for the Pi's panel and lighting. For the final manual test, stand ten feet away and try to read the four times and temperatures in two or three seconds, then check the warning and wet-hour probabilities. No deployment is performed by this generator.

## Geometry verification

Tests record measured text-ink rectangles and conservative icon boxes. They check canvas boundaries, four-column boundaries and pairwise overlap across all ten themes, both layouts, supported extremes, long locations, clock-change labels, offline/stale/expired cards and shortened/exhausted forecasts. DejaVu Sans and the Pillow fallback are checked when the configured test font is available. Custom fonts can have different metrics; unusually wide strings are fitted to their region. Geometry checks do not assess eyesight or aesthetic quality.
