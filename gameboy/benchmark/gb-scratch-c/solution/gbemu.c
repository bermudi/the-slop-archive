/* gbemu.c - oracle shim: adapts the vendored reference core to the task's
 * required CLI. Exists to prove the task is solvable end-to-end, not as
 * benchmark subject matter (solution/ is verifier-side). */
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <SDL2/SDL.h>
#include "gb.h"

static const uint8_t pal[4][3] = {
    {0x9B, 0xBC, 0x0F}, {0x8B, 0xAC, 0x0F}, {0x30, 0x62, 0x30}, {0x0F, 0x38, 0x0F},
};

static void on_serial(GB *g, uint8_t c) {
    (void)g;
    putchar(c);
    fflush(stdout);
}

static void dump_ppm(GB *g, const char *path) {
    FILE *f = fopen(path, "wb");
    if (!f) { fprintf(stderr, "gbemu: cannot write %s\n", path); return; }
    fprintf(f, "P6\n%d %d\n255\n", GB_W, GB_H);
    for (int i = 0; i < GB_W * GB_H; i++)
        fwrite(pal[g->ppu.px[i] & 3], 1, 3, f);
    fclose(f);
}

static int headless(GB *g, double seconds, const char *ppm) {
    long frames = (long)(seconds * 59.7275);
    for (long n = 0; n < frames; n++)
        gb_run_frame(g);
    if (ppm) dump_ppm(g, ppm);
    return 0;
}

static int windowed(GB *g) {
    if (SDL_Init(SDL_INIT_VIDEO) != 0) {
        fprintf(stderr, "gbemu: SDL_Init: %s\n", SDL_GetError());
        return 1;
    }
    SDL_Window *win = SDL_CreateWindow("gbemu", SDL_WINDOWPOS_UNDEFINED,
        SDL_WINDOWPOS_UNDEFINED, GB_W * 3, GB_H * 3, SDL_WINDOW_SHOWN);
    if (!win) {                       /* no usable video driver: still run */
        for (;;) { gb_run_frame(g); SDL_Delay(16); }
    }
    SDL_Renderer *ren = SDL_CreateRenderer(win, -1, 0);
    SDL_Texture *tex = ren ? SDL_CreateTexture(ren, SDL_PIXELFORMAT_RGB24,
        SDL_TEXTUREACCESS_STREAMING, GB_W, GB_H) : NULL;
    uint8_t rgb[GB_W * GB_H * 3];
    for (;;) {
        SDL_Event ev;
        while (SDL_PollEvent(&ev))
            if (ev.type == SDL_QUIT) goto done;
        gb_run_frame(g);
        if (tex) {
            for (int i = 0; i < GB_W * GB_H; i++)
                memcpy(rgb + i * 3, pal[g->ppu.px[i] & 3], 3);
            SDL_UpdateTexture(tex, NULL, rgb, GB_W * 3);
            SDL_RenderCopy(ren, tex, NULL, NULL);
            SDL_RenderPresent(ren);
        }
        SDL_Delay(16);
    }
done:
    SDL_Quit();
    return 0;
}

int main(int argc, char **argv) {
    const char *rom = NULL, *ppm = NULL;
    double seconds = 10.0;
    int hl = 0;
    for (int i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "--headless")) hl = 1;
        else if (!strcmp(argv[i], "--seconds") && i + 1 < argc) seconds = atof(argv[++i]);
        else if (!strcmp(argv[i], "--frame-out") && i + 1 < argc) ppm = argv[++i];
        else if (argv[i][0] == '-') { fprintf(stderr, "gbemu: unknown option %s\n", argv[i]); return 2; }
        else rom = argv[i];
    }
    if (!rom) { fprintf(stderr, "usage: gbemu <rom.gb> [--headless --seconds N --frame-out F]\n"); return 2; }

    GB *g = calloc(1, sizeof *g);
    gb_init(g);
    gb_boot(g);
    g->on_serial = on_serial;
    if (gb_load_rom(g, rom) != 0) return 1;

    int rc = hl ? headless(g, seconds, ppm) : windowed(g);
    free(g);
    return rc;
}
