# Icon sources

`touch-icon-celtic.svg` is the canonical vector source for Ordinarium's
favicon, Apple touch icons, and web app icons. It uses the same B2 Celtic-cross
geometry as Occasional Prayers, with the palette roles inverted. A solid
midpoint burgundy (`#76323f`) is applied to the cross and ring over a warm-tan
vertical gradient (`#e0c5ab` to `#b69c83`). The tan stops reproduce the
original burgundy background gradient's perceptual lightness range around the
existing warm tan (`#cdb298`).

`coda-celtic.svg` is the neutral transparent footer variant. It intentionally
retains the same 10% black treatment used on Occasional Prayers so it works on
the site's light and dark page backgrounds.

`icon-celtic.html` renders every PNG directly from the same vector geometry at
its final dimensions. The checked-in PNGs live in `ordinarium/static/images/`.
The `favicon.ico` in that directory contains independent 16, 32, and 48 pixel
renders of `touch-icon-celtic.svg`; it is not produced by resizing another PNG.
