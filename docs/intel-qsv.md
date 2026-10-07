# Intel Quick Sync: Docker and TrueNAS

## Problem and evidence

The reported system is an Intel N150 running the downloader in a TrueNAS
Docker app. The app user can access the passed-through GPU: renderD128 has
GID 107, and the user belongs to that group. GPU passthrough therefore does
not need to be replaced with privileged mode.

The first failure was `Error creating a MFX session: -9` (MFX_ERR_NOT_FOUND).
The container had libvpl (the dispatcher) but neither the Intel GPU runtime
(libmfx-gen) nor the iHD media driver. A compiled-in h264_qsv encoder does not
prove that its runtime dependencies or the GPU are available.

After installing the runtime and free driver, libva loaded iHD successfully,
but encoding failed with unsupported parameters. These messages do not prove
that every listed input property is invalid. The free-kernel media driver has
fewer encoding features than Intel's full-feature build. Installing that build
is the next corrective step; success still needs verification on the N150.

## Changes and reasons

- **Dockerfile:** Use Debian trixie explicitly so package names and source format
  match the diagnosed Debian 13 environment. Enable the `non-free` component,
  then install `intel-media-va-driver-non-free` (full-feature iHD),
  `libmfx-gen1.2` (Intel VPL GPU implementation), and `vainfo` (capability probe).
  Install these only on amd64 because this Intel runtime is architecture-specific.
  Install at image build time: the application runs unprivileged, and runtime
  package installs disappear when TrueNAS recreates the container.
- **FFmpeg command configuration:** Apply QSV defaults in the shared runner so
  remote streams, downloaded HLS segments, and video-only paths behave alike.
  Request NV12 software frames for compatible 8-bit encoding input. Set
  `global_quality=23` explicitly rather than relying on FFmpeg's default CQP.
  This is an initial quality choice, not a measured optimum for every source.
  Existing pixel format/filter and quality/bitrate options take precedence.
  Copy, CPU, NVIDIA, and AMD commands are unaffected.
- **Device selection:** An optional `ANIWORLD_QSV_DEVICE` initializes QSV with
  the selected Linux render node. It avoids ambiguous selection on multi-GPU
  hosts. If unset, FFmpeg retains automatic selection. Nothing assumes that
  renderD128 is always Intel on every host.
- **Compose and README:** Document GPU devices, numeric supplemental groups,
  QSV codec selection, and deployment of the fork's image. The sample still
  defaults to upstream: a local code patch does not modify an upstream image.
- **Decoding:** Keep software decoding for provider compatibility. Hardware
  decoding is a separate optimization and is not necessary to fix the failed
  encoder initialization. Do not enable it indiscriminately for unknown inputs.

No host driver, kernel, firmware, or TrueNAS app setting is changed by this patch.
The container depends on the host exposing a usable Intel GPU. Firmware-dependent
rate-control modes can still require host-side configuration.

## Deployment

Build the updated Dockerfile (for example `docker build -t aniworld-qsv:local .`)
and deploy that image through your existing TrueNAS image registry workflow.
A pull of the unchanged upstream image will not include this patch. Preserve
existing download/config volumes when replacing the app container.

Keep GPU allocation enabled. Keep the video/render supplemental GIDs from
`ls -ln /dev/dri`, rather than copying IDs from another host. Set:

```text
ANIWORLD_VIDEO_CODEC=h264_qsv
ANIWORLD_QSV_DEVICE=/dev/dri/renderD128
```

The device variable is optional; adjust it to the actual Intel node. Do not use
av1_qsv without checking that the GPU exposes AV1 encoding.

## Verification in the deployed container

Run as the normal application user, not root:

```sh
id
ls -ln /dev/dri
vainfo --display drm --device /dev/dri/renderD128
ffmpeg -hide_banner -f lavfi -i testsrc2=size=1280x720:rate=30 -t 3 \
  -vf format=nv12 -c:v h264_qsv -global_quality 23 -f null -
```

Look for an H.264 encode entrypoint (EncSlice or EncSliceLP) in vainfo.
The generated-source FFmpeg test removes the provider and network from the
experiment. If it succeeds, test an actual downloader job. If it fails, preserve
the complete FFmpeg output and vainfo capabilities before changing bitrate,
low-power mode, or host firmware settings. A generated-source success alone
does not guarantee support for every provider's source format.

## Local validation and limits

`python3 tests/test_qsv_args.py` checks that all QSV encoders receive defaults,
explicit options are preserved, device initialization precedes inputs, and
other encoders are unchanged. Python syntax and `git diff --check` were checked.
The full pytest suite cannot run in the current environment without missing
application/test dependencies. Docker daemon access and an Intel render node
are unavailable here; the image build and physical GPU validation remain to
be done on the deployment system.

## References

- Intel media driver builds and feature table:
  https://github.com/intel/media-driver
- Intel VPL status definitions:
  https://github.com/intel/libvpl/blob/main/api/vpl/mfxdefs.h
- Debian full-feature driver:
  https://packages.debian.org/trixie/intel-media-va-driver-non-free
- Debian VPL GPU runtime:
  https://packages.debian.org/trixie/libmfx-gen1.2
- FFmpeg device initialization:
  https://ffmpeg.org/ffmpeg.html
