# Colour modes and colormaps

## Halo colour modes

Selectable from the Structure tab:

| Mode | Scalar | Range |
|---|---|---|
| Mvir | log₁₀(Mvir / Msun)   | 10 – 15 |
| Rvir | log₁₀(Rvir / Mpc/h)  | -1.5 – 0.5 |
| Vvir | log₁₀(Vvir / km s⁻¹) | 1.5 – 3 |

## Galaxy colour modes

| Mode | Scalar | Range |
|---|---|---|
| Stellar Mass | log₁₀(M★ / Msun)     | 8 – 12.5 |
| sSFR         | log₁₀(sSFR / yr⁻¹)   | −14 – −8 |
| SFR          | log₁₀(SFR / Msun yr⁻¹) | −3 – 2 |
| Cold Gas     | log₁₀(M_gas / Msun)  | 7 – 11.5 |
| Bulge Mass   | log₁₀(M_bulge / Msun)| 7 – 12 |
| B / T        | bulge_mass ÷ stellar_mass | 0 – 1 |
| BH Mass      | log₁₀(M_BH / Msun)   | 4 – 10 |
| ICS Mass     | log₁₀(M_ICS / Msun)  | 6 – 12 |
| Age          | mass-weighted stellar age | 0 – 14 Gyr |
| Density      | KDE local density (categorical / per-snapshot normalised) | — |
| Type         | Central (Blues cmap) / Satellite (Reds cmap) | — |
| Structure    | Multi-layer composition — see below | — |

The inline colorbar beneath each Colour-by dropdown reflects the current mode's range and the current colormap.

## Structure mode

A more physically-suggestive galaxy rendering. For each galaxy:

* a black BH core sized by `BlackHoleMass`
* a blue cold-gas envelope sized by `ColdGas`
* coolwarm-coloured "stellar particles" scattered inside the envelope; particle count scales with stellar mass
* an outer envelope coloured **green** (CGM regime) or **red** (Hot-atmosphere regime), sized by `H2gas` or `ColdGas`
* sparser coolwarm scatter through the outer envelope

All layers stay within the standard galaxy splat-radius scaling so the overall on-screen size matches the other modes.

## Colormaps

27 colormaps available in both the halo and galaxy colormap dropdowns. The **Reverse** box beside each dropdown flips the colormap (e.g. Viridis runs yellow to purple):

**Sequential**
: Viridis, Plasma, Inferno, Magma, Cividis, Turbo, Blues, Purples, Greens, Oranges, Reds, Greys, YlOrRd, YlGnBu, BuPu, Hot, Cool, Bone, Copper

**Diverging**
: Coolwarm, RdBu, Seismic, Spectral, BrBG

**Cyclic / qualitative**
: Twilight, Jet, Rainbow

## Point sizing

Splats are rendered in **world coordinates** (Mpc/h) via `vtkPointGaussianMapper`'s per-point scale array — so when the camera zooms in they grow on screen, and when it zooms out they shrink. The radii are scaled by the underlying mass:

* Haloes: 0.15 – 1.5 Mpc/h (log₁₀ Mvir 10 – 15)
* Galaxies: 0.025 – 0.35 Mpc/h (log₁₀ M★ 8 – 12.5)
