/* apu.c - DMG audio: 2 pulse (sweep/envelope), wave, noise (LFSR).
 * Integer-only (no floats: the N810's ARM1136 runs soft-float userland).
 * Channels are clocked per machine cycle; output is downsampled to a ring
 * buffer with a 20.12 fixed-point accumulator and a one-pole lowpass.
 */
#include "gb.h"

static const uint8_t duty_masks[4] = {0x80, 0x81, 0xE1, 0x7E};
static const int noise_div[8] = {8, 16, 32, 64, 128, 256, 512, 1024};

static int dac_pulse(uint8_t nrx2) { return (nrx2 & 0xF8) != 0; }

static void length_clock(int *enabled, int *len, int len_en) {
    if (len_en && *len > 0 && --*len == 0) *enabled = 0;
}

static void env_clock(Pulse *p) {
    if (p->env_period == 0) return;
    if (p->env_timer > 0) p->env_timer--;
    if (p->env_timer == 0) {
        p->env_timer = p->env_period;
        if (p->env_up && p->vol < 15) p->vol++;
        else if (!p->env_up && p->vol > 0) p->vol--;
    }
}

static void env_load(Pulse *p, uint8_t nrx2) {
    p->vol = nrx2 >> 4;
    p->env_up = nrx2 & 0x08;
    p->env_period = nrx2 & 0x07;
    p->env_timer = p->env_period;
}

/* ---- channel 1 sweep ---- */

static int sweep_calc(GB *g, int apply) {
    Apu *a = &g->apu;
    int nf = a->sweep.sw_shadow >> a->sweep.sw_shift;
    nf = a->sweep.sw_neg ? a->sweep.sw_shadow - nf : a->sweep.sw_shadow + nf;
    if (apply) {
        a->sweep.sw_shadow = nf;
        g->apu.pulse[0].freq = nf & 0x7FF;
    }
    return nf;
}

static void sweep_trigger(GB *g) {
    Apu *a = &g->apu;
    a->sweep.sw_shadow = a->pulse[0].freq;
    a->sweep.sw_timer = a->sweep.sw_period ? a->sweep.sw_period : 8;
    a->sweep.sw_enabled = (a->sweep.sw_period > 0) || (a->sweep.sw_shift > 0);
    if (a->sweep.sw_shift > 0 && sweep_calc(g, 0) > 2047)
        a->pulse[0].enabled = 0;
}

static void sweep_clock(GB *g) {
    Apu *a = &g->apu;
    if (a->sweep.sw_timer > 0) a->sweep.sw_timer--;
    if (a->sweep.sw_timer != 0) return;
    a->sweep.sw_timer = a->sweep.sw_period ? a->sweep.sw_period : 8;
    if (a->sweep.sw_enabled && a->sweep.sw_period) {
        int nf = sweep_calc(g, 0);
        if (nf > 2047) {
            a->pulse[0].enabled = 0;
        } else if (a->sweep.sw_shift > 0) {
            sweep_calc(g, 1);
            if (sweep_calc(g, 0) > 2047) a->pulse[0].enabled = 0;
        }
    }
}

/* ---- triggers ---- */

static void pulse_trigger(GB *g, int ch) {
    Pulse *p = &g->apu.pulse[ch];
    p->dac = dac_pulse(g->bus[0xFF12 + ch * 5]);
    p->enabled = p->dac;
    p->duty_pos = 0;
    p->freq_timer = 2048 - p->freq;
    if (p->len == 0) p->len = 64;
    env_load(p, g->bus[0xFF12 + ch * 5]);
    if (ch == 0) sweep_trigger(g);
}

static void wave_trigger(GB *g) {
    Wave *w = &g->apu.wave;
    w->dac = (g->bus[0xFF1A] & 0x80) != 0;
    w->enabled = w->dac;
    w->pos = 0;
    w->freq_timer = (2048 - w->freq) * 2;
    if (w->len == 0) w->len = 256;
}

static void noise_trigger(GB *g) {
    Noise *n = &g->apu.noise;
    n->dac = dac_pulse(g->bus[0xFF21]);
    n->enabled = n->dac;
    n->lfsr = 0x7FFF;
    if (n->len == 0) n->len = 64;
    env_load((Pulse *)n, g->bus[0xFF21]);   /* env fields are laid out identically */
}

/* ---- register writes ---- */

void apu_write(GB *g, uint16_t a, uint8_t v) {
    Apu *ap = &g->apu;

    if (a == 0xFF26) {                       /* NR52 power */
        int was = ap->powered;
        ap->powered = v & 0x80;
        if (was && !ap->powered) {
            memset(ap->pulse, 0, sizeof ap->pulse);
            memset(&ap->wave, 0, sizeof ap->wave);
            memset(&ap->noise, 0, sizeof ap->noise);
            memset(&ap->sweep, 0, sizeof ap->sweep);
            ap->nr50 = ap->nr51 = 0;
            for (int i = 0xFF10; i < 0xFF26; i++) g->bus[i] = 0;
        }
        g->bus[0xFF26] = (uint8_t)(0x70 | (ap->powered ? 0x80 : 0));
        return;
    }
    if (!ap->powered) return;                /* other regs ignored while off */

    switch (a) {
    case 0xFF10:                             /* NR10 sweep */
        ap->sweep.sw_period = (v >> 4) & 7;
        ap->sweep.sw_neg = v & 0x08;
        ap->sweep.sw_shift = v & 0x07;
        break;
    case 0xFF11: case 0xFF16: {              /* NRx1 duty + length */
        Pulse *p = &ap->pulse[a == 0xFF11 ? 0 : 1];
        p->duty = v >> 6;
        p->len = 64 - (v & 0x3F);
        break;
    }
    case 0xFF12: case 0xFF17: {              /* NRx2 envelope */
        Pulse *p = &ap->pulse[a == 0xFF12 ? 0 : 1];
        env_load(p, v);
        p->dac = dac_pulse(v);
        if (!p->dac) p->enabled = 0;
        break;
    }
    case 0xFF13: case 0xFF18:                /* NRx3 freq lo */
        ap->pulse[a == 0xFF13 ? 0 : 1].freq =
            (ap->pulse[a == 0xFF13 ? 0 : 1].freq & 0x700) | v;
        break;
    case 0xFF14: case 0xFF19: {              /* NRx4 trigger */
        Pulse *p = &ap->pulse[a == 0xFF14 ? 0 : 1];
        p->freq = (p->freq & 0xFF) | ((v & 7) << 8);
        p->len_en = v & 0x40;
        if (v & 0x80) pulse_trigger(g, a == 0xFF14 ? 0 : 1);
        break;
    }
    case 0xFF1A:                             /* NR30 dac */
        ap->wave.dac = v & 0x80;
        if (!ap->wave.dac) ap->wave.enabled = 0;
        break;
    case 0xFF1B: ap->wave.len = 256 - v; break;
    case 0xFF1C:                             /* NR32 volume code */
        ap->wave.shift = ((v >> 5) & 3);
        break;
    case 0xFF1D:
        ap->wave.freq = (ap->wave.freq & 0x700) | v;
        break;
    case 0xFF1E:
        ap->wave.freq = (ap->wave.freq & 0xFF) | ((v & 7) << 8);
        ap->wave.len_en = v & 0x40;
        if (v & 0x80) wave_trigger(g);
        break;
    case 0xFF20: ap->noise.len = 64 - (v & 0x3F); break;
    case 0xFF21:
        env_load((Pulse *)&ap->noise, v);
        ap->noise.dac = dac_pulse(v);
        if (!ap->noise.dac) ap->noise.enabled = 0;
        break;
    case 0xFF22: {                           /* NR43 */
        ap->noise.width7 = v & 0x08;
        int s = (v >> 4) & 7;
        int div = noise_div[v & 7];
        ap->noise.freq_timer = div << s;
        break;
    }
    case 0xFF23:                             /* NR44 */
        ap->noise.len_en = v & 0x40;
        if (v & 0x80) noise_trigger(g);
        break;
    case 0xFF24: ap->nr50 = v; break;
    case 0xFF25: ap->nr51 = v; break;
    default: break;                          /* wave ram handled by bus */
    }
    g->bus[a] = v;
}

/* ---- per-machine-cycle tick ---- */

static void emit_sample(GB *g) {
    Apu *ap = &g->apu;
    int l = 0, r = 0;
    if (ap->powered) {
        for (int ch = 0; ch < 2; ch++) {
            Pulse *p = &ap->pulse[ch];
            if (!p->enabled || !p->dac) continue;
            int s = ((duty_masks[p->duty] >> p->duty_pos) & 1) * p->vol;
            if (ap->nr51 & (1 << ch)) r += s;
            if (ap->nr51 & (0x10 << ch)) l += s;
        }
        if (ap->wave.enabled && ap->wave.dac) {
            uint8_t byte = g->bus[0xFF30 + (ap->wave.pos >> 1)];
            int nib = (ap->wave.pos & 1) ? (byte & 0xF) : (byte >> 4);
            int code = ap->wave.shift;
            int s = (code == 0) ? 0 : (nib >> (code - 1));
            if (ap->nr51 & 0x04) r += s;
            if (ap->nr51 & 0x40) l += s;
        }
        Noise *n = &ap->noise;
        if (n->enabled && n->dac) {
            int s = ((~n->lfsr) & 1) * n->vol;
            if (ap->nr51 & 0x08) r += s;
            if (ap->nr51 & 0x80) l += s;
        }
    }
    int vl = ((ap->nr50 >> 4) & 7) + 1, vr = (ap->nr50 & 7) + 1;
    int sl = 128 + (l * vl - 240) / 2;
    int sr = 128 + (r * vr - 240) / 2;
    ap->lp_l += (sl - ap->lp_l) >> 2;        /* one-pole lowpass */
    ap->lp_r += (sr - ap->lp_r) >> 2;
    int space = (ap->rt - ap->rh - 2) & (APU_RING - 1);
    if (space >= 2) {
        ap->ring[ap->rh] = (uint8_t)ap->lp_l;
        ap->ring[(ap->rh + 1) & (APU_RING - 1)] = (uint8_t)ap->lp_r;
        ap->rh = (ap->rh + 2) & (APU_RING - 1);
    }
}

void apu_init(GB *g) {
    g->apu.powered = 1;
    g->apu.nr50 = 0x77;
    g->apu.nr51 = 0xF3;
    g->apu.step_fp = (uint32_t)(((uint64_t)GB_HZ << 12) / 44100);
    g->apu.pulse[0].enabled = 0;             /* boot: silent */
    g->apu.lp_l = g->apu.lp_r = 128;
    g->bus[0xFF24] = 0x77;
    g->bus[0xFF25] = 0xF3;
    g->bus[0xFF26] = 0xF1;
}

void apu_tick(GB *g, int m_cycles) {
    Apu *ap = &g->apu;
    for (int i = 0; i < m_cycles; i++) {
        if (ap->powered) {
            /* frame sequencer: 512 Hz, 8 steps */
            ap->fs_count += 4;
            if (ap->fs_count >= 8192) {
                ap->fs_count -= 8192;
                int step = ap->fs_step++ & 7;
                if (step == 2 || step == 6) sweep_clock(g);
                if (step == 7) {
                    env_clock(&ap->pulse[0]);
                    env_clock(&ap->pulse[1]);
                    env_clock((Pulse *)&ap->noise);
                }
                if ((step & 1) == 0) {
                    length_clock(&ap->pulse[0].enabled, &ap->pulse[0].len, ap->pulse[0].len_en);
                    length_clock(&ap->pulse[1].enabled, &ap->pulse[1].len, ap->pulse[1].len_en);
                    length_clock(&ap->wave.enabled, &ap->wave.len, ap->wave.len_en);
                    length_clock(&ap->noise.enabled, &ap->noise.len, ap->noise.len_en);
                }
            }
            /* pulses: frequency timer in M-cycles */
            for (int ch = 0; ch < 2; ch++) {
                Pulse *p = &ap->pulse[ch];
                if (--p->freq_timer <= 0) {
                    p->freq_timer += 2048 - p->freq;
                    p->duty_pos = (p->duty_pos + 1) & 7;
                }
            }
            /* wave: sample timer in T-cycles */
            Wave *w = &ap->wave;
            w->freq_timer -= 4;
            while (w->freq_timer <= 0) {
                w->freq_timer += (2048 - w->freq) * 2;
                w->pos = (w->pos + 1) & 31;
            }
            /* noise: lfsr */
            Noise *n = &ap->noise;
            n->freq_timer -= 8;
            while (n->freq_timer <= 0) {
                n->freq_timer += noise_div[g->bus[0xFF22] & 7] << ((g->bus[0xFF22] >> 4) & 7);
                int bit = (n->lfsr ^ (n->lfsr >> 1)) & 1;
                n->lfsr = (n->lfsr >> 1) | (bit << 14);
                if (n->width7) n->lfsr = (n->lfsr & ~0x40) | (bit << 6);
            }
        }
        ap->acc += 4 << 12;
        while (ap->acc >= ap->step_fp) {
            ap->acc -= ap->step_fp;
            emit_sample(g);
        }
    }
}

int apu_pull(GB *g, uint8_t *dst, int max_bytes) {
    Apu *ap = &g->apu;
    int n = 0;
    while (n + 2 <= max_bytes && ap->rt != ap->rh) {
        dst[n++] = ap->ring[ap->rt];
        ap->rt = (ap->rt + 1) & (APU_RING - 1);
    }
    return n;
}
