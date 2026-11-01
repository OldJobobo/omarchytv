# Local webOS 3 emulator

The configured host runs LG's official **webOS TV 3.0 Emulator** image under QEMU/KVM, without installing VirtualBox. Its app engine reports **Chromium 38.0.2125.122**, matching the old TV engine. The guest is Linux i686, not the physical TV's ARM firmware.

## Daily use

From the fork checkout:

```sh
./fork/emulator run
```

This starts the owned VM if needed, waits for the SDK welcome app to finish booting, launches the already-installed OmarchyTV app, verifies that it is actually visible, and opens a windowed VNC viewer unless one is already connected. The guest remains 1920×1080; resizing the viewer does not change the app's viewport. There is no autostart service. RAM is consumed only while the VM runs.

```sh
./fork/emulator status
./fork/emulator start
./fork/emulator view
./fork/emulator view --fullscreen
./fork/emulator launch
./fork/emulator key right
./fork/emulator key escape
./fork/emulator key home
./fork/emulator screenshot home.png
./fork/emulator stop
./fork/emulator stop --force
```

- `start` is headless; `view` opens an existing VM.
- Arrows/Enter navigate the app. Escape or Backspace acts as Back; right Super/Logo opens the SDK Home UI. The `key` command injects into the guest only, never the desktop or TV.
- `stop` requests guest ACPI shutdown. The tested old SDK guest did **not** exit on that request; `stop --force` is the explicit, verified way to quit it after app settings are saved. It quits only the PID/QMP name/disk verified as this VM, flushes QEMU's block layer, and never deletes the overlay or kills other QEMU processes. Like a VM power-off, it is not a guest filesystem-clean shutdown.
- Closing the viewer does **not** stop the VM.
- `screenshot` captures the **entire guest framebuffer**, unmodified, into `.local/emulator/evidence/`. PNG conversion requires the host's Pillow library. These are **emulator screenshots, not physical-TV evidence**.
- The old Qt engine's `Page.captureScreenshot` can time out; use the QEMU framebuffer capture instead.

## Build and install a candidate

The ignored `emulator` profile is deliberately separate from `livingroom`: debug inspectability is enabled only in the VM build, the terminal identifies an emulator, and no private legacy Home/startup overlay or flags are installed. It can retain the authored TV fallback catalog for layout/navigation testing, but the streaming apps are **not installed in the VM**.

```sh
./fork/dev integrate
./fork/dev build --profile emulator --package
./fork/emulator install --build .local/builds/BUILD-DIRECTORY
./fork/emulator launch
```

Use the build directory printed by the builder, relative to the checkout. Without `--build`, the controller uses its recorded emulator build in `.local/emulator/evidence/build-result.json`. Installation checks the profile, app ID, debug flag and IPK hash, then closes only an existing VM OmarchyTV instance before replacement so stale page code is not reused. A livingroom-profile package is refused by this controller. It always names the isolated SDK device explicitly, validates its loopback address/port/account, checks the pinned developer SSH connection, and uses a project-local SDK HOME. No real-TV device profile or key is loaded.

LG CLI 3.0.2 installation code fails under Node 26 (`isDate is not a function`). The configured SDK operations use an **existing Node 22 runtime**, selected in the private config. The system Node version, global packages and vendor SDK files are not changed. Node 22+ can run the local inspector/smoke client; the CLI packaging path remains separately pinned by `fork/package-lock.json`.

## Real-engine regression checks

Start the VM and launcher, close the viewer, leave the app on Home/dock with no dialog open, then run:

```sh
./fork/emulator smoke
```

The smoke test uses the actual guest keyboard and app inspector. It checks the authored dock order, every loaded palette's popup/heading/selection/focus RGB roles, disabled-widget visibility, Escape modal closing and runtime errors. Stored preferences and dock focus are restored afterward. It refuses an attached viewer, and stops further preference writes if an operator attaches during its theme loop.

RGB comparisons are exact. Chromium 38 quantizes popup alpha to eight bits, so alpha serialization has a tolerance of one step out of 255; this is not permission to recolor authored palette values. Native input is paced and modal closure is awaited rather than assuming modern-browser timing.

Full stock-theme Settings captures and machine-readable results stay in ignored evidence. Custom artwork and profiles are never uploaded by these commands.

## Isolation and local files

- Default configured resources: **1024 MiB RAM, two vCPUs**.
- Software VGA display, emulated PCnet networking and silent emulated audio; no host audio capture/playback.
- Original VMDK is read-only and hash-checked on startup. Normal guest writes go only to the QCOW2 overlay.
- QEMU's restricted user network blocks guest outbound access; there is no bridge, TAP setup, host filesystem share, USB passthrough or guest clipboard agent.
- SSH, inspector and VNC bind only to localhost. QMP uses a Unix socket under the ignored run directory.
- VM control verifies the current user's PID, exact VM name, disk and restricted network before sending commands. It never uses `killall`, a real-TV SSH target or an operator controller.
- The SDK developer key is the CLI's stock **2048-bit emulator key**, stored with restrictive permissions under the ignored emulator directory. The stale 1024-bit key bundled with the old ZIP did not authenticate. No personal TV key is copied.
- Legacy RSA signature compatibility is scoped to this pinned localhost guest, not global SSH configuration or the TV.

`.local/emulator/config.json` selects the vendor/base/overlay paths, their hash, resources, localhost ports, SDK Node runtime and developer-key path. `.local/emulator/home/` contains isolated CLI device settings. `.local/emulator/installed.json` records the installed VM candidate, separately from physical-TV deployment evidence. An internal `refs/omarchytv/emulator-installed` source pin keeps that commit reachable when disposable integration refs are rebuilt; it is not a public branch or a ref to push.

The controller intentionally does **not** download SDK software, accept a license, install packages, load modules, create a system VM definition, reset a guest disk or configure the physical TV. A fresh machine needs QEMU/KVM, a VNC viewer, the project CLI dependencies, a suitable Node runtime, and an independently prepared private config/image/overlay. Pin the guest SSH host key only after confirming the listening process is the newly created owned VM.

## Licensing and fidelity limits

LG's emulator is proprietary SDK software. The operator must accept LG's terms before downloading/using it. Keep the SDK, images, keys, writable overlay, personal profiles and captures out of Git; do not redistribute the appliance as part of the fork. This setup preserves the original image rather than patching vendor binaries.

Official emulator/download documentation:
https://webostv.developer.lge.com/develop/tools/emulator-installation

Engine/version mapping:
https://webostv.developer.lge.com/develop/specifications/web-api-and-web-engine

This is a **3.x development environment, not a clone of the TV's exact 3.9 build**. It does not establish DRM/streaming-app, HDMI/tuner, physical audio, Magic Remote sensor, ARM performance/RAM, root/Home integration, SSH-autostart/privacy/inspector-guard or cold-boot acceptance. Keep physical-TV tests for those final hardware/integration checks; routine UI and legacy-engine work can stay here.

`--[ Pi :: gpt-6.1-sol ]--`\
   `--- on behalf of:` @OldJobobo
