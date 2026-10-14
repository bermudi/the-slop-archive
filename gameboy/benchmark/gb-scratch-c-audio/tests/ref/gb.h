/* gbn810 - a Game Boy (DMG) emulator for the Nokia N810
 * written from scratch. no cores, no libraries, no cheating.
 *
 * gb.h - shared core types
 */
#ifndef GBN810_H
#define GBN810_H

#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#define GB_W 160
#define GB_H 144
#define GB_FRAME_CYCLES 70224        /* T-cycles per frame */
#define GB_HZ 4194304                /* master clock */

/* flags in F */
#define F_Z 0x80
#define F_N 0x40
#define F_H 0x20
#define F_C 0x10

/* interrupt bits in IF/IE */
#define IF_VBLANK 0x01
#define IF_STAT   0x02
#define IF_TIMER  0x04
#define IF_SERIAL 0x08
#define IF_JOYPAD 0x10

enum { GB_MBC_NONE = 0, GB_MBC1, GB_MBC2, GB_MBC3, GB_MBC5 };

typedef struct {
    uint8_t a, f, b, c, d, e, h, l;
    uint16_t sp, pc;
    uint8_t ime, ime_delay, halted, halt_bug;
} Cpu;

typedef struct {
    int lcd_on;
    int mode;                 /* 0 hblank, 1 vblank, 2 oam scan, 3 drawing */
    int ly, lyc;              /* current line, compare line */
    int line_dots;            /* dots elapsed in current line */
    int win_line, win_active; /* internal window line counter / WY latch */
    int off_dots;             /* dot accumulation while LCD is off */
    uint8_t px[GB_W * GB_H];  /* shade 0..3 framebuffer */
} Ppu;

typedef struct {
    uint16_t div;             /* internal 16-bit divider */
    uint8_t tima, tma, tac;
} Timer;

typedef struct {
    int mbc, battery, has_rtc;
    uint8_t *rom;
    long rom_size;
    int rom_banks;
    uint8_t *ram;
    long ram_size;
    char sav_path[512];
    int dirty;
    /* bank registers */
    int ramg;                 /* ram enable */
    int rom_low;              /* mbc1 low 5 bits / mbc3 7 bits / mbc5 low 8 */
    int bank2;                /* mbc1 secondary */
    int mode_sel;             /* mbc1 banking mode */
    int rom_bank, ram_bank;   /* mbc3/5 */
    /* mbc3 rtc */
    time_t rtc_base;          /* epoch when rtc_offset was snapshotted */
    long rtc_offset;          /* seconds accumulated before rtc_base */
    int rtc_halt;
    int rtc_carry;            /* days overflowed */
} Cart;

typedef struct {
    int enabled, dac;
    int len, len_en;
    int vol, env_period, env_timer, env_up;
    int freq, freq_timer;     /* freq_timer in M-cycles */
    int duty, duty_pos;
    int out;                  /* current 0..15 sample */
} Pulse;

typedef struct {
    int enabled, dac;
    int len, len_en;
    int freq, freq_timer;     /* freq_timer in T-cycles */
    int shift, pos;
    int out;
} Wave;

typedef struct {
    int enabled, dac;
    int len, len_en;
    int vol, env_period, env_timer, env_up;
    int freq_timer;           /* T-cycles */
    int lfsr, width7;
    int out;
    /* sweep (channel 1 only, but stored in noise struct's sibling) */
} Noise;

typedef struct {
    /* channel 1 sweep */
    int sw_period, sw_timer, sw_shift, sw_neg, sw_enabled, sw_shadow;
} Sweep;

#define APU_RING (1 << 16)    /* bytes, stereo u8 interleaved */

typedef struct {
    Pulse pulse[2];
    Wave wave;
    Noise noise;
    Sweep sweep;
    int powered, nr50, nr51;
    int fs_count, fs_step;    /* frame sequencer (T counter, step 0..7) */
    uint32_t acc, step_fp;    /* downsampler, 20.12 fixed point */
    int lp_l, lp_r;           /* one-pole lowpass state */
    uint8_t ring[APU_RING];
    int rh, rt;               /* ring write/read offsets */
} Apu;

typedef struct {
    /* bit layout matches FF00 read nibbles, 1 = pressed */
    uint8_t buttons;          /* bit0 A, 1 B, 2 Select, 3 Start */
    uint8_t dpad;             /* bit0 Right, 1 Left, 2 Up, 3 Down */
    uint8_t select;           /* last value written to FF00 */
    int quit;
} Input;

struct GB {
    Cpu cpu;
    Ppu ppu;
    Timer timer;
    Cart cart;
    Apu apu;
    Input in;
    uint8_t bus[0x10000];     /* everything that is not cartridge space */
    int frame_done;
    long frame_no;
    long serial_delay;
    void (*on_serial)(struct GB *, uint8_t);
};

typedef struct GB GB;

/* core */
void gb_init(GB *g);
void gb_boot(GB *g);                      /* post-boot register state */
int  gb_load_rom(GB *g, const char *path);/* 0 on success */
void gb_save(GB *g);
void gb_run_frame(GB *g);
void gb_tick(GB *g, int cycles);          /* advance all components */
int  cpu_step(GB *g);                     /* returns T-cycles consumed */

/* mmu.c */
uint8_t gb_rd(GB *g, uint16_t a);
void gb_wr(GB *g, uint16_t a, uint8_t v);
void gb_joypad_press(GB *g, int button_bit, int pressed);

/* apu.c */
void apu_write(GB *g, uint16_t a, uint8_t v);
void apu_init(GB *g);
void apu_tick(GB *g, int m_cycles);
int  apu_pull(GB *g, uint8_t *dst, int max_bytes);

/* ppu.c */
void ppu_tick(GB *g, int cycles);

/* timer.c */
void timer_tick(GB *g, int cycles);

#endif
