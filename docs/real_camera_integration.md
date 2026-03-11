## Real JAI Camera Integration

This document defines how real JAI camera support should be integrated into
`controllers/camera_controller.py` without bringing GUI logic from the old project.

### Scope

Allowed reference sources (in priority order):
1. `jai_sp20000_project/test_jai_minimal.py`
2. `jai_sp20000_project/camera_sdk.py`
3. `jai_sp20000_project/frame_packet.py`
4. `jai_sp20000_project/save_worker.py` (save/format logic only)

Out of scope:
- GUI window logic
- button callback wiring
- status bar update routines
- precheck subprocess orchestration

### Current Status

`CameraController` now implements a non-GUI JAI/eBUS capture chain:
- device discovery (`list_devices`)
- connect + stream/pipeline open (`connect`)
- parameter apply (`configure`)
- start/stop acquisition (`start_acquisition` / `stop_acquisition`)
- single frame capture to PIL image (`capture_frame`)
- safe close (`disconnect`)

SLM remains mock in this phase.

### Planned Implementation Order

1. Device discovery + open:
- map from `test_jai_minimal.py` and `camera_sdk.py`:
  - load eBUS module
  - find devices
  - connect by `device_id` or first available
  - open stream/pipeline

2. Parameter apply:
- map from `camera_sdk.py`:
  - width/height/offset
  - pixel format
  - exposure/gain
  - node range validation and error propagation

3. One-frame capture:
- map from `test_jai_minimal.py` and `_EBUSBridge.grab_mono8_frame`:
  - start stream/acquisition
  - retrieve next buffer with timeout
  - extract image bytes and convert to numpy
  - convert numpy -> PIL (`CameraController.numpy_to_pil`)

4. Safe close:
- map from `camera_sdk.py`:
  - acquisition stop
  - stream disable
  - pipeline stop
  - stream/device disconnect

### Image Format Handling

`CameraController.numpy_to_pil` mirrors old `save_worker.py` logic:
- `uint8` -> PIL mode `L`
- `uint16` -> PIL mode `I;16`
- fallback by value range for non-standard dtype

This keeps save behavior stable for future PNG/TIFF/NPY paths.

### Main Workflow Integration

Use:
- `camera.mode: real`
- `mode: mock` (SLM still mock)
- scan limits for small-scale validation:
  - `scan.max_slm1_masks: 1`
  - `scan.max_slm2_masks: 2`

Reference config: `config/real_jai_small_scan.yaml`.
