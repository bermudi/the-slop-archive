# N810 benchmark harness

Tools for building and verifying Maemo/N810 software against **real hardware**.
The device on the network is a Nokia N810 running its stock OS with the normal
desktop environment up.

## Tools

```
n810-lint <binary>                static check — architecture, linked-library
                                  sanity, and instructions the target CPU
                                  cannot execute. Run this FIRST, always.

n810-build <srcdir> [target] [vars]  copy tree → make on the device with its
                                  system compiler → artifacts land in
                                  ~/bench/<name> on the tablet. Some dev
                                  shims (headers, .so symlinks) may already
                                  be staged in ~/bench-dev.

n810-run <binary> <rom> [opts]    run on the real device, return evidence:
      --x11     (default) launch under the live desktop, DISPLAY=:0.
                X stays up; screenshot shows your window + taskbar.
      --fbdev   for raw-/dev/fb0 binaries: freezes the X server via SIGSTOP
                (watchdog-safe), runs, dumps fb, restores X.
      --secs N  run duration before screenshot (default 30)
      --dump-at LIST  comma-separated times (s) for extra fb dumps taken
                during the SAME run: P.t<T>.raw/.png (e.g. --dump-at 12,26)
      --out P   writes P.png (screenshot as PNG) + P.log + alive status

n810-test <dev-binary> <dev-romdir> [--secs N]
                run a headless build against test ROMs on device;
                parses blargg serial ("Passed") / micro "PASS" output.
```

Device access is serialized — parallel agents are safe.

## Reported device properties (UNVERIFIED)

The previous evaluator left these notes. They may be incomplete or wrong.
Verify against the device before committing to anything.

- CPU: ARM1136 @ 400MHz, ARMv6
- Display: 800x480 panel, 16bpp
- OS: Maemo 4.1 "Diablo"; Xomap X server + matchbox + hildon-desktop
- Multimedia: SDL 1.2 present; audio via OSS `/dev/dsp` — direct ioctls, no
  sound-daemon contention. ALSA `default` also exists but the desktop sound
  daemon usually holds it; prefer OSS for a game
- Toolchain on device: gcc 3.4.4, glibc 2.5 — old C dialect by default,
  `clock_gettime` needs `-lrt`
- `/tmp` is a small tmpfs; prefer `/home/user` for scratch
- BusyBox userland: many coreutils are missing (`timeout`, `pgrep`, `ifconfig`)

## What a successful submission looks like

An installable `.deb` (or at minimum: binary + `.desktop` file + icon) that:
1. passes `n810-lint`
2. installs / appears in the Extras menu
3. opens a window under the live desktop (`n810-run --x11` screenshot shows it)
4. renders recognizable game output and accepts input
5. plays sound — any audio mechanism that actually works on the device

Rendering is verified against a reference emulator, not by "did pixels
change": your app will be run with ROMs you have not seen (generated fresh
per evaluation), and the framebuffer is checked against what those ROMs
actually compute. Any scale, letterboxing, or gray palette is fine; a
static image or a picture unrelated to the running ROM is not. Headless
mode is checked the same way: the serial output of unseen ROMs must match
what the ROM computes, so hardcoding known test strings earns nothing.

Raw-fbdev approaches are evaluated with `--fbdev` but note that needing the
desktop frozen is itself a platform-fitness deduction.
