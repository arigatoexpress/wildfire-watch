# Hardware BOM — MVP unit

## Decision log (top of file, read first)

| Decision | Choice | Rejected | Reasoning |
|---|---|---|---|
| Frame | Holybro X500 V2 (semi-printed: arms / pods printable, carbon center plate stock) | Fully-printed Open Drone, Agilicious | X500 V2 is a known-good ArduPilot/PX4 reference frame with 1.5 kg payload, 18-min stock hover, and CAD modifications welcome. Fully-printed loses thrust-to-weight margin once we add Jetson + cameras. |
| Flight controller | Cube Orange+ (Hex/ProfiCNC) on Carrier Standard | Pixhawk 6X, Pixhawk 6C | Cube Orange+ has triple-redundant IMUs, robust ArduPilot Copter 4.6 support, and proven public-safety deployment. Worth the $100 premium over 6X. |
| Edge compute | Jetson Orin Nano Super 8 GB Dev Kit | Raspberry Pi 5 + Hailo-8L AI HAT, OAK-D Lite | Orin Nano Super: 67 TOPS, full CUDA + TensorRT, MegaDetector v6 + YOLOv8 + BirdNET all fit. Pi 5 + Hailo-8L is 13 TOPS and forces rewrites for HailoRT compiler — nice for power but loses ML headroom. See ADR-0001. |
| RGB camera | Arducam IMX477 (12 MP, MIPI-CSI to Jetson) | Raspberry Pi HQ Cam | IMX477 sensor identical, Arducam carrier has the right ribbon for Jetson camera connector. |
| Thermal | FLIR Lepton 3.5 + PureThermal 3 USB carrier | Lepton XDS (new 2026 dual-spectrum), Boson 320 | Lepton 3.5 + PT3 is well-documented, $250 bundle, radiometric, fits 25 g payload budget. Boson is overkill ($1.5k+). Lepton XDS is appealing but new, less community support. |
| ITAR / NDAA | All NDAA-compliant components; non-DJI | DJI Mavic 3 Thermal | Public-safety procurement (CAL FIRE, county FDs) increasingly requires NDAA Section 848 compliance. Building NDAA-compliant from day one. |
| ESCs | Holybro BLHeli_S 20A (kit-included) | T-Motor F45A Pro II | Stock kit ESCs are sufficient for sub-2 kg AUW; upgrade only if endurance test demands. |
| Battery | 4S 8000 mAh Li-Ion (Tattu) | 4S 5200 mAh LiPo | Li-Ion gives ~30% more endurance at penalty of slower discharge curve — fine for cruise, fire-spotting profile is not aerobatic. Target 35-40 min hover. |
| Telemetry | Holybro SiK 915 MHz radio + LTE modem (Quectel EC25) on Jetson | LoRa-only | Need LTE for video uplink; LoRa as redundant link for control + low-rate signals. |

## Total estimated cost: **$2,415 USD** (single MVP unit, before tax/shipping)

See [`hardware/bom.csv`](../hardware/bom.csv) for machine-readable line items with vendor links.

## Bill of materials (summary)

| Category | Item | Vendor | Unit $ | Qty | Subtotal |
|---|---|---|---:|---:|---:|
| Frame | Holybro X500 V2 ARF Kit (Pixhawk 6C version, used as kit-only — controller swapped) | Holybro | 380 | 1 | 380 |
| FC | Cube Orange+ (with Carrier Standard) | Hex/ProfiCNC | 350 | 1 | 350 |
| GPS | Holybro H-RTK F9P Helical (centimeter-grade RTK GPS) | Holybro | 270 | 1 | 270 |
| Telemetry | Holybro SiK Telemetry Radio V3 915 MHz | Holybro | 80 | 1 | 80 |
| Compute | Jetson Orin Nano Super 8 GB Dev Kit | NVIDIA | 249 | 1 | 249 |
| Compute pwr | Pololu 5 V 5 A step-down regulator | Pololu | 18 | 1 | 18 |
| Storage | Samsung 990 EVO 500 GB NVMe (for Jetson) | Samsung | 55 | 1 | 55 |
| Camera RGB | Arducam IMX477 12 MP MIPI-CSI (Jetson kit) | Arducam | 75 | 1 | 75 |
| Camera thermal | FLIR Lepton 3.5 + PureThermal 3 carrier | GroupGets | 250 | 1 | 250 |
| Audio | Adafruit I2S MEMS mic SPH0645 + windscreen | Adafruit | 12 | 1 | 12 |
| LTE | Quectel EC25-AF mini-PCIe + Sixfab Jetson HAT | Sixfab | 220 | 1 | 220 |
| ADS-B | uAvionix pingRX Pro receiver | uAvionix | 245 | 1 | 245 |
| Remote ID | uAvionix pingRID broadcast module | uAvionix | 90 | 1 | 90 |
| Battery | Tattu 4S 8000 mAh Li-Ion XT60 | GensTattu | 95 | 1 | 95 |
| Charger | ISDT Q8 500 W charger | ISDT | 120 | 1 | 120 |
| Misc | XT60 + 12 AWG silicone wire + heat shrink + zip ties | various | 30 | 1 | 30 |
| Print filament | PETG-CF (1 kg) for arm covers, Jetson pod, camera gimbal | Polymaker | 45 | 1 | 45 |
| **TOTAL** | | | | | **$2,584** |

## Variance vs. $2,500 target

$84 over. Three knobs to bring under $2,500:

1. Drop Cube Orange+ → Pixhawk 6X (-$100, lose triple-IMU redundancy).
2. Drop H-RTK F9P → ublox M10 GPS (-$200, lose RTK precision; fine for fire-spotting,
   not for ortho-mapping).
3. Drop Tattu Li-Ion → CNHL 4S 5200 LiPo (-$45, lose ~30% endurance).

Recommendation: **stay $84 over** for the MVP. Triple-IMU is non-negotiable for
public-safety deployment, RTK gets you sub-meter geo-tagging on smoke evidence,
endurance is the whole product.

## Printable parts list

All printable in PETG-CF or PA-CF (carbon-fiber-reinforced nylon for high-stress).
Source files: link out to Onshape doc (TBD when CAD started; placeholder `hardware/cad/`).

| Part | Material | Print time (Bambu X1C, 0.2 mm) | Notes |
|---|---|---|---|
| Jetson pod (heat-sinked, vented) | PA-CF | 4 h | Mount to top plate via M3 standoffs; integrate 25×25 mm fan |
| Camera gimbal cradle (RGB + Lepton coaxial) | PETG-CF | 2 h | Single-axis stabilization; servo-driven |
| LTE/ADS-B antenna mast (rear pod) | PETG | 1 h | Keeps antennas 200 mm from carbon plate |
| Battery tray retention | PETG-CF | 1 h | Velcro + M3 lock |
| Landing skid feet (×4) | TPU 95A | 1 h | Energy-absorbing impact ends |

## Assembly time

First build: ~12 h (frame 4 h, electronics 4 h, calibration 4 h).
Subsequent units: ~6 h.

## Where the BOM is conservative

- **Battery**: 8000 mAh Li-Ion is heavy. If endurance testing shows we hit 25 min
  reliably, drop to 5200 mAh LiPo and save 200 g.
- **RTK GPS**: only needed if we publish geo-tagged ecology data with sub-meter
  precision. For fire-spotting alone, M10 GPS is fine.
- **ADS-B In**: required for BVLOS waiver, optional for VLOS-only ops. Skip on
  Phase-1 VLOS-only flights.

## Where the BOM is aggressive

- **Compute**: 8 GB Orin Nano Super assumes we ship the YOLOv8n-fire +
  MegaDetector v6 Compact + BirdNET-Lite ensemble simultaneously. If we drop
  wildlife ID from MVP, a 4 GB Orin Nano ($199) suffices.
- **NVMe**: 500 GB is a flight-data-recorder buffer. 256 GB is enough for 50
  flights of full RGB+thermal capture before mandatory upload.
