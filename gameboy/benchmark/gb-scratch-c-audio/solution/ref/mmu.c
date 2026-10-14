/* mmu.c - memory map, MBC1/2/3/5 cartridge controllers, joypad, serial.
 * DMG (original Game Boy) only.
 */
#include "gb.h"
#include <errno.h>

/* ---- cartridge ---- */

static int rom_banks_for(uint8_t id) {
    if (id <= 8) return 2 << id;          /* 32KB..8MB */
    return 2;
}

static long ram_size_for(uint8_t id) {
    switch (id) {
    case 1: return 2048;
    case 2: return 8192;
    case 3: return 32768;
    case 4: return 131072;
    case 5: return 65536;
    default: return 0;
    }
}

int gb_load_rom(GB *g, const char *path) {
    Cart *ct = &g->cart;
    FILE *f = fopen(path, "rb");
    if (!f) { fprintf(stderr, "gbn810: cannot open %s: %s\n", path, strerror(errno)); return -1; }
    fseek(f, 0, SEEK_END);
    long sz = ftell(f);
    fseek(f, 0, SEEK_SET);
    if (sz < 0x8000 || (sz & 0x3FFF)) {
        fprintf(stderr, "gbn810: %s does not look like a ROM (%ld bytes)\n", path, sz);
        fclose(f);
        return -1;
    }
    ct->rom = malloc((size_t)sz);
    if (!ct->rom || fread(ct->rom, 1, (size_t)sz, f) != (size_t)sz) {
        fprintf(stderr, "gbn810: read failed on %s\n", path);
        fclose(f);
        return -1;
    }
    fclose(f);
    ct->rom_size = sz;
    ct->rom_banks = rom_banks_for(ct->rom[0x0148]);

    uint8_t type = ct->rom[0x0147];
    switch (type) {
    case 0x00: ct->mbc = GB_MBC_NONE; break;
    case 0x01: case 0x02: case 0x03: ct->mbc = GB_MBC1; break;
    case 0x05: case 0x06: ct->mbc = GB_MBC2; break;
    case 0x0F: case 0x10: case 0x11: case 0x12: case 0x13: ct->mbc = GB_MBC3; break;
    case 0x19: case 0x1A: case 0x1B: case 0x1C: case 0x1D: case 0x1E: ct->mbc = GB_MBC5; break;
    default:
        fprintf(stderr, "gbn810: unsupported mapper 0x%02X, treating as ROM-only\n", type);
        ct->mbc = GB_MBC_NONE;
        break;
    }
    ct->battery = (type == 0x03 || type == 0x06 || type == 0x0F ||
                   type == 0x10 || type == 0x13 || type == 0x1B || type == 0x1E);
    ct->has_rtc = (type == 0x0F || type == 0x10);
    ct->rtc_base = time(NULL);

    if (ct->mbc == GB_MBC2) {
        ct->ram_size = 512;
        ct->ram = calloc(512, 1);
    } else {
        ct->ram_size = ram_size_for(ct->rom[0x0149]);
        if (ct->ram_size > 0) ct->ram = calloc((size_t)ct->ram_size, 1);
    }
    if (ct->ram_size > 0 && !ct->ram) { fprintf(stderr, "gbn810: OOM cart ram\n"); return -1; }

    /* save file path: <rom>.sav */
    snprintf(ct->sav_path, sizeof ct->sav_path, "%s.sav", path);

    if (ct->battery) {
        FILE *s = fopen(ct->sav_path, "rb");
        if (s) {
            size_t n = fread(ct->ram, 1, (size_t)ct->ram_size, s);
            (void)n;
            fclose(s);
        }
    }
    return 0;
}

void gb_save(GB *g) {
    Cart *ct = &g->cart;
    if (!ct->battery || !ct->ram || !ct->dirty) return;
    FILE *s = fopen(ct->sav_path, "wb");
    if (!s) { fprintf(stderr, "gbn810: cannot write %s\n", ct->sav_path); return; }
    fwrite(ct->ram, 1, (size_t)ct->ram_size, s);
    if (ct->has_rtc) {
        /* persist 5 rtc regs + epoch base so in-game clock survives */
        time_t now = time(NULL);
        long total = ct->rtc_offset + (long)(now - ct->rtc_base);
        uint8_t buf[16] = {0};
        buf[0] = (uint8_t)(total % 60);
        buf[1] = (uint8_t)((total / 60) % 60);
        buf[2] = (uint8_t)((total / 3600) % 24);
        uint16_t days = (uint16_t)((total / 86400) & 0x1FF);
        buf[3] = (uint8_t)(days & 0xFF);
        buf[4] = (uint8_t)((days >> 8) | (ct->rtc_halt ? 0x40 : 0) | (ct->rtc_carry ? 0x80 : 0));
        memcpy(buf + 5, &total, sizeof total);
        fwrite(buf, 1, 16, s);
    }
    fclose(s);
    ct->dirty = 0;
}

/* ---- rtc helpers (mbc3): seconds since a fixed epoch ---- */

static void rtc_set_base(Cart *ct) { ct->rtc_base = time(NULL); }

static long rtc_total(Cart *ct) {
    return ct->rtc_offset + (long)(time(NULL) - ct->rtc_base);
}

/* ---- rom / ram window reads ---- */

static uint8_t cart_rom(GB *g, uint16_t a) {
    Cart *ct = &g->cart;
    int bank = 0;
    if (a < 0x4000) {
        if (ct->mbc == GB_MBC1 && ct->mode_sel)
            bank = (ct->bank2 << 5) & (ct->rom_banks - 1);
    } else {
        switch (ct->mbc) {
        case GB_MBC1: {
            bank = ct->rom_low & 0x1F;
            if (bank == 0) bank = 1;
            if (ct->mode_sel) bank |= ct->bank2 << 5;
            bank &= ct->rom_banks - 1;
            break;
        }
        case GB_MBC3: {
            bank = ct->rom_low & 0x7F;
            if (bank == 0) bank = 1;
            bank &= ct->rom_banks - 1;
            break;
        }
        case GB_MBC5: {
            bank = ct->rom_low & (ct->rom_banks - 1);
            break;
        }
        default: bank = a >> 14; break;
        }
        a -= 0x4000;
    }
    long off = (long)bank * 0x4000 + a;
    if (off >= ct->rom_size) return 0xFF;
    return ct->rom[off];
}

static uint8_t cart_ram(GB *g, uint16_t a) {
    Cart *ct = &g->cart;
    if (ct->mbc == GB_MBC2) {
        if (!ct->ramg || a > 0x01FF) return 0xFF;
        return (uint8_t)(ct->ram[a & 0x1FF] | 0xF0);
    }
    if (!ct->ramg) return 0xFF;
    if (ct->mbc == GB_MBC3 && ct->ram_bank >= 0x08) {
        long t = rtc_total(ct);
        switch (ct->ram_bank) {
        case 0x08: return (uint8_t)(t % 60);
        case 0x09: return (uint8_t)((t / 60) % 60);
        case 0x0A: return (uint8_t)((t / 3600) % 24);
        case 0x0B: return (uint8_t)((t / 86400) & 0xFF);
        default:   return (uint8_t)((((t / 86400) >> 8) & 1)
                          | (ct->rtc_halt ? 0x40 : 0)
                          | (ct->rtc_carry ? 0x80 : 0));
        }
    }
    if (!ct->ram || ct->ram_size == 0) return 0xFF;
    int mask = (int)(ct->ram_size / 8192) - 1;
    int bank = ct->ram_bank & (mask > 0 ? mask : 0);
    if (ct->mbc == GB_MBC1 && !ct->mode_sel) bank = 0;
    long off = (long)bank * 8192 + (a - 0xA000);
    if (off >= ct->ram_size) return 0xFF;
    return ct->ram[off];
}

/* ---- io ---- */

static uint8_t io_read(GB *g, uint16_t a) {
    Ppu *p = &g->ppu;
    switch (a) {
    case 0xFF00: {   /* joypad: 1 = released */
        uint8_t v = 0x0F;
        if (!(g->in.select & 0x10)) v &= (uint8_t)~g->in.dpad;
        if (!(g->in.select & 0x20)) v &= (uint8_t)~g->in.buttons;
        return (uint8_t)(0xC0 | v);
    }
    case 0xFF04: return (uint8_t)(g->timer.div >> 8);
    case 0xFF0F: return (uint8_t)(g->bus[0xFF0F] | 0xE0);
    case 0xFF41: {   /* STAT */
        uint8_t stat = g->bus[0xFF41];
        if (!p->lcd_on) return (uint8_t)((stat & 0x78) | 0x80);
        uint8_t mode = (uint8_t)p->mode;
        if (p->ly == p->lyc) mode |= 0x04;
        return (uint8_t)((stat & 0x78) | 0x80 | mode);
    }
    case 0xFF44: return (uint8_t)(p->lcd_on ? p->ly : 0);
    case 0xFF26: {   /* NR52 status */
        if (!g->apu.powered) return 0x70;
        uint8_t v = 0x80;
        if (g->apu.pulse[0].enabled) v |= 1;
        if (g->apu.pulse[1].enabled) v |= 2;
        if (g->apu.wave.enabled)     v |= 4;
        if (g->apu.noise.enabled)    v |= 8;
        return (uint8_t)(v | 0x70);
    }
    default:
        if (a >= 0xFF10 && a <= 0xFF25) return g->bus[a] | 0x00; /* raw */
        return g->bus[a];
    }
}

static void mbc_write(GB *g, uint16_t a, uint8_t v) {
    Cart *ct = &g->cart;
    switch (ct->mbc) {
    case GB_MBC1:
        if (a < 0x2000) ct->ramg = (v & 0x0F) == 0x0A;
        else if (a < 0x4000) ct->rom_low = v & 0x1F;
        else if (a < 0x6000) ct->bank2 = v & 0x03;
        else ct->mode_sel = v & 1;
        break;
    case GB_MBC2:
        if (a < 0x4000) {
            if (a & 0x0100) ct->rom_low = v & 0x0F;   /* bank only via odd addr */
            else ct->ramg = (v & 0x0F) == 0x0A;
        }
        break;
    case GB_MBC3:
        if (a < 0x2000) ct->ramg = (v & 0x0F) == 0x0A;
        else if (a < 0x4000) ct->rom_low = v & 0x7F;
        else if (a < 0x6000) {
            if (ct->ram_bank >= 0x08 && v >= 0x08) rtc_set_base(ct); /* keep epoch sane */
            ct->ram_bank = v & 0x0F;
        } else {
            /* latch clock data: 0x00 then 0x01; we always serve live values */
            (void)v;
        }
        break;
    case GB_MBC5:
        if (a < 0x2000) ct->ramg = (v & 0x0F) == 0x0A;
        else if (a < 0x3000) ct->rom_low = v;
        else if (a < 0x4000) ct->rom_low = (ct->rom_low & 0xFF) | ((v & 1) << 8);
        else if (a < 0x6000) ct->ram_bank = v & 0x0F;
        break;
    default:
        break;
    }
}

static void io_write(GB *g, uint16_t a, uint8_t v) {
    Ppu *p = &g->ppu;

    if (a >= 0xFF30 && a <= 0xFF3F) { g->bus[a] = v; return; }  /* wave RAM: always writable */
    if (a >= 0xFF10 && a <= 0xFF26) { apu_write(g, a, v); return; }

    switch (a) {
    case 0xFF00: g->in.select = v & 0x30; break;
    case 0xFF01: g->bus[0xFF01] = v; break;
    case 0xFF02:
        g->bus[0xFF02] = v;
        if (v & 0x80) {
            /* serial: blargg tests and printers use internal clock.
               we complete immediately-ish and raise the IRQ. */
            if (g->on_serial) g->on_serial(g, g->bus[0xFF01]);
            g->bus[0xFF02] = (uint8_t)(v & 0x7F);
            g->serial_delay = 4096;
        }
        break;
    case 0xFF04: {  /* DIV write: may cause a falling edge on the selected bit */
        Timer *t = &g->timer;
        static const int sh[4] = {9, 3, 5, 7};   /* TAC 0..3 -> div bit 9,3,5,7 */
        uint16_t old = t->div;
        t->div = 0;
        if ((t->tac & 4) && ((old >> sh[t->tac & 3]) & 1)) {
            if (++t->tima == 0) { t->tima = t->tma; g->bus[0xFF0F] |= IF_TIMER; }
        }
        break;
    }
    case 0xFF05: g->timer.tima = v; break;  /* TIMA */
    case 0xFF06: g->timer.tma = v; break;
    case 0xFF07: g->timer.tac = v & 0x07; break;  /* TAC: enable + rate select */
    case 0xFF0F: g->bus[0xFF0F] = (uint8_t)(v & 0x1F); break;
    case 0xFF40: {  /* LCDC */
        uint8_t old = g->bus[0xFF40];
        g->bus[0xFF40] = v;
        int was_on = old & 0x80, now_on = v & 0x80;
        p->lcd_on = now_on;
        if (!now_on && was_on) {
            p->ly = 0; p->mode = 0; p->line_dots = 0;
            p->win_active = 0; p->win_line = 0; p->off_dots = 0;
        } else if (now_on && !was_on) {
            p->ly = 0; p->mode = 2; p->line_dots = 0;
            p->win_active = 0; p->win_line = 0; p->off_dots = 0;
        }
        break;
    }
    case 0xFF41: {  /* STAT: writable bits 6-3; the STAT-block quirk fires an
                       immediate interrupt if a newly-enabled source matches */
        uint8_t old = g->bus[0xFF41];
        g->bus[0xFF41] = (uint8_t)((old & 0x07) | (v & 0x78));
        uint8_t irq = 0;
        if ((v & 0x40) && p->ly == p->lyc) irq = 1;
        if (!irq && (v & 0x20) && p->lcd_on && p->mode == 2) irq = 1;
        if (!irq && (v & 0x10) && p->lcd_on && p->mode == 1) irq = 1;
        if (!irq && (v & 0x08) && p->lcd_on && p->mode == 0) irq = 1;
        if (irq) g->bus[0xFF0F] |= IF_STAT;
        break;
    }
    case 0xFF45: {  /* LYC */
        g->bus[0xFF45] = v;
        p->lyc = v;
        if (p->lcd_on && p->ly == p->lyc) {
            g->bus[0xFF41] |= 0x04;
            if (g->bus[0xFF41] & 0x40) g->bus[0xFF0F] |= IF_STAT;
        }
        break;
    }
    case 0xFF46: {  /* OAM DMA: instant copy (documented simplification) */
        uint16_t src = (uint16_t)(v << 8);
        for (int i = 0; i < 160; i++)
            g->bus[0xFE00 + i] = gb_rd(g, (uint16_t)(src + i));
        break;
    }
    case 0xFF4D: break; /* KEY1: CGB speed switch, absent on DMG */

    default:
        g->bus[a] = v;
        break;
    }
}

/* ---- bus ---- */

uint8_t gb_rd(GB *g, uint16_t a) {
    if (a < 0x8000) return cart_rom(g, a);
    if (a < 0xA000) return g->bus[a];
    if (a < 0xC000) return cart_ram(g, a);
    if (a < 0xFE00) return g->bus[a - 0x2000];     /* WRAM + echo */
    if (a < 0xFEA0) return g->bus[a];              /* OAM */
    if (a < 0xFF00) return 0x00;
    if (a < 0xFF80) return io_read(g, a);
    if (a < 0xFFFF) return g->bus[a];              /* HRAM */
    return g->bus[0xFFFF];                         /* IE */
}

void gb_wr(GB *g, uint16_t a, uint8_t v) {
    if (a < 0x8000) { mbc_write(g, a, v); return; }
    if (a < 0xA000) { g->bus[a] = v; return; }     /* VRAM */
    if (a < 0xC000) { /* cart ram */
        Cart *ct = &g->cart;
        if (ct->mbc == GB_MBC2) {
            if (ct->ramg && a <= 0x01FF) { ct->ram[a & 0x1FF] = (uint8_t)(v & 0x0F); ct->dirty = 1; }
            return;
        }
        if (!ct->ramg || !ct->ram || ct->ram_size == 0) return;
        if (ct->mbc == GB_MBC3 && ct->ram_bank >= 0x08) {
            /* writing live rtc regs: fold the new value into our epoch */
            long t = rtc_total(ct);
            long day = t / 86400;
            switch (ct->ram_bank) {
            case 0x08: t = day * 86400 + (t % 86400) / 3600 * 3600 + (v & 0x3F) * 60 + t % 60; break;
            case 0x09: t = day * 86400 + (t % 86400) / 3600 * 3600 + (v & 0x3F) * 60 + t % 60; break;
            case 0x0A: t = day * 86400 + (v & 0x1F) * 3600 + t % 3600; break;
            case 0x0B: day = (day & ~0xFF) | v; t = day * 86400 + t % 86400; break;
            case 0x0C: {
                day = (day & 0xFF) | ((v & 1) << 8);
                ct->rtc_halt = (v & 0x40) != 0;
                ct->rtc_carry = (v & 0x80) != 0;
                t = day * 86400 + t % 86400;
                break;
            }
            default: return;
            }
            ct->rtc_offset = t;
            rtc_set_base(ct);
            return;
        }
        int mask = (int)(ct->ram_size / 8192) - 1;
        int bank = ct->ram_bank & (mask > 0 ? mask : 0);
        if (ct->mbc == GB_MBC1 && !ct->mode_sel) bank = 0;
        long off = (long)bank * 8192 + (a - 0xA000);
        if (off < ct->ram_size) { ct->ram[off] = v; ct->dirty = 1; }
        return;
    }
    if (a < 0xFE00) { g->bus[a - 0x2000] = v; return; } /* echo */
    if (a < 0xFEA0) { g->bus[a] = v; return; }          /* OAM */
    if (a < 0xFF00) return;                             /* prohibited */
    if (a < 0xFF80) { io_write(g, a, v); return; }
    if (a < 0xFFFF) { g->bus[a] = v; return; }          /* HRAM */
    g->bus[0xFFFF] = v;                                 /* IE */
}

void gb_joypad_press(GB *g, int button_bit, int pressed) {
    uint8_t *field = (button_bit & 0x08) ? &g->in.dpad : &g->in.buttons;
    uint8_t before = *field;
    if (pressed) *field |= (uint8_t)button_bit;
    else *field &= (uint8_t)~button_bit;
    if ((before & button_bit) != (*field & button_bit) && pressed)
        g->bus[0xFF0F] |= IF_JOYPAD;
}
