/* timer.c - DIV/TIMA/TMA/TAC with falling-edge detection.
 *
 * The timer taps bits {9,3,5,7} of the internal 16-bit counter depending on
 * TAC&3 (4096/262144/65536/16384 Hz); TIMA increments on the falling edge of
 * the selected bit when TAC bit 2 is set. Overflow reloads TMA and raises
 * the timer interrupt.
 */
#include "gb.h"

static const int tap_shift[4] = {9, 3, 5, 7};

void timer_tick(GB *g, int cycles) {
    Timer *t = &g->timer;
    int enabled = t->tac & 4;
    int shift = tap_shift[t->tac & 3];

    while (cycles--) {
        uint16_t old = t->div++;
        if (enabled && ((old >> shift) & 1) && !((t->div >> shift) & 1)) {
            if (++t->tima == 0) {    /* overflow: reload + IRQ */
                t->tima = t->tma;
                g->bus[0xFF0F] |= IF_TIMER;
            }
        }
    }
}
