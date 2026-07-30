# Installation

## Requirements

- Python >= 3.10
- A SAGE26 or SAGEswarm output directory (HDF5 format) and lhalo_binary merger trees, **or** a LightSAGE `cli_lightcone` HDF5 lightcone output

## From source (recommended until PyPI release)

```bash
git clone https://github.com/MBradley1985/ViSAGE
cd ViSAGE
pip install -e ".[dev]"
```

## Optional: synthetic photometry (SED)

The LightSAGE synthetic-photometry stage (forward-modelling AB magnitudes for
lightcone galaxies, used by [Lightcone Mode](../user_guide/lightcone.md)'s
Photometry tab) needs [FSPS](https://github.com/dfm/python-fsps) and astropy,
which are **not** installed by default:

```bash
pip install "sage-viewer[sed]"      # or, from source:  pip install -e ".[sed]"
```

`python-fsps` also requires its stellar-population data — set the `SPS_HOME`
environment variable to point at it (see the python-fsps install docs). Nothing
else in ViSAGE depends on FSPS; the viewer and every other flow run without it.

## Verifying the install

```bash
visage --version
```

## Remote / HPC installation

A helper script is included for module-system clusters (Slurm, PBS, etc.):

```bash
# Load a Python module first (name varies by cluster)
module load python/3.12.0

# Create a venv and install ViSAGE in one step
./install_hpc.sh

# Optional: place the venv on scratch for faster I/O
./install_hpc.sh /scratch/$USER/visage-env
```

The install is editable (`pip install -e .`) so `git pull` updates the code immediately with no reinstall. `ffmpeg` is checked separately — load it via your module system if you need MOV recording.

In every subsequent session:

```bash
source .venv/bin/activate
visage --par /path/to/millennium.par --port 8080
```

Then use SSH port-forwarding to view in your local browser:

```bash
# In a local terminal
ssh -L 8080:localhost:8080 user@cluster
# Open http://localhost:8080
```

## Dependencies

| Package | Purpose |
|---|---|
| pyvista | 3D rendering (VTK wrapper) |
| trame | Web UI server |
| trame-vtk | Streams PyVista render window to browser |
| trame-vuetify | Vuetify 3 UI components |
| h5py | Reads SAGE HDF5 galaxy output |
| numpy | Array operations |
| scipy | KDE density computation, KDTree navigation |
| joblib | Parallel halo file loading |
| fsps, astropy | *Optional* (`[sed]`) — synthetic photometry / SED synthesis |
