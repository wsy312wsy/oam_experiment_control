# OAM Experiment Control

Python project for automated control of OAM spectrum measurement experiments.

## Current stage

- This repository is currently in a `mock skeleton` stage.
- Real SDK integration is not implemented yet for Holoeye (SLM1) and ZKWX (SLM2).
- JAI camera has a non-GUI real capture path integrated in `controllers/camera_controller.py`
  for small-scale workflow validation.
- Future hardware integration will be connected through the `controllers/` abstraction layer.

## Run mock scan

1. Install dependencies:

```bash
pip install -r requirements.txt
```

1. Run one complete mock experiment:

```bash
python main.py
```

Running `python main.py` will:
- Load config from `OAM_CONFIG` env var, default `config/default_config.yaml`
- Read masks in `data/mock_masks/slm1` and `data/mock_masks/slm2`
- Auto-create placeholder masks if folders are empty (configurable)
- Execute nested scan loop (SLM1 outer, SLM2 inner)
- Apply timing policy: no extra wait after SLM1 switch; after each SLM2 switch, wait `scan.slm2_settle_ms` then trigger one CCD frame capture
- Save generated mock frames into `data/<run_id>/frames/`
- Write per-frame log to `data/<run_id>/scan_log.jsonl`
- Write run summary to `data/<run_id>/metadata.json`
- Write runtime log to `logs/<run_id>.log`

## Camera mode

- Default mode is `camera.mode: mock` (fully runnable).
- `camera.mode: real` uses JAI/eBUS non-GUI capture path (requires eBUS SDK + device).
- Small-scale real-camera config example: `config/real_jai_small_scan.yaml`
- Integration notes and boundaries: `docs/real_camera_integration.md`.

## Dual-SLM Display Calibration

Use the standalone calibration tool to bind `SLM1`/`SLM2` to fixed monitor ids
and avoid cross-screen output:

```bash
python tools/slm_display_calibration.py
```

What it does:
- Enumerates current monitors (`monitor_id`, resolution, position, primary flag)
- Shows high-contrast fullscreen test patterns on two candidate screens
- Lets you manually enter which `monitor_id` is `SLM1` and which is `SLM2`
- Saves mapping to `config/slm_display_mapping.yaml`

Quick verify mode (reuse saved mapping):

```bash
python tools/slm_display_calibration.py --verify
```

Mapping file fields:
- `slm1_monitor_id`
- `slm2_monitor_id`
- `calibration_time`
- `monitor_summary`

Controllers `SLM1Controller` and `SLM2Controller` load this file on `connect()`
as the fixed display-binding basis for future real SDK display output.

Run small real-camera scan from main workflow:

```bash
$env:OAM_CONFIG="config/real_jai_small_scan.yaml"
python main.py
```

Quick config tips:
- Use JAI real camera: set `camera.mode: "real"` in your config file.
- Timing parameter: set `scan.slm2_settle_ms` (current conservative default `300` ms).
- Change exposure: edit `camera.exposure_us`.
- Change save location: edit `paths.data_root`.
- Change ROI:
  - size: `camera.width`, `camera.height`
  - offset: `camera.offset_x`, `camera.offset_y`
- Width/height rule:
  - `camera.mode: mock`: `camera.width` and `camera.height` are required and must be `> 0`
  - `camera.mode: real`: width/height can be `null` in current stage; device-side current/default values are used

## Output layout

Example run directory:

```text
data/
  oam_mock_scan_YYYYMMDD_HHMMSS/
    frames/
      slm1_mask_001/
        f00001_s1_slm1_mask_001_s2_slm2_mask_001.png
        ...
      slm1_mask_002/
      slm1_mask_003/
    scan_log.jsonl
    metadata.json
```

Frame filename format:
- `f{frame_index:05d}_s1_{slm1_stem}_s2_{slm2_stem}.{save_format}`

`scan_log.jsonl` format:
- One JSON object per line
- Fixed fields:
  - `timestamp`
  - `slm1_mask`
  - `slm2_mask`
  - `image_path`
  - `success`
  - `error_message`
  - `elapsed_ms`

`metadata.json` fields:
- `run_id`
- `experiment_name`
- `output_dir`
- `slm1_mask_dir`
- `slm2_mask_dir`
- `slm1_mask_count`
- `slm2_mask_count`
- `camera_mode`
- `save_format`
- `start_time`
- `end_time`
- `total_frames`
- `status`

## Project structure

- `controllers/`: device abstraction and mock/real controller implementations
- `core/`: config, runner, logger, data management
- `processing/`: OAM processing placeholders for later stages
- `config/`: default configuration files
- `utils/`: filesystem, naming, timing helpers

## Vendor SDK folders

`holoeye/` and `ZKWX_python_VS2015_x64/` are kept as local vendor resources.
Current mock skeleton does not depend on their internal binary/runtime layout.
