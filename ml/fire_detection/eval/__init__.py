"""wildfire-watch fire/smoke detector evaluation package.

Modules:
    prep_datasets  — download + verify FASDD, FLAME-2, D-Fire.
    eval_harness   — given a checkpoint + dataset, compute mAP / precision / recall / latency.
    latency_bench  — measure inference latency on Mac CPU; estimate Jetson FP16 latency.

All modules lazy-import heavy deps (ultralytics, requests, yaml). Tests run
without them via stub mode.
"""
