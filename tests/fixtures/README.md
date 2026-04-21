# Test Fixtures

This directory is created on-demand by test fixtures. Video fixtures are **not committed**
(`.gitignore` excludes `*.mp4`, `*.mov`, `*.m4v`, `*.webm`).

## Generating CI fixtures locally

The test suite generates synthetic fixtures on first run using ffmpeg. The commands below are
idempotent — they only run if the target file does not already exist:

```bash
# CFR 1fps baseline (30 seconds, 320x240)
ffmpeg -y -f lavfi -i testsrc=duration=30:size=320x240:rate=1 \
  -c:v libx264 -pix_fmt yuv420p tests/fixtures/cfr_baseline.mp4

# Synthetic VFR fixture (variable timestamps, 30 seconds)
ffmpeg -y -f lavfi -i testsrc=duration=30:size=320x240:rate=30 \
  -vf "settb=AVTB,setpts=if(lt(N\,30)\,N/3\,if(lt(N\,60)\,N/10\,N/30))/TB" \
  -fps_mode vfr -c:v libx264 -pix_fmt yuv420p tests/fixtures/vfr_synthetic.mp4

# iPhone HEVC VFR fixture (ideally, commit path for real; otherwise synthesize)
ffmpeg -y -f lavfi -i testsrc=duration=30:size=320x240:rate=30 \
  -vf "settb=AVTB,setpts=N/30/TB" -fps_mode vfr \
  -c:v libx265 -tag:v hvc1 -pix_fmt yuv420p tests/fixtures/iphone_hevc_vfr.mov
```

If a real iPhone HEVC clip is available locally, drop it at `tests/fixtures/iphone_hevc_vfr.mov`
and the fixture will skip regeneration. See Plan 05 for the INGEST-04 ±2s tolerance test.
