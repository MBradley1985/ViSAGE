# Recording

The **Record** tab captures screenshots and movies directly from the viewer.

## Screenshots

| Setting | Options |
|---|---|
| Format | PNG · JPG · TIFF |
| Resolution | Native · 2× · 4× supersampled |
| Label | Optional user-typed string prepended to the filename |

Click **Take Screenshot** (or press Enter in the label field) to save. All files go into a single session folder created on app launch, shown in the status line.

## Movies

| Setting | Options |
|---|---|
| Format | GIF · MOV (H.264, requires `ffmpeg`) · PNG sequence |
| FPS | 1 – 60 |
| Resolution | Native · 2× · 4× supersampled |
| Speed | Playback speed: a preset (0.1× to 5×) or any value typed in, 0.01× to 100× |
| Rotate | Camera orbit: a preset (clockwise or anticlockwise, 15 / 30 / 60 ° s⁻¹) or any rate typed in, 0.1 to 720 ° s⁻¹ (negative or "ccw" for anticlockwise, "off" to stop) |
| Label | Optional user-typed string |

Click **Record** to start capturing frames, then **Stop** when done. The movie is assembled and saved to the session folder.

### MOV recording

MOV output requires `ffmpeg` in your `PATH`. On HPC clusters:

```bash
module load ffmpeg
```

### High-res GIFs

4× supersampling + GIF produces large files; use PNG sequence for post-processing if file size matters.

## Output folder

All screenshots and movies for a session are saved to a single folder named after the launch timestamp. The path is printed in the viewer's info bar on startup. Use the **Library** tab to browse and re-open saved files.

## Library

See [Library](library.md) for how to view, open, and manage recorded files.
