/* cpu.c - Sharp LR35902 interpreter, written from scratch.
 *
 * Every bus access ticks the machine 4 T-cycles *before* the access, and
 * internal cycles are ticked explicitly, so timers/PPU/APU advance in step
 * with the instruction stream (no cycle fudging at instruction end).
 */
#include "gb.h"

/* ---- bus helpers (each access costs 4 T-cycles) ---- */

static uint8_t fetch8(GB *g) {
    uint8_t v;
    if (g->cpu.halt_bug) {
        g->cpu.halt_bug = 0;
        v = gb_rd(g, g->cpu.pc);
        gb_tick(g, 4);
        return v;
    }
    v = gb_rd(g, g->cpu.pc++);
    gb_tick(g, 4);
    return v;
}

static uint16_t fetch16(GB *g) {
    uint16_t lo = fetch8(g);
    uint16_t hi = fetch8(g);
    return (uint16_t)(lo | (hi << 8));
}

static void push16(GB *g, uint16_t v) {
    gb_tick(g, 4);                       /* internal decrement */
    gb_tick(g, 4);                       /* stack write hi */
    gb_wr(g, --g->cpu.sp, (uint8_t)(v >> 8));
    gb_tick(g, 4);                       /* stack write lo */
    gb_wr(g, --g->cpu.sp, (uint8_t)(v & 0xFF));
}

static uint16_t pop16(GB *g) {
    uint16_t lo = gb_rd(g, g->cpu.sp++);
    gb_tick(g, 4);                       /* stack read lo */
    uint16_t hi = gb_rd(g, g->cpu.sp++);
    gb_tick(g, 4);                       /* stack read hi */
    return (uint16_t)(lo | (hi << 8));
}

/* ---- register file by opcode index (B C D E H L (HL) A) ---- */

static uint8_t get_r(GB *g, int i) {
    Cpu *c = &g->cpu;
    switch (i) {
    case 0: return c->b;
    case 1: return c->c;
    case 2: return c->d;
    case 3: return c->e;
    case 4: return c->h;
    case 5: return c->l;
    case 6: { uint8_t v = gb_rd(g, (uint16_t)((c->h << 8) | c->l)); gb_tick(g, 4); return v; }
    default: return c->a;
    }
}

static void set_r(GB *g, int i, uint8_t v) {
    Cpu *c = &g->cpu;
    switch (i) {
    case 0: c->b = v; break;
    case 1: c->c = v; break;
    case 2: c->d = v; break;
    case 3: c->e = v; break;
    case 4: c->h = v; break;
    case 5: c->l = v; break;
    case 6: gb_tick(g, 4); gb_wr(g, (uint16_t)((c->h << 8) | c->l), v); break;
    default: c->a = v; break;
    }
}

static uint16_t get_rr(GB *g, int i) {
    Cpu *c = &g->cpu;
    switch (i) {
    case 0: return (uint16_t)((c->b << 8) | c->c);
    case 1: return (uint16_t)((c->d << 8) | c->e);
    case 2: return (uint16_t)((c->h << 8) | c->l);
    default: return c->sp;
    }
}

static void set_rr(GB *g, int i, uint16_t v) {
    Cpu *c = &g->cpu;
    switch (i) {
    case 0: c->b = (uint8_t)(v >> 8); c->c = (uint8_t)v; break;
    case 1: c->d = (uint8_t)(v >> 8); c->e = (uint8_t)v; break;
    case 2: c->h = (uint8_t)(v >> 8); c->l = (uint8_t)v; break;
    default: c->sp = v; break;
    }
}

/* ---- 8-bit ALU ---- */

static uint8_t alu_add(GB *g, uint8_t a, uint8_t b, int usecarry) {
    int cy = (usecarry && (g->cpu.f & F_C)) ? 1 : 0;
    int r = a + b + cy;
    uint8_t f = 0;
    if ((uint8_t)r == 0) f |= F_Z;
    if (((a & 0xF) + (b & 0xF) + cy) > 0xF) f |= F_H;
    if (r > 0xFF) f |= F_C;
    g->cpu.f = f;
    return (uint8_t)r;
}

static uint8_t alu_sub(GB *g, uint8_t a, uint8_t b, int usecarry, int store) {
    int cy = (usecarry && (g->cpu.f & F_C)) ? 1 : 0;
    int r = a - b - cy;
    uint8_t f = F_N;
    if ((uint8_t)r == 0) f |= F_Z;
    if (((a & 0xF) - (b & 0xF) - cy) < 0) f |= F_H;
    if (r < 0) f |= F_C;
    g->cpu.f = f;
    return store ? (uint8_t)r : a;
}

static void alu(GB *g, int op, uint8_t v) {
    switch (op) {
    case 0: g->cpu.a = alu_add(g, g->cpu.a, v, 0); break;   /* ADD */
    case 1: g->cpu.a = alu_add(g, g->cpu.a, v, 1); break;   /* ADC */
    case 2: g->cpu.a = alu_sub(g, g->cpu.a, v, 0, 1); break;/* SUB */
    case 3: g->cpu.a = alu_sub(g, g->cpu.a, v, 1, 1); break;/* SBC */
    case 4: g->cpu.a &= v; g->cpu.f = (uint8_t)((g->cpu.a ? 0 : F_Z) | F_H); break;
    case 5: g->cpu.a ^= v; g->cpu.f = (uint8_t)(g->cpu.a ? 0 : F_Z); break;
    case 6: g->cpu.a |= v; g->cpu.f = (uint8_t)(g->cpu.a ? 0 : F_Z); break;
    default: alu_sub(g, g->cpu.a, v, 0, 0); break;          /* CP */
    }
}

static uint8_t inc8(GB *g, uint8_t v) {
    uint8_t f = g->cpu.f & F_C;
    if ((uint8_t)(v + 1) == 0) f |= F_Z;
    if ((v & 0xF) == 0xF) f |= F_H;
    g->cpu.f = f;
    return (uint8_t)(v + 1);
}

static uint8_t dec8(GB *g, uint8_t v) {
    uint8_t f = (uint8_t)((g->cpu.f & F_C) | F_N);
    if ((uint8_t)(v - 1) == 0) f |= F_Z;
    if ((v & 0xF) == 0) f |= F_H;
    g->cpu.f = f;
    return (uint8_t)(v - 1);
}

/* ---- rotates / shifts ---- */

static uint8_t op_rlc(GB *g, uint8_t v) {
    uint8_t c = (uint8_t)((v >> 7) & 1);
    v = (uint8_t)((v << 1) | c);
    g->cpu.f = (uint8_t)((v ? 0 : F_Z) | (c ? F_C : 0));
    return v;
}

static uint8_t op_rrc(GB *g, uint8_t v) {
    uint8_t c = (uint8_t)(v & 1);
    v = (uint8_t)((v >> 1) | (c << 7));
    g->cpu.f = (uint8_t)((v ? 0 : F_Z) | (c ? F_C : 0));
    return v;
}

static uint8_t op_rl(GB *g, uint8_t v) {
    uint8_t oc = (uint8_t)((g->cpu.f & F_C) ? 1 : 0);
    uint8_t c = (uint8_t)((v >> 7) & 1);
    v = (uint8_t)((v << 1) | oc);
    g->cpu.f = (uint8_t)((v ? 0 : F_Z) | (c ? F_C : 0));
    return v;
}

static uint8_t op_rr(GB *g, uint8_t v) {
    uint8_t oc = (uint8_t)((g->cpu.f & F_C) ? 1 : 0);
    uint8_t c = (uint8_t)(v & 1);
    v = (uint8_t)((v >> 1) | (oc << 7));
    g->cpu.f = (uint8_t)((v ? 0 : F_Z) | (c ? F_C : 0));
    return v;
}

static uint8_t op_sla(GB *g, uint8_t v) {
    uint8_t c = (uint8_t)((v >> 7) & 1);
    v = (uint8_t)(v << 1);
    g->cpu.f = (uint8_t)((v ? 0 : F_Z) | (c ? F_C : 0));
    return v;
}

static uint8_t op_sra(GB *g, uint8_t v) {
    uint8_t c = (uint8_t)(v & 1);
    v = (uint8_t)((v >> 1) | (v & 0x80));
    g->cpu.f = (uint8_t)((v ? 0 : F_Z) | (c ? F_C : 0));
    return v;
}

static uint8_t op_srl(GB *g, uint8_t v) {
    uint8_t c = (uint8_t)(v & 1);
    v = (uint8_t)(v >> 1);
    g->cpu.f = (uint8_t)((v ? 0 : F_Z) | (c ? F_C : 0));
    return v;
}

static uint8_t op_swap(GB *g, uint8_t v) {
    v = (uint8_t)((v >> 4) | (v << 4));
    g->cpu.f = (uint8_t)(v ? 0 : F_Z);
    return v;
}

/* SM83 hardware DAA (verified against blargg 01-special/11):
 * 16-bit result; C = bit 8 of the result (never cleared, only set);
 * add-branch threshold is 0x9F; subtract branch uses only H and C. */
static void op_daa(GB *g) {
    int16_t result = g->cpu.a;
    uint8_t f = g->cpu.f;
    if (f & F_N) {
        if (f & F_H) result = (int16_t)((result - 6) & 0xFF);
        if (f & F_C) result = (int16_t)(result - 0x60);
    } else {
        if ((f & F_H) || (result & 0x0F) > 9) result = (int16_t)(result + 6);
        if ((f & F_C) || result > 0x9F) result = (int16_t)(result + 0x60);
    }
    f &= (uint8_t)~F_H;
    f &= (uint8_t)~F_Z;
    if ((result & 0xFF) == 0) f |= F_Z;
    if (result & 0x100) f |= F_C;
    g->cpu.f = f;
    g->cpu.a = (uint8_t)result;
}

/* conditions: 0 NZ, 1 Z, 2 NC, 3 C */
static int cond(GB *g, int i) {
    switch (i) {
    case 0: return !(g->cpu.f & F_Z);
    case 1: return (g->cpu.f & F_Z) != 0;
    case 2: return !(g->cpu.f & F_C);
    default: return (g->cpu.f & F_C) != 0;
    }
}

/* 16-bit ops */
static void add_hl(GB *g, uint16_t v) {
    uint16_t hl = get_rr(g, 2);
    uint32_t r = (uint32_t)hl + v;
    uint8_t f = g->cpu.f & F_Z;
    if (((hl & 0xFFF) + (v & 0xFFF)) > 0xFFF) f |= F_H;
    if (r > 0xFFFF) f |= F_C;
    g->cpu.f = f;
    set_rr(g, 2, (uint16_t)r);
}

/* used by ADD SP,e8 and LD HL,SP+e8: Z=0 N=0, H/C on unsigned low-byte math */
static uint16_t sp_off(GB *g, uint8_t e) {
    uint16_t sp = g->cpu.sp;
    uint8_t f = 0;
    if (((sp & 0xF) + (e & 0xF)) > 0xF) f |= F_H;
    if (((sp & 0xFF) + (e & 0xFF)) > 0xFF) f |= F_C;
    g->cpu.f = f;
    return (uint16_t)(sp + (int8_t)e);
}

static int service_interrupts(GB *g) {
    uint8_t pending = (uint8_t)(g->bus[0xFF0F] & g->bus[0xFFFF]);
    if (!pending || !g->cpu.ime) return 0;
    for (int i = 0; i < 5; i++) {
        if (pending & (1 << i)) {
            g->cpu.ime = 0;
            g->cpu.ime_delay = 0;
            g->bus[0xFF0F] &= (uint8_t)~(1 << i);
            gb_tick(g, 8);               /* 2 internal M-cycles */
            push16(g, g->cpu.pc);
            g->cpu.pc = (uint16_t)(0x40 + i * 8);
            return 20;
        }
    }
    return 0;
}

static int illegal_warned = 0;

/* CB prefix: rotates/shifts/swap, BIT, RES, SET */
static int cb_prefix(GB *g, uint8_t op) {
    int reg = op & 7;
    int hl = (reg == 6);
    uint8_t v;

    if (op < 0x40) {
        v = get_r(g, reg);
        switch (op >> 3) {
        case 0: v = op_rlc(g, v); break;
        case 1: v = op_rrc(g, v); break;
        case 2: v = op_rl(g, v); break;
        case 3: v = op_rr(g, v); break;
        case 4: v = op_sla(g, v); break;
        case 5: v = op_sra(g, v); break;
        case 6: v = op_swap(g, v); break;
        default: v = op_srl(g, v); break;
        }
        set_r(g, reg, v);
        return 8 + hl * 8;
    } else if (op < 0x80) {              /* BIT n,r */
        v = get_r(g, reg);
        int bit = (op >> 3) & 7;
        g->cpu.f = (uint8_t)((g->cpu.f & F_C) | F_H);
        if (!((v >> bit) & 1)) g->cpu.f |= F_Z;
        return 8 + hl * 4;               /* BIT (HL) = 12 */
    } else {                             /* RES / SET */
        v = get_r(g, reg);
        int bit = (op >> 3) & 7;
        if (op < 0xC0) v = (uint8_t)(v & ~(1 << bit));
        else           v = (uint8_t)(v |  (1 << bit));
        set_r(g, reg, v);
        return 8 + hl * 8;
    }
}

/* ---- the interpreter: returns T-cycles consumed ---- */

int cpu_step(GB *g) {
    Cpu *c = &g->cpu;

    /* EI takes effect after the instruction that follows it */
    if (c->ime_delay > 0 && --c->ime_delay == 0)
        c->ime = 1;

    if (c->halted) {
        uint8_t pending = (uint8_t)(g->bus[0xFF0F] & g->bus[0xFFFF]);
        if (pending) {
            c->halted = 0;
            return g->cpu.ime ? service_interrupts(g) : 4;
        }
        gb_tick(g, 4);
        return 4;
    }

    int cyc = service_interrupts(g);
    if (cyc) return cyc;

    uint8_t op = fetch8(g);
    uint16_t a16;
    uint8_t v;

    switch (op) {
    /* 0x00-0x0F */
    case 0x00: return 4;                                    /* NOP */
    case 0x01: case 0x11: case 0x21: case 0x31:             /* LD rr,d16 */
        set_rr(g, (op >> 4) & 3, fetch16(g));
        return 12;
    case 0x02:                                              /* LD (BC),A */
        gb_tick(g, 4); gb_wr(g, get_rr(g, 0), c->a); return 8;
    case 0x03: case 0x13: case 0x23: case 0x33:             /* INC rr */
        gb_tick(g, 4); set_rr(g, (op >> 4) & 3, (uint16_t)(get_rr(g, (op >> 4) & 3) + 1)); return 8;
    case 0x04: case 0x0C: case 0x14: case 0x1C: case 0x24: case 0x2C: case 0x34: case 0x3C: {
        int r = (op >> 3) & 7;                              /* INC r */
        if (r == 6) { v = get_r(g, 6); set_r(g, 6, inc8(g, v)); return 12; }
        set_r(g, r, inc8(g, get_r(g, r))); return 4;
    }
    case 0x05: case 0x0D: case 0x15: case 0x1D: case 0x25: case 0x2D: case 0x35: case 0x3D: {
        int r = (op >> 3) & 7;                              /* DEC r */
        if (r == 6) { v = get_r(g, 6); set_r(g, 6, dec8(g, v)); return 12; }
        set_r(g, r, dec8(g, get_r(g, r))); return 4;
    }
    case 0x06: case 0x0E: case 0x16: case 0x1E: case 0x26: case 0x2E: case 0x36: case 0x3E:
        set_r(g, (op >> 3) & 7, fetch8(g)); return 8;       /* LD r,d8 */
    case 0x07: c->a = op_rlc(g, c->a); c->f &= (uint8_t)~F_Z; return 4; /* RLCA: Z always reset (SM83 quirk) */
    case 0x08:                                              /* LD (a16),SP */
        a16 = fetch16(g);
        gb_tick(g, 4);
        gb_wr(g, a16, (uint8_t)(c->sp & 0xFF));
        gb_tick(g, 4);
        gb_wr(g, (uint16_t)(a16 + 1), (uint8_t)(c->sp >> 8));
        return 20;
    case 0x09: case 0x19: case 0x29: case 0x39:             /* ADD HL,rr */
        gb_tick(g, 4); add_hl(g, get_rr(g, (op >> 4) & 3)); return 8;
    case 0x0A:                                              /* LD A,(BC) */
        c->a = gb_rd(g, get_rr(g, 0)); gb_tick(g, 4); return 8;
    case 0x0B: case 0x1B: case 0x2B: case 0x3B:             /* DEC rr */
        gb_tick(g, 4); set_rr(g, (op >> 4) & 3, (uint16_t)(get_rr(g, (op >> 4) & 3) - 1)); return 8;
    case 0x0F: c->a = op_rrc(g, c->a); c->f &= (uint8_t)~F_Z; return 4; /* RRCA: Z always reset (SM83 quirk) */

    /* 0x10-0x1F */
    case 0x10: fetch8(g); return 8;                         /* STOP (speed switch unsupported) */
    case 0x12:                                              /* LD (DE),A */
        gb_tick(g, 4); gb_wr(g, get_rr(g, 1), c->a); return 8;
    case 0x17: c->a = op_rl(g, c->a); c->f &= (uint8_t)~F_Z; return 4; /* RLA: Z always reset (SM83 quirk) */
    case 0x18: { int8_t e = (int8_t)fetch8(g); gb_tick(g, 4); c->pc = (uint16_t)(c->pc + e); return 12; }
    case 0x1A:                                              /* LD A,(DE) */
        c->a = gb_rd(g, get_rr(g, 1)); gb_tick(g, 4); return 8;
    case 0x2A:                                              /* LD A,(HL+) */
        c->a = gb_rd(g, get_rr(g, 2)); set_rr(g, 2, (uint16_t)(get_rr(g, 2) + 1)); gb_tick(g, 4); return 8;
    case 0x3A:                                              /* LD A,(HL-) */
        c->a = gb_rd(g, get_rr(g, 2)); set_rr(g, 2, (uint16_t)(get_rr(g, 2) - 1)); gb_tick(g, 4); return 8;
    case 0x1F: c->a = op_rr(g, c->a); c->f &= (uint8_t)~F_Z; return 4; /* RRA: Z always reset (SM83 quirk) */

    /* 0x20-0x2F */
    case 0x20: case 0x28: case 0x30: case 0x38: {           /* JR cc */
        int8_t e = (int8_t)fetch8(g);
        if (cond(g, (op >> 3) & 3)) { gb_tick(g, 4); c->pc = (uint16_t)(c->pc + e); return 12; }
        return 8;
    }
    case 0x22:                                              /* LD (HL+),A */
        gb_tick(g, 4); gb_wr(g, get_rr(g, 2), c->a); set_rr(g, 2, (uint16_t)(get_rr(g, 2) + 1)); return 8;
    case 0x27: op_daa(g); return 4;                         /* DAA */
    case 0x2F: c->a = (uint8_t)~c->a; c->f |= F_N | F_H; return 4; /* CPL */

    /* 0x30-0x3F */
    case 0x32:                                              /* LD (HL-),A */
        gb_tick(g, 4); gb_wr(g, get_rr(g, 2), c->a); set_rr(g, 2, (uint16_t)(get_rr(g, 2) - 1)); return 8;
    case 0x37: c->f = (uint8_t)((c->f & F_Z) | F_C); return 4;      /* SCF */
    case 0x3F: c->f = (uint8_t)((c->f & (F_Z | F_C)) ^ F_C); return 4; /* CCF */

    /* 0x40-0x7F: LD r,r' (0x76 HALT just below) */
    case 0x76:                                              /* HALT */
        c->halted = 1;
        if (((g->bus[0xFF0F] & g->bus[0xFFFF]) != 0) && !c->ime)
            c->halt_bug = 1;    /* HALT bug: IME=0 with pending interrupt */
        return 4;
    case 0x40: case 0x41: case 0x42: case 0x43: case 0x44: case 0x45: case 0x46: case 0x47:
    case 0x48: case 0x49: case 0x4A: case 0x4B: case 0x4C: case 0x4D: case 0x4E: case 0x4F:
    case 0x50: case 0x51: case 0x52: case 0x53: case 0x54: case 0x55: case 0x56: case 0x57:
    case 0x58: case 0x59: case 0x5A: case 0x5B: case 0x5C: case 0x5D: case 0x5E: case 0x5F:
    case 0x60: case 0x61: case 0x62: case 0x63: case 0x64: case 0x65: case 0x66: case 0x67:
    case 0x68: case 0x69: case 0x6A: case 0x6B: case 0x6C: case 0x6D: case 0x6E: case 0x6F:
    case 0x70: case 0x71: case 0x72: case 0x73: case 0x74: case 0x75: case 0x77:
    case 0x78: case 0x79: case 0x7A: case 0x7B: case 0x7C: case 0x7D: case 0x7E: case 0x7F: {
        int src = op & 7, dst = (op >> 3) & 7;
        v = get_r(g, src);
        if (dst == 6) { gb_tick(g, 4); gb_wr(g, get_rr(g, 2), v); return 8 + (src == 6 ? 4 : 0); }
        set_r(g, dst, v);
        return 4 + (src == 6 ? 4 : 0);
    }

    /* 0x80-0xBF: ALU A,r */
    case 0x80: case 0x81: case 0x82: case 0x83: case 0x84: case 0x85: case 0x86: case 0x87:
    case 0x88: case 0x89: case 0x8A: case 0x8B: case 0x8C: case 0x8D: case 0x8E: case 0x8F:
    case 0x90: case 0x91: case 0x92: case 0x93: case 0x94: case 0x95: case 0x96: case 0x97:
    case 0x98: case 0x99: case 0x9A: case 0x9B: case 0x9C: case 0x9D: case 0x9E: case 0x9F:
    case 0xA0: case 0xA1: case 0xA2: case 0xA3: case 0xA4: case 0xA5: case 0xA6: case 0xA7:
    case 0xA8: case 0xA9: case 0xAA: case 0xAB: case 0xAC: case 0xAD: case 0xAE: case 0xAF:
    case 0xB0: case 0xB1: case 0xB2: case 0xB3: case 0xB4: case 0xB5: case 0xB6: case 0xB7:
    case 0xB8: case 0xB9: case 0xBA: case 0xBB: case 0xBC: case 0xBD: case 0xBE: case 0xBF: {
        v = get_r(g, op & 7);
        alu(g, (op >> 3) & 7, v);
        return 4 + ((op & 7) == 6 ? 4 : 0);
    }

    /* 0xC0-0xCF */
    case 0xC0: case 0xC8: case 0xD0: case 0xD8:             /* RET cc */
        gb_tick(g, 4);
        if (cond(g, (op >> 3) & 3)) { c->pc = pop16(g); gb_tick(g, 4); return 20; }
        return 8;
    case 0xC1: case 0xD1: case 0xE1: case 0xF1: {           /* POP rr */
        uint16_t w = pop16(g);
        int i = (op >> 4) & 3;         /* C1->BC(0) D1->DE(1) E1->HL(2) F1->AF(3) */
        if (i == 3) { c->a = (uint8_t)(w >> 8); c->f = (uint8_t)(w & 0xF0); }
        else set_rr(g, i, w);
        return 12;
    }
    case 0xC2: case 0xCA: case 0xD2: case 0xDA:             /* JP cc */
        a16 = fetch16(g);
        if (cond(g, (op >> 3) & 3)) { gb_tick(g, 4); c->pc = a16; return 16; }
        return 12;
    case 0xC3:                                              /* JP a16 */
        a16 = fetch16(g); gb_tick(g, 4); c->pc = a16; return 16;
    case 0xC4: case 0xCC: case 0xD4: case 0xDC:             /* CALL cc */
        a16 = fetch16(g);
        if (cond(g, (op >> 3) & 3)) { push16(g, c->pc); c->pc = a16; return 24; }
        return 12;
    case 0xC5: case 0xD5: case 0xE5: case 0xF5: {           /* PUSH rr */
        int i = (op >> 4) & 3;
        uint16_t w = (i == 3) ? (uint16_t)((c->a << 8) | (c->f & 0xF0)) : get_rr(g, i);
        push16(g, w);
        return 16;
    }
    case 0xC6: case 0xCE: case 0xD6: case 0xDE:
    case 0xE6: case 0xEE: case 0xF6: case 0xFE:             /* alu A,d8 */
        alu(g, (op >> 3) & 7, fetch8(g)); return 8;
    case 0xC7: case 0xCF: case 0xD7: case 0xDF:
    case 0xE7: case 0xEF: case 0xF7: case 0xFF:             /* RST vec */
        push16(g, c->pc);
        c->pc = (uint16_t)((op & 0x38)); return 16;

    /* 0xD0-0xDF */
    case 0xC9:                                              /* RET */
        c->pc = pop16(g); gb_tick(g, 4); return 16;
    case 0xD9:                                              /* RETI */
        c->pc = pop16(g); gb_tick(g, 4);
        c->ime = 1; c->ime_delay = 0;
        return 16;
    case 0xCB:
        v = fetch8(g);
        return 4 + cb_prefix(g, v);

    /* 0xE0-0xEF */
    case 0xCD:                                              /* CALL a16 */
        a16 = fetch16(g); push16(g, c->pc); c->pc = a16; return 24;
    case 0xE0:                                              /* LDH (a8),A */
        a16 = fetch8(g); gb_tick(g, 4); gb_wr(g, (uint16_t)(0xFF00 + a16), c->a); return 12;
    case 0xE2:                                              /* LD (C),A */
        gb_tick(g, 4); gb_wr(g, (uint16_t)(0xFF00 + c->c), c->a); return 8;
    case 0xE8:                                              /* ADD SP,e8 */
        v = fetch8(g); gb_tick(g, 4); gb_tick(g, 4); c->sp = sp_off(g, v); return 16;
    case 0xE9: c->pc = get_rr(g, 2); return 4;              /* JP HL */
    case 0xEA:                                              /* LD (a16),A */
        a16 = fetch16(g); gb_tick(g, 4); gb_wr(g, a16, c->a); return 16;

    /* 0xF0-0xFF */
    case 0xF0:                                              /* LDH A,(a8) */
        a16 = fetch8(g); c->a = gb_rd(g, (uint16_t)(0xFF00 + a16)); gb_tick(g, 4); return 12;
    case 0xF2:                                              /* LD A,(C) */
        c->a = gb_rd(g, (uint16_t)(0xFF00 + c->c)); gb_tick(g, 4); return 8;
    case 0xF3: c->ime = 0; c->ime_delay = 0; return 4;      /* DI */
    case 0xF8:                                              /* LD HL,SP+e8 */
        v = fetch8(g); gb_tick(g, 4); set_rr(g, 2, sp_off(g, v)); return 12;
    case 0xF9: gb_tick(g, 4); c->sp = get_rr(g, 2); return 8; /* LD SP,HL */
    case 0xFA:                                              /* LD A,(a16) */
        a16 = fetch16(g); c->a = gb_rd(g, a16); gb_tick(g, 4); return 16;
    case 0xFB: c->ime_delay = 2; return 4;                  /* EI */

    default:                                                /* illegal opcodes */
        if (!illegal_warned) {
            fprintf(stderr, "gbn810: illegal opcode 0x%02X at 0x%04X\n", op, c->pc - 1);
            illegal_warned = 1;
        }
        return 4;
    }
}
