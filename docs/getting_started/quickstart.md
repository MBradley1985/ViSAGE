# Quickstart

## Three ways to launch

**Explore Mode** — view existing SAGE26 results using a full path to your `.par` file:

```bash
visage --par /path/to/SAGE26/input/millennium.par
```

**Launch Mode** (wizard) — configure and run SAGE26, calibrate with SAGEswarm, or extract a lightcone with LightSAGE. Run from your SAGE26 root so the wizard can find your `.par` files and executable automatically:

```bash
cd /path/to/SAGE26
visage
```

**Lightcone Mode** — view a LightSAGE `cli_lightcone` HDF5 output (produced by the wizard's LightSAGE flow, or from a manual run):

```bash
visage --lightcone /path/to/lightcone.h5
```

See the [Launch Mode](../user_guide/launch_mode.md) and [Lightcone Mode](../user_guide/lightcone.md) guides for details.

## Explore Mode examples

### miniMillennium

Open the printed URL (default `http://localhost:8080`) in any browser.

## Launch on microUchuu

```bash
visage --par input/microuchuu.par --snap 49
```

## Common options

```bash
# Start at a specific snapshot
visage --par input/millennium.par --snap 32

# Use a specific port
visage --par input/millennium.par --port 8888

# Limit haloes per snapshot (faster on slower machines)
visage --par input/millennium.par --max-halos 20000

# Use all CPUs for loading
visage --par input/millennium.par --n-jobs -1
```

## First steps in the viewer

1. The scene loads at the requested snapshot (default: z=0, snap 63).
2. Use the **timeline slider** in the toolbar to jump to any snapshot.
3. Press **▶ Play** to animate through cosmic time.
4. Toggle **Dark Matter Haloes** or **Galaxies** off in the **Structure** tab (right panel).
5. Change **Colour by** to `ssfr` to highlight star-forming galaxies.
6. In the **Target** tab, enter a halo index and press **Go** to fly there.
7. **Double-click** any point in the scene to select the nearest galaxy and see its properties in the info bar.
