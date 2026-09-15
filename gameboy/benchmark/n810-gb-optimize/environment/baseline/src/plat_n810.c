/* plat_n810.c - Nokia N810 (Maemo OS2008) platform.
 *
 * Video:  /dev/fb0 raw framebuffer, integer-scaled 160x144 centered.
 * Input:  /dev/input/event* (hardware d-pad + slide-out keyboard).
 * Audio:  /dev/dsp (OSS) if available, otherwise silent.
 * No X11, no SDL, no dependencies - one static binary.
 *
 * Default controls:
 *   d-pad/arrows   -> GB d-pad      X / RightShift -> A
 *   Z / LeftShift  -> B             Enter          -> Start
 *   Backspace/Chr  -> Select        Home bezel/ESC -> quit
 *
 * Note: Xomap owns the framebuffer, so stop it first on the device:
 *   sudo gainroot
 *   /etc/init.d/xomap stop
 *   ./gbn810 game.gb
 */
#define _POSIX_C_SOURCE 199309L
#include "gb.h"
#include <fcntl.h>
#include <unistd.h>
#include <signal.h>
#include <errno.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <linux/fb.h>
#include <linux/input.h>
#include <sys/soundcard.h>
#include <time.h>

/* ---- palettes (shade 0..3 = lightest..darkest) ---- */
static const uint8_t pal_green[4][3] = {
    {0xE0, 0xF8, 0xD0}, {0x88, 0xC0, 0x70}, {0x34, 0x68, 0x56}, {0x08, 0x18, 0x20},
};
static const uint8_t pal_gray[4][3] = {
    {0xFF, 0xFF, 0xFF}, {0xAA, 0xAA, 0xAA}, {0x55, 0x55, 0x55}, {0x00, 0x00, 0x00},
};

static struct {
    int fb;
    uint8_t *fbmem;
    size_t fbsize;
    struct fb_var_screeninfo vinfo;
    uint32_t lut[4];
    int scale, ox, oy;
    int evfd[16], nev;
    int dsp;
    int has_vsync;
} P;

static volatile sig_atomic_t g_stop = 0;
static void on_term(int s) { (void)s; g_stop = 1; }

/* serial → stdout: lets the bench ROM report per-frame ticks for external
   timing measurement (each vblank the ROM emits one byte to the serial port) */
static void serial_out(GB *g, uint8_t b) { (void)g; fputc(b, stdout); fflush(stdout); }

/* ---- framebuffer ---- */

static uint32_t make_pixel(const struct fb_bitfield *bf, uint8_t c) {
    if (bf->length == 0) return 0;
    int sh = bf->length >= 8 ? 0 : 8 - bf->length;
    return ((c >> sh) & ((1u << bf->length) - 1)) << bf->offset;
}

static int fb_init(void) {
    P.fb = open("/dev/fb0", O_RDWR);
    if (P.fb < 0) { fprintf(stderr, "gbn810: cannot open /dev/fb0: %s\n", strerror(errno)); return -1; }
    struct fb_fix_screeninfo finfo;
    if (ioctl(P.fb, FBIOGET_VSCREENINFO, &P.vinfo) || ioctl(P.fb, FBIOGET_FSCREENINFO, &finfo)) {
        fprintf(stderr, "gbn810: fb ioctl failed: %s\n", strerror(errno));
        return -1;
    }
    P.fbsize = finfo.smem_len;
    P.fbmem = mmap(0, P.fbsize, PROT_READ | PROT_WRITE, MAP_SHARED, P.fb, 0);
    if (P.fbmem == MAP_FAILED) { fprintf(stderr, "gbn810: fb mmap failed\n"); return -1; }

    const uint8_t (*pal)[3] = pal_green;
    const char *p = getenv("GBN8_PALETTE");
    if (p && !strcmp(p, "gray")) pal = pal_gray;

    for (int i = 0; i < 4; i++) {
        P.lut[i] = make_pixel(&P.vinfo.red, pal[3 - i][0])
                 | make_pixel(&P.vinfo.green, pal[3 - i][1])
                 | make_pixel(&P.vinfo.blue, pal[3 - i][2]);
    }

    int w = P.vinfo.xres, h = P.vinfo.yres;
    P.scale = w / GB_W < h / GB_H ? w / GB_W : h / GB_H;
    if (P.scale > 4) P.scale = 4;
    P.ox = (w - GB_W * P.scale) / 2;
    P.oy = (h - GB_H * P.scale) / 2;

    /* blank once */
    memset(P.fbmem, 0, P.fbsize);

    printf("gbn810: fb %dx%dx%d, scale %dx, offset (%d,%d), palette %s\n",
           w, h, P.vinfo.bits_per_pixel, P.scale, P.ox, P.oy,
           pal == pal_gray ? "gray" : "green");
    return 0;
}

static void fb_present(GB *g) {
    int bpp = P.vinfo.bits_per_pixel / 8;
    int rowlen = GB_W * P.scale;
    static uint32_t row[GB_W * 4];
    int bypp = bpp < 4 ? bpp : 4;

    for (int y = 0; y < GB_H; y++) {
        const uint8_t *src = g->ppu.px + (size_t)y * GB_W;
        for (int i = 0; i < GB_W; i++) {
            uint32_t px = P.lut[src[i] & 3];
            for (int s = 0; s < P.scale; s++)
                row[i * P.scale + s] = px;
        }
        uint8_t *dst = P.fbmem + (((size_t)(P.oy + y * P.scale) * P.vinfo.xres + P.ox) * bpp);
        for (int s = 0; s < P.scale; s++, dst += (size_t)P.vinfo.xres * bpp)
            memcpy(dst, row, (size_t)rowlen * bypp);
    }
    if (P.has_vsync)
        ioctl(P.fb, FBIO_WAITFORVSYNC, 0);
}

/* ---- input ---- */

struct keymap { uint16_t code; uint8_t bit; uint8_t dpad; };
static const struct keymap keymap[] = {
    {KEY_RIGHT,      0x01, 1},
    {KEY_LEFT,       0x02, 1},
    {KEY_UP,         0x04, 1},
    {KEY_DOWN,       0x08, 1},
    {KEY_X,          0x01, 0},   /* A */
    {KEY_RIGHTSHIFT, 0x01, 0},   /* A */
    {KEY_Z,          0x02, 0},   /* B */
    {KEY_LEFTSHIFT,  0x02, 0},   /* B */
    {KEY_BACKSPACE,  0x04, 0},   /* Select */
    {KEY_COMPOSE,    0x04, 0},   /* Select (Chr) */
    {KEY_ENTER,      0x08, 0},   /* Start */
    {KEY_KPENTER,    0x08, 0},
};

static void input_handle(GB *g, uint16_t code, int value) {
    switch (code) {
    case KEY_ESC:
    case KEY_HOMEPAGE:
    case KEY_BACK:
    case KEY_MENU:
        if (value) { printf("gbn810: quit key pressed\n"); g->in.quit = 1; }
        return;
    default: break;
    }
    for (size_t i = 0; i < sizeof keymap / sizeof keymap[0]; i++) {
        if (keymap[i].code == code) {
            gb_joypad_press(g, keymap[i].bit | (keymap[i].dpad ? 0x08 : 0), value != 0);
            return;
        }
    }
}

static int input_init(void) {
    char path[32];
    for (int i = 0; i < 16 && P.nev < 16; i++) {
        snprintf(path, sizeof path, "/dev/input/event%d", i);
        int fd = open(path, O_RDONLY | O_NONBLOCK);
        if (fd >= 0) P.evfd[P.nev++] = fd;
    }
    if (P.nev == 0) fprintf(stderr, "gbn810: warning: no input devices found\n");
    else printf("gbn810: listening on %d input device(s)\n", P.nev);
    return 0;
}

static void input_poll(GB *g) {
    struct input_event ev;
    for (int i = 0; i < P.nev; i++) {
        ssize_t n;
        while ((n = read(P.evfd[i], &ev, sizeof ev)) == (ssize_t)sizeof ev) {
            if (ev.type != EV_KEY || ev.value == 2) continue;
            input_handle(g, ev.code, ev.value);
        }
    }
}

/* ---- audio (OSS) ---- */

static int audio_init(void) {
    P.dsp = open("/dev/dsp", O_WRONLY);
    if (P.dsp < 0) { printf("gbn810: no /dev/dsp, running silent\n"); return -1; }
    int fmt = AFMT_U8, ch = 2, rate = 44100, frag = (11 << 16) | 4;
    if (ioctl(P.dsp, SNDCTL_DSP_SETFMT, &fmt) < 0 || fmt != AFMT_U8 ||
        ioctl(P.dsp, SNDCTL_DSP_STEREO, &ch) < 0 ||
        ioctl(P.dsp, SNDCTL_DSP_SPEED, &rate) < 0) {
        fprintf(stderr, "gbn810: /dev/dsp rejected settings, running silent\n");
        close(P.dsp);
        P.dsp = -1;
        return -1;
    }
    ioctl(P.dsp, SNDCTL_DSP_SETFRAGMENT, &frag);
    printf("gbn810: audio on /dev/dsp, %d Hz u8 stereo\n", rate);
    return 0;
}

static void audio_drain(GB *g) {
    if (P.dsp < 0) return;
    uint8_t buf[4096];
    int n;
    while ((n = apu_pull(g, buf, sizeof buf)) > 0) {
        int off = 0;
        while (off < n) {
            ssize_t w = write(P.dsp, buf + off, (size_t)(n - off));
            if (w <= 0) return;
            off += (int)w;
        }
    }
}

/* ---- pacing: 59.7275 frames/s ---- */

static void pace_init(struct timespec *next) {
    clock_gettime(CLOCK_MONOTONIC, next);
}

static void pace_wait(struct timespec *next) {
    const long frame_ns = 16743000;   /* 1e9 / 59.7275 */
    (*next).tv_nsec += frame_ns;
    while ((*next).tv_nsec >= 1000000000L) {
        (*next).tv_nsec -= 1000000000L;
        (*next).tv_sec++;
    }
    clock_nanosleep(CLOCK_MONOTONIC, TIMER_ABSTIME, next, NULL);
}

int main(int argc, char **argv) {
    const char *rom = NULL;
    int mute = 0;
    for (int i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "--mute")) mute = 1;
        else if (argv[i][0] == '-' && argv[i][1]) { fprintf(stderr, "usage: gbn810 <rom.gb> [--mute]\n"); return 2; }
        else rom = argv[i];
    }
    if (!rom) { fprintf(stderr, "usage: gbn810 <rom.gb> [--mute]\n"); return 2; }

    GB *g = calloc(1, sizeof *g);
    gb_init(g);
    gb_boot(g);
    g->on_serial = serial_out;

    if (gb_load_rom(g, rom) != 0) return 1;

    signal(SIGINT, on_term);
    signal(SIGTERM, on_term);

    if (fb_init() != 0) return 1;
    input_init();
    if (!mute) audio_init();

    struct timespec next;
    pace_init(&next);
    while (!g->in.quit && !g_stop) {
        gb_run_frame(g);
        input_poll(g);
        fb_present(g);
        audio_drain(g);
        pace_wait(&next);
    }

    gb_save(g);
    printf("gbn810: bye (frame %ld)\n", g->frame_no);
    return 0;
}
