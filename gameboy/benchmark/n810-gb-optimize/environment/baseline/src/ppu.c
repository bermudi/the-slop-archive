/* ppu.c - DMG picture processing unit.
 *
 * Scanline renderer with hardware-mode timing:
 *   mode 2 (OAM scan) 80 dots -> mode 3 (drawing) 172 dots
 *   -> mode 0 (hblank) 204 dots = 456 dots/line, 154 lines/frame.
 * Lines are rendered when mode 3 begins, as on hardware.
 */
#include "gb.h"

#define MODE_HBLANK 0
#define MODE_VBLANK 1
#define MODE_OAM    2
#define MODE_DRAW   3

static void stat_irq(GB *g) { g->bus[0xFF0F] |= IF_STAT; }

static void check_lyc(GB *g) {
    Ppu *p = &g->ppu;
    uint8_t stat = g->bus[0xFF41];
    if (p->ly == p->lyc) {
        g->bus[0xFF41] = (uint8_t)(stat | 0x04);
        if (stat & 0x40) stat_irq(g);
    } else {
        g->bus[0xFF41] = (uint8_t)(stat & ~0x04);
    }
}

/* render one scanline into p->px */
static void render_line(GB *g) {
    Ppu *p = &g->ppu;
    uint8_t lcdc = g->bus[0xFF40];
    int ly = p->ly;
    uint8_t *line = p->px + (size_t)ly * GB_W;
    uint8_t bgsh[GB_W];            /* bg/window shade per pixel */
    uint8_t bgp = g->bus[0xFF47];

    /* --- background + window --- */
    int bg_on = lcdc & 0x01;
    int win_on = (lcdc & 0x20) != 0;
    if (win_on && ly == g->bus[0xFF4A]) p->win_active = 1;  /* WY latch */
    win_on = win_on && p->win_active;
    int scy = g->bus[0xFF42], scx = g->bus[0xFF43];
    int bg_map = (lcdc & 0x08) ? 0x1C00 : 0x1800;
    int win_map = (lcdc & 0x40) ? 0x1C00 : 0x1800;
    int signed_tiles = !(lcdc & 0x10);
    int wxoff = g->bus[0xFF4B] - 7;

    for (int x = 0; x < GB_W; x++) {
        int px, py, map;
        if (win_on && x >= wxoff) {
            px = x - wxoff;
            py = p->win_line;
            map = win_map;
        } else {
            px = (scx + x) & 0xFF;
            py = (scy + ly) & 0xFF;
            map = bg_map;
        }
        uint8_t tile = g->bus[0x8000 + map + (py >> 3) * 32 + (px >> 3)];
        int addr = signed_tiles
            ? 0x1000 + (int8_t)tile * 16 + (py & 7) * 2
            : tile * 16 + (py & 7) * 2;
        uint8_t lo = g->bus[0x8000 + addr];
        uint8_t hi = g->bus[0x8000 + addr + 1];
        int bit = 7 - (px & 7);
        int col = (((hi >> bit) & 1) << 1) | ((lo >> bit) & 1);
        bgsh[x] = (uint8_t)((bgp >> (col * 2)) & 3);
    }
    if (!bg_on)
        for (int x = 0; x < GB_W; x++) bgsh[x] = (uint8_t)(bgp & 3);
    memcpy(line, bgsh, GB_W);

    /* --- sprites --- */
    if (!(lcdc & 0x02)) {
        if (win_on) p->win_line++;
        return;
    }
    int h = (lcdc & 0x04) ? 16 : 8;
    typedef struct { uint8_t x, lo, hi, attr; } Spr;
    Spr sp[10];
    int n = 0;
    for (int i = 0; i < 40 && n < 10; i++) {
        const uint8_t *o = g->bus + 0xFE00 + i * 4;
        int sy = o[0] - 16, sx = o[1] - 8;
        int row = ly - sy;
        if (row < 0 || row >= h) continue;
        uint8_t tile = o[2];
        if (h == 16) tile &= 0xFE;
        int trow = (o[3] & 0x40) ? (h - 1 - row) : row;
        int addr = 0x8000 + tile * 16 + trow * 2;
        sp[n].x = (uint8_t)sx;
        sp[n].lo = g->bus[addr];
        sp[n].hi = g->bus[addr + 1];
        sp[n].attr = o[3];
        n++;
    }
    /* stable sort by x: lowest x (then lowest OAM index) wins */
    for (int i = 1; i < n; i++) {
        Spr t = sp[i];
        int j = i - 1;
        while (j >= 0 && sp[j].x > t.x) { sp[j + 1] = sp[j]; j--; }
        sp[j + 1] = t;
    }
    for (int x = 0; x < GB_W; x++) {
        for (int i = 0; i < n; i++) {
            if (x < sp[i].x || x >= sp[i].x + 8) continue;
            int px = x - sp[i].x;
            int bit = (sp[i].attr & 0x20) ? px : 7 - px;
            int col = (((sp[i].hi >> bit) & 1) << 1) | ((sp[i].lo >> bit) & 1);
            if (col == 0) continue;
            if ((sp[i].attr & 0x80) && bg_on && bgsh[x] != 0) continue; /* behind bg */
            uint8_t pal = (sp[i].attr & 0x10) ? g->bus[0xFF49] : g->bus[0xFF48];
            line[x] = (uint8_t)((pal >> (col * 2)) & 3);
            break;                       /* first sprite in priority order */
        }
    }
    if (win_on) p->win_line++;
}

void ppu_tick(GB *g, int cycles) {
    Ppu *p = &g->ppu;
    if (!p->lcd_on) {
        p->off_dots += cycles;
        if (p->off_dots >= GB_FRAME_CYCLES) {
            p->off_dots -= GB_FRAME_CYCLES;
            g->frame_done = 1;         /* keep frames flowing while LCD off */
        }
        return;
    }

    p->line_dots += cycles;
    switch (p->mode) {
    case MODE_OAM:
        if (p->line_dots >= 80) {
            p->mode = MODE_DRAW;
            render_line(g);
        }
        break;
    case MODE_DRAW:
        if (p->line_dots >= 80 + 172) {
            p->mode = MODE_HBLANK;
            if (g->bus[0xFF41] & 0x08) stat_irq(g);
        }
        break;
    case MODE_HBLANK:
        if (p->line_dots >= 456) {
            p->line_dots -= 456;
            p->ly++;
            if (p->ly == 144) {
                p->mode = MODE_VBLANK;
                g->bus[0xFF0F] |= IF_VBLANK;
                g->frame_done = 1;
                if (g->bus[0xFF41] & 0x10) stat_irq(g);
            } else {
                p->mode = MODE_OAM;
                if (g->bus[0xFF41] & 0x20) stat_irq(g);
            }
            check_lyc(g);
        }
        break;
    case MODE_VBLANK:
        if (p->line_dots >= 456) {
            p->line_dots -= 456;
            p->ly++;
            if (p->ly > 153) {
                p->ly = 0;
                p->mode = MODE_OAM;
                p->win_line = 0;       /* window counter resets at frame start */
                p->win_active = 0;
                if (g->bus[0xFF41] & 0x20) stat_irq(g);
            }
            check_lyc(g);
        }
        break;
    }
}
