/* gb.c - core glue: init, post-boot state, frame pump. */
#include "gb.h"

void gb_init(GB *g) {
    memset(g, 0, sizeof *g);
    /* HRAM/IO default read values that games expect before touching them */
    g->bus[0xFF0F] = 0xE1;                   /* IF */
    apu_init(g);
}

/* register state the real DMG boot ROM leaves behind */
void gb_boot(GB *g) {
    Cpu *c = &g->cpu;
    c->a = 0x01;
    c->f = 0xB0;
    c->b = 0x00; c->c = 0x13;
    c->d = 0x00; c->e = 0xD8;
    c->h = 0x01; c->l = 0x4D;
    c->sp = 0xFFFE;
    c->pc = 0x0100;
    g->timer.div = 0xAB00;                   /* DIV reads 0xAB at boot */
    g->timer.tac = 0xF8;
    g->bus[0xFF40] = 0x91;                   /* LCDC */
    g->bus[0xFF41] = 0x85;                   /* STAT */
    g->bus[0xFF47] = 0xFC;                   /* BGP */
    g->bus[0xFF48] = 0xFF;                   /* OBP0 */
    g->bus[0xFF49] = 0xFF;                   /* OBP1 */
    g->ppu.lcd_on = 1;
    g->ppu.mode = 2;
    g->bus[0xFF02] = 0x7E;                   /* SC */
}

/* advance every component; called by the CPU between bus accesses */
void gb_tick(GB *g, int cycles) {
    timer_tick(g, cycles);
    ppu_tick(g, cycles);
    apu_tick(g, cycles >> 2);
    if (g->serial_delay > 0 && (g->serial_delay -= cycles) <= 0)
        g->bus[0xFF0F] |= IF_SERIAL;
}

void gb_run_frame(GB *g) {
    g->frame_done = 0;
    long guard = GB_FRAME_CYCLES * 4;
    while (!g->frame_done && guard > 0)
        guard -= cpu_step(g);
    if (!g->frame_done) {
        fprintf(stderr, "gbn810: frame %ld did not reach vblank (stalled?)\n", g->frame_no);
        g->frame_done = 1;
    }
    g->frame_no++;
}

/* platforms install their own g->on_serial; headless prints to stdout */
