# Configuration

ViSAGE reads all simulation parameters directly from the SAGE `.par` file. No separate config file is needed.

## CLI options

| Option | Default | Description |
|---|---|---|
| `--par FILE` | (required unless `--lightcone`) | Path to SAGE .par file. Omit both `--par` and `--lightcone` to start in Launch Mode |
| `--lightcone FILE` | — | Path to a `cli_lightcone` HDF5 output file — opens the full Explore UI on the lightcone instead of a SAGE box |
| `--snap N` | last snap | Initial snapshot number |
| `--port N` | 8080 | Trame server port |
| `--n-jobs N` | CPUs-1 | Parallel workers for halo loading |
| `--min-halo-mass MSUN` | 1e10 | Minimum halo mass floor (Msun) |
| `--min-stellar-mass MSUN` | 1e8 | Minimum stellar mass floor (Msun) |
| `--max-halos N` | 100000 | Downsample ceiling for haloes per snapshot |

Galaxies have no display cap — every galaxy passing the mass floor is loaded (all snapshots are preloaded, so there's no need to downsample for playback speed).

## Par file fields used

ViSAGE reads the following fields from the `.par` file:

| Field | Used for |
|---|---|
| `OutputDir` | Locating SAGE HDF5 galaxy output |
| `FileNameGalaxies` | Galaxy output file base name |
| `FirstFile` / `LastFile` | Range of tree files to read |
| `SimulationDir` | Directory containing lhalo_binary tree files |
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
