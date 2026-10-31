# Plotting

The Plotting tab makes SAGE26's diagnostic plots from the open model, with
observations, and opens them over the viewer. They are saved in
`sage_library/plots/` and listed in the Library. It works on SAGE26
models, LightSAGE lightcones and DarkSAGE and DustySAGE runs.

## Choosing the galaxies

- **Galaxies:** the whole box or lightcone, the Coords sphere, the Box
  region or the selected galaxy's group.
- **Use Filters and Environments:** applies the Filters tab and the
  Environment checkboxes in the Structure tab as well, so a plot shows what
  the viewer shows.
- **Local z** (lightcones): the redshift slice for the Local and Observed
  plots.

Mass functions are per Mpc³, using the volume of the box, sphere, region or
cone. A filter picks a population in the same volume. A group has no
meaningful volume, and neither does a region of a cone, so those plots show
counts instead.

History plots follow the same selection through every snapshot: a sphere
or box stays where it is, and filters are worked out afresh each snapshot.
A group doesn't exist across snapshots, so they are unavailable for a group.

## The plots

- **Local:** one snapshot, or one slice of a cone.
- **History:** by redshift. In a lightcone, galaxies are grouped by the
  snapshot they were drawn from, and a shallow cone's redshift bins are
  fitted to its own range.
- **Observed** (lightcones with photometry): redshift distribution, number
  counts, colour-magnitude and colour-colour diagrams, luminosity functions,
  BPT and dust attenuation.

Plots a model has no fields for are greyed out.

## Options

Median and 1σ or each galaxy, colour by a property, log or linear axes, axis
limits, a dark background. Save as PNG, PDF, JPEG or SVG; a PNG is always
kept, to show. Observations are always markers, in their own legend.

Plots use SAGE26's stylesheet. With no LaTeX installed they fall back to
matplotlib's own maths and a Palatino-style font.
