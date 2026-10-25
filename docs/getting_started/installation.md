# Installation

## Requirements

- Python >= 3.11, on macOS, Linux or Windows
- A SAGE26 or SAGEswarm output directory (HDF5 format) and merger trees (lhalo_binary or lhalo_hdf5), **or** a LightSAGE `cli_lightcone` HDF5 lightcone output

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

`python-fsps` also requires its stellar-population data, found through the
`SPS_HOME` environment variable (see the python-fsps install docs).

**Launch Mode does all of this for you:** LightSAGE's **Install** button
installs `fsps` and `astropy` into ViSAGE's Python and, when `SPS_HOME` isn't
set, downloads the FSPS stellar libraries (about 1 GB) into `~/.visage/fsps`,
which ViSAGE then uses without `SPS_HOME`. Nothing else in ViSAGE depends on
FSPS; the viewer and every other flow run without it.

## Verifying the install

```bash
visage --version
```

## Windows

```powershell
py -m pip install sage-viewer
visage
```

The viewer runs natively on Windows: Explore and Lightcone modes, Story Mode,
recording (a bundled ffmpeg is installed for MOV output), and the Console,
which opens PowerShell.

The [Launch Mode](../user_guide/launch_mode.md) flows, SAGE26, SAGEswarm and
LightSAGE, compile and run Unix C/C++ code (make/CMake, MPI, HDF5, GSL,
Boost, bash scripts) that does not build with Windows compilers. On Windows,
ViSAGE runs those tools inside **WSL** (Windows Subsystem for Linux)
automatically. The checkouts stay on your Windows drive, so
`C:\Users\you\SAGE26` is `/mnt/c/Users/you/SAGE26` inside WSL, and the
native viewer reads SAGE's output directly. One-time setup:

1. In an **administrator** PowerShell, run `wsl --install`, then restart Windows.
2. Open the new **Ubuntu** app once and create a Linux user name and password.
3. Run `visage`; if Linux build tools are missing, the home page offers
   **Install Linux build tools**. This runs `apt-get` inside WSL (as root, so
   there is no password prompt) to install the compilers and libraries all
   three tools need.

Notes:

- Clone the tools from Launch Mode rather than with Git for Windows.
  Git for Windows converts the bash scripts to Windows line endings, which
  bash cannot run. Launch Mode warns you if it finds a checkout like that.
- WSL gets half of the machine's RAM by default. For large SAGEswarm runs,
  raise it with a `memory=` line in `%UserProfile%\.wslconfig`.
- Alternatively, install and run ViSAGE entirely inside WSL. It then behaves
  exactly as on Linux, and your Windows browser reaches
  `http://localhost:8080` as usual.

### If the view feels slow on Windows

ViSAGE renders every frame on the server, JPEG-encodes it and streams it to
the browser. At startup on Windows it prints
`Tuning : 1 ms timer resolution, power throttling off`. Those two settings
stop Windows from delaying the frame loop. If the view still lags:

- Run `visage --perf` and move the camera. Each line splits a frame into
  `render` (GPU drawing), `frame` (render + readback + JPEG encode) and
  `between` (input handling, sending, waiting for the next frame), with the
  frame rate and size. A `frame` time well above `render` means the
  CPU-side encode is the cost. A large `between` means something else
  (background loading, the network, the browser) is the bottleneck.
- Check that the `GPU :` line names your discrete card. If it doesn't,
  restart ViSAGE once after the first launch sets the graphics preference.
- On a laptop, plug in and choose **Best performance** in Windows power
  settings. On battery, Windows lowers CPU clocks, which slows encoding.
- A smaller browser window means smaller frames and higher frame rates.
- Run `visage --diagnose --par your.par` and send the
  `visage_diagnostics.txt` it writes. It checks the GPU, times each step
  of a frame, and opens ViSAGE in your browser to measure whether the
  browser keeps up while the view turns and while you drag it.
- On Windows frames are JPEG quality 95 (100 elsewhere).
  `VISAGE_JPEG_QUALITY` (50–100) sets it:
  lower sends smaller frames, for a slow link or browser.

## Hardware detection

ViSAGE sizes itself to the machine on every platform, and prints what it
found at startup:

```text
System   : Windows 11 (AMD64) · 16 CPUs (15 workers) · 31.8 GB RAM (cache 15.9 GB)
GPU      : NVIDIA GeForce RTX 4060 Laptop GPU/PCIe/SSE2 (OpenGL 4.6.0)
```

- **CPUs:** halo loading uses every CPU this process may run on, minus one.
  On a cluster that means the job's allocation, not the whole node.
- **Memory:** the snapshot cache defaults to half of physical RAM, or half of
  an HPC job's / container's memory limit when that is smaller.
- **GPU:** the line above names the GPU that actually renders. If OpenGL has
  fallen back to the CPU (Remote Desktop, a virtual machine, a missing
  driver), the viewer shows a warning. On a Windows laptop with integrated
  and discrete graphics, ViSAGE sets the Windows "High performance" graphics
  preference for Python so the discrete GPU renders. See `--gpu` under
  [Configuration](configuration.md).

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
| pywinpty | *Windows only* — real terminal for Launch Mode and the Console |
| imageio-ffmpeg | *Windows only* — bundled ffmpeg for MOV recording |
| fsps, astropy | *Optional* (`[sed]`) — synthetic photometry / SED synthesis |
