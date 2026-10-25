# Configuration

ViSAGE reads all simulation parameters directly from the SAGE `.par` file. No separate config file is needed.

## CLI options

| Option | Default | Description |
|---|---|---|
| `--par FILE` | (required unless `--lightcone`) | Path to SAGE .par file. Omit both `--par` and `--lightcone` to start in Launch Mode |
| `--lightcone FILE` | — | Path to a `cli_lightcone` HDF5 output file — opens the full Explore UI on the lightcone instead of a SAGE box |
| `--snap N` | last snap | Initial snapshot number |
| `--port N` | 8080 | Trame server port |
| `--n-jobs N` | usable CPUs − 1 | Parallel workers for halo loading (respects a cluster job's CPU allocation) |
| `--cache-gb GB` | half of RAM | Snapshot cache budget; half of physical RAM, or of an HPC job's memory limit. Also `VISAGE_CACHE_GB` |
| `--perf` | off | Print frame timing (fps, render / encode / between ms, frame size) every few seconds while the view moves. Also `VISAGE_PERF=1` |
| `--gpu MODE` | `auto` | Which GPU renders: `auto` prefers the discrete GPU on a Windows laptop with hybrid graphics; `high` / `low` force the discrete / integrated GPU; `system` leaves the OS default. Also `VISAGE_GPU` |
| `--min-particles N` | 20 (the setup screens' choice) | Resolution: haloes with at least N dark-matter particles are kept, and galaxies from the stellar mass where 90% of centrals live in such haloes, worked out per snapshot (per redshift shell in a lightcone) |
| `--min-halo-mass MSUN` | — | A fixed halo mass floor (Msun), instead of `--min-particles` |
| `--min-stellar-mass MSUN` | — | A fixed stellar mass floor (Msun), instead of `--min-particles` |
| `--max-halos N` | 100000 | Downsample ceiling for haloes per snapshot |

The mass cuts follow the simulation's resolution (its particle mass) rather than one number for every run. The particles a resolved halo needs (20, 50 or 100; default 20) are chosen under **Resolved haloes** on the SAGE26 and LightSAGE setup screens, and kept for every model opened afterwards.

Galaxies have no display cap — every galaxy passing the mass floor is loaded (all snapshots are preloaded, so there's no need to downsample for playback speed).

## Par file fields used

ViSAGE reads the following fields from the `.par` file:

| Field | Used for |
|---|---|
| `OutputDir` | Locating SAGE HDF5 galaxy output |
| `FileNameGalaxies` | Galaxy output file base name |
| `FirstFile` / `LastFile` | Range of tree files to read |
| `SimulationDir` | Directory containing the merger tree files (lhalo_binary or lhalo_hdf5) |
| `TreeName` | Base name of tree files (e.g. `trees_063`) |
| `FileWithSnapList` | Scale factor list file |
| `LastSnapShotNr` | Number of snapshots |
| `Hubble_h` | Unit conversion |
| `BoxSize` | Camera framing and zoom-to-box |

## Performance tuning

For interactive use on a laptop with miniMillennium:

```bash
visage --par input/millennium.par \
  --max-halos 30000 \
  --min-halo-mass 1e11 \
  --n-jobs 4
```

For cluster use with full data:

```bash
visage --par input/millennium.par \
  --max-halos 100000 \
  --n-jobs 16 \
  --port 8080
```
