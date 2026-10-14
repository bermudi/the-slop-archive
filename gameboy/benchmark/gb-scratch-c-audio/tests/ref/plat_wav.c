/* plat_wav.c - headless platform variant that also captures APU output.
 * Runs N frames like plat_headless.c (serial -> stdout, optional --ppm),
 * and drains the APU ring into a PCM WAV (44100 Hz, u8 stereo, exactly
 * the format apu.c emits into the ring).
 *
 *   gbn8-wav <rom> [--frames N] [--ppm FILE] [--wav FILE]
 *
 * Verifier-side only: builds the reference audio oracle so the audio
 * challenge ROM can be instrument-validated against the trusted core.
 */
#include "gb.h"
#include <signal.h>

static volatile sig_atomic_t g_stop = 0;
static void on_sigint(int s) { (void)s; g_stop = 1; }

static void headless_serial(GB *g, uint8_t b) {
    (void)g;
    fputc(b, stdout);
    fflush(stdout);
}

static const uint8_t gray_palette[4][3] = {
    {0xFF, 0xFF, 0xFF}, {0xAA, 0xAA, 0xAA}, {0x55, 0x55, 0x55}, {0x00, 0x00, 0x00},
};

static void dump_ppm(GB *g, const char *path) {
    FILE *f = fopen(path, "wb");
    if (!f) { fprintf(stderr, "gbn8-wav: cannot write %s\n", path); return; }
    fprintf(f, "P6\n%d %d\n255\n", GB_W, GB_H);
    for (int i = 0; i < GB_W * GB_H; i++)
        fwrite(gray_palette[g->ppu.px[i] & 3], 1, 3, f);
    fclose(f);
}

static void wav_header(FILE *f, long data_len) {
    /* 44-byte canonical PCM header: u8 samples, 2ch, 44100 Hz */
    fseek(f, 0, SEEK_SET);
    fwrite("RIFF", 1, 4, f);
    uint32_t u32; uint16_t u16;
    u32 = 36 + (uint32_t)data_len; fwrite(&u32, 4, 1, f);
    fwrite("WAVE", 1, 4, f);
    fwrite("fmt ", 1, 4, f);
    u32 = 16; fwrite(&u32, 4, 1, f);
    u16 = 1; fwrite(&u16, 2, 1, f);          /* PCM */
    u16 = 2; fwrite(&u16, 2, 1, f);          /* stereo */
    u32 = 44100; fwrite(&u32, 4, 1, f);
    u32 = 44100 * 2; fwrite(&u32, 4, 1, f);  /* byte rate */
    u16 = 2; fwrite(&u16, 2, 1, f);          /* block align */
    u16 = 8; fwrite(&u16, 2, 1, f);          /* bits */
    fwrite("data", 1, 4, f);
    u32 = (uint32_t)data_len; fwrite(&u32, 4, 1, f);
}

int main(int argc, char **argv) {
    const char *rom = NULL, *ppm = NULL, *wav = NULL;
    long frames = 60;

    for (int i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "--frames") && i + 1 < argc) frames = atol(argv[++i]);
        else if (!strcmp(argv[i], "--ppm") && i + 1 < argc) ppm = argv[++i];
        else if (!strcmp(argv[i], "--wav") && i + 1 < argc) wav = argv[++i];
        else if (!strcmp(argv[i], "-h") || !strcmp(argv[i], "--help")) {
            printf("usage: gbn8-wav <rom.gb> [--frames N] [--ppm FILE] [--wav FILE]\n");
            return 0;
        }
        else if (argv[i][0] == '-') { fprintf(stderr, "gbn8-wav: unknown option %s\n", argv[i]); return 2; }
        else rom = argv[i];
    }
    if (!rom) { fprintf(stderr, "usage: gbn8-wav <rom.gb> [--frames N] [--ppm FILE] [--wav FILE]\n"); return 2; }

    GB *g = calloc(1, sizeof *g);
    gb_init(g);
    gb_boot(g);
    g->on_serial = headless_serial;

    if (gb_load_rom(g, rom) != 0) return 1;

    FILE *wf = NULL;
    if (wav) {
        wf = fopen(wav, "wb");
        if (!wf) { fprintf(stderr, "gbn8-wav: cannot write %s\n", wav); return 1; }
        wav_header(wf, 0);           /* placeholder, rewritten at close */
    }

    signal(SIGINT, on_sigint);
    signal(SIGTERM, on_sigint);

    uint8_t buf[8192];
    long wav_bytes = 0;
    for (long n = 0; n < frames && !g_stop; n++) {
        gb_run_frame(g);
        if (wf) {
            int got = apu_pull(g, buf, sizeof buf);
            if (got > 0) { fwrite(buf, 1, got, wf); wav_bytes += got; }
        }
    }

    if (wf) { wav_header(wf, wav_bytes); fclose(wf); }
    if (ppm) dump_ppm(g, ppm);
    gb_save(g);
    return 0;
}
