/* plat_headless.c - headless platform: run N frames, capture serial output,
 * optionally dump a screenshot as PPM. Used for hardware test ROMs (blargg)
 * and CI. Builds on any POSIX host.
 *
 *   gbn8 <rom> [--frames N] [--ppm FILE] [--rate HZ] [--quiet]
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
    if (!f) { fprintf(stderr, "gbn8: cannot write %s\n", path); return; }
    fprintf(f, "P6\n%d %d\n255\n", GB_W, GB_H);
    for (int i = 0; i < GB_W * GB_H; i++)
        fwrite(gray_palette[g->ppu.px[i] & 3], 1, 3, f);
    fclose(f);
}

int main(int argc, char **argv) {
    const char *rom = NULL, *ppm = NULL;
    long frames = 60;

    for (int i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "--frames") && i + 1 < argc) frames = atol(argv[++i]);
        else if (!strcmp(argv[i], "--ppm") && i + 1 < argc) ppm = argv[++i];
        else if (!strcmp(argv[i], "-h") || !strcmp(argv[i], "--help")) {
            printf("usage: gbn8 <rom.gb> [--frames N] [--ppm FILE]\n");
            return 0;
        }
        else if (argv[i][0] == '-') { fprintf(stderr, "gbn8: unknown option %s\n", argv[i]); return 2; }
        else rom = argv[i];
    }
    if (!rom) { fprintf(stderr, "usage: gbn8 <rom.gb> [--frames N] [--ppm FILE]\n"); return 2; }

    GB *g = calloc(1, sizeof *g);
    gb_init(g);
    gb_boot(g);
    g->on_serial = headless_serial;

    if (gb_load_rom(g, rom) != 0) return 1;

    signal(SIGINT, on_sigint);
    signal(SIGTERM, on_sigint);

    for (long n = 0; n < frames && !g_stop; n++)
        gb_run_frame(g);

    if (ppm) dump_ppm(g, ppm);
    gb_save(g);
    return 0;
}
