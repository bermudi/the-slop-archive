# N810 benchmark harness

Tools for building and verifying Maemo/N810 software against **real hardware**.
The device is a Nokia N810: ARM1136 @ 400MHz (ARMv6, pre-v6K), 800x480 **16bpp**
LCD, Maemo 4.1 "Diablo", Xomap X server + matchbox + hildon-desktop running.

## Tools

```
n810-lint <binary>                static check — catches what QEMU cannot:
                                  v6K+ opcodes (ldrex*/strex*/clrex…),
                                  SDL2/other nonexistent lib linkage,
                                  wrong arch. Run this FIRST, always.

n810-build <srcdir> [target] [vars]  copy tree → make with the device's own
                                  gcc 3.4.4 → artifacts in ~/bench/<name>
                                  on the tablet. -dev shims (SDL headers,
                                  .so symlinks) pre-staged in ~/bench-dev.

n810-run <binary> <rom> [opts]    run on the real device, return evidence:
      --x11     (default) launch under the live desktop, DISPLAY=:0.
                X stays up; screenshot shows your window + taskbar.
      --fbdev   for raw-/dev/fb0 binaries: freezes Xomap via SIGSTOP
                (watchdog-safe), runs, dumps fb, restores X.
      --secs N  run duration before screenshot (default 30)
      --dump-at LIST  comma-separated times (s) for extra fb dumps taken
                during the SAME run: P.t<T>.raw/.png (e.g. --dump-at 12,26)
      --out P   writes P.png (800x480 RGB565→PNG) + P.log + alive status

n810-test <dev-binary> <dev-romdir> [--secs N]
                run a headless build against test ROMs on device;
                parses blargg serial ("Passed") / micro "PASS" output.
```

Device access is serialized via flock — parallel agents are safe.

## Environment facts you cannot assume away

- **No SDL2.** SDL 1.2 only. `-lSDL`, `SDL_SetVideoMode`, 1999 API.
- **Panel is 16bpp max.** `SDL_SetVideoMode(w,h,32,...)` fails on device.
- **No `/dev/dsp`.** OSS never existed on this OS — and `/dev/dspctl` /
  `/dev/dsptask/*` are the OMAP DSP gateway, *not* OSS (a `ls /dev/dsp*`
  glob will fool you). Working audio: `SDL_OpenAudio` (loads libasound +
  the alsa_dsp plugin, opens `/dev/dsptask*`; verified audible on hardware)
  or libasound `default` when esd doesn't hold it.
- **gcc 3.4.4 / glibc 2.5.** No anonymous unions without `-fms-extensions`,
  defaults to gnu89 (`-std=gnu99` needed for C99 declarations),
  `clock_gettime` needs `-lrt`.
- **Pre-v6K silicon.** No LDREX/STREX/CLREX/DMB — `zig cc -mcpu=arm1136j_s`
  emits them anyway (LLVM models the _s rev as v6K). Do not trust readelf
  CPU tags or qemu-arm; both lie about this. `n810-lint` is the check.
- **`/tmp` is 512KB.** Don't write dumps there; use `/home/user`.
- **No `timeout`, `pgrep`, `ifconfig`.** BusyBox 1.6.1.

## What a successful submission looks like

An installable `.deb` (or at minimum: binary + `.desktop` file + icon) that:
1. passes `n810-lint`
2. installs / appears in the Extras menu
3. opens a **managed window** under matchbox (`n810-run --x11` screenshot
   shows it)
4. renders recognizable game output and accepts input
5. plays sound — any audio mechanism that actually works on the device

Raw-fbdev approaches are evaluated with `--fbdev` but note that needing the
desktop frozen is itself a platform-fitness deduction.
