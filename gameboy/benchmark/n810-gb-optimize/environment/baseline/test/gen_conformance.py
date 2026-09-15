#!/usr/bin/env python3
"""Generate spops_test.gb: linear battery of flag/ register conformance cases.
Serial output: one char per case, 'P' pass / 'F' fail, then 'D' when done.
Case list at bottom of this file. All expected values hand-derived from
official SM83 semantics (Pan Docs /<verified community tables>).
"""
import struct

rom = bytearray(b'\x00' * 0x8000)
code = bytearray()
fixups = []          # (pos_in_code, target_label)
labels = {}

def emit(*bs):
    for b in bs:
        code.append(b & 0xFF)

def word(v):
    return [v & 0xFF, (v >> 8) & 0xFF]

def label(name):
    labels[name] = len(code)

def jmp(op, name):
    fixups.append((len(code) + 1, name))
    if op in (0x18, 0x20, 0x28, 0x30, 0x38):
        emit(op, 0)                          # jr: ONE signed operand byte
    else:
        emit(op, 0, 0)

# --- entry ---
emit(0x00)                       # nop @0100
fixups.append((len(code)+1, 'main')); emit(0xC3)  # jp main
emit(0x00, 0x00)
emit(0x00, 0x00)

# send char in A over serial
label('putc')
emit(0xE0, 0x01)                 # ldh (01),a  SB
emit(0x3E, 0x81)                 # ld a,$81
emit(0xE0, 0x02)                 # ldh (02),a  SC
emit(0xC9)                       # ret

label('fail')
emit(0x3E, 0x46)                 # ld a,'F'
fixups.append((len(code)+1, 'putc')); emit(0xCD, 0x00, 0x00)  # call putc
label('halt')
emit(0x18, 0xFE)                 # jr -2

# ---- case helpers ----------------------------------------------------
# setup AF: LD BC,(f<<8|a); PUSH BC; POP AF
def load_af(a, f):
    emit(0x01); emit(*word((a << 8) | f))   # ld bc,d16  (B=A, C=F)
    emit(0xC5)                              # push bc
    emit(0xF1)                              # pop af

def load_hl(v):
    emit(0x21); emit(*word(v))

def load_de(v):
    emit(0x11); emit(*word(v))

def load_sp(v):
    emit(0x31); emit(*word(v))

# compare A against imm, jump to fail if not equal
def cp_a(imm):
    emit(0xFE, imm)                         # cp imm
    jmp(0xC2, 'fail')                       # jp nz, fail

# after op: AF on stack; capture SP: PUSH AF; LD HL,SP+2; PUSH HL; POP DE; POP AF
# (SP+2 because PUSH AF already moved SP down by 2)
def capture_sp():
    emit(0xF5)                              # push af
    emit(0xF8, 0x02)                        # ld hl,sp+2
    emit(0xE5)                              # push hl
    emit(0xD1)                              # pop de
    emit(0xF1)                              # pop af

def check_de(v):
    emit(0xF5)                                 # push af (preserve across CPs)
    emit(0x7B); cp_a(v & 0xFF)                 # ld a,e ; cp
    emit(0x7A); cp_a((v >> 8) & 0xFF)          # ld a,d ; cp
    emit(0xF1)                                 # pop af

def check_af(a, f):
    emit(0xF5)                              # push af (save)
    emit(0xC1)                              # pop bc -> b=a, c=f
    emit(0x78); cp_a(a)                     # ld a,b ; cp
    emit(0x79); cp_a(f & 0xF0)              # ld a,c ; cp (F low nibble is always 0)
    emit(0xC5)                              # push bc (the saved AF)
    emit(0xF1)                              # pop af -> restore AF, stack balanced

def check_hl(v):
    emit(0xF5)                                 # push af
    emit(0xE5); emit(0xC1)                     # push hl; pop bc
    emit(0x78); cp_a((v >> 8) & 0xFF)
    emit(0x79); cp_a(v & 0xFF)
    emit(0xF1)                                 # pop af

def pass_case():
    emit(0x3E, 0x50)                        # ld a,'P'
    fixups.append((len(code)+1, 'putc')); emit(0xCD, 0x00, 0x00)  # call putc

CASES = []   # (name, builder)

# 0: INC SP C005->C006, flags unchanged
# (post-op SP must be >= 0xC004: capture_sp pushes 4 bytes below it and
#  writes below 0x8000 hit cartridge space and vanish, like real hardware)
def c0():
    load_sp(0xC005); load_af(0x11, 0x80)
    emit(0x33)                              # inc sp
    capture_sp(); check_de(0xC006); check_af(0x11, 0x80)
    pass_case()
CASES.append(('inc sp 0->1, flags kept', c0))

# 1: INC SP wrap FFFF->0000
def c1():
    load_sp(0xFFFF); load_af(0x22, 0x10)
    emit(0x33)
    capture_sp(); check_de(0x0000); check_af(0x22, 0x10)
    pass_case()
CASES.append(('inc sp wrap', c1))

# 2: DEC SP C007->C006 (post-op SP >= 0xC004 for capture, see case 0)
def c2():
    load_sp(0xC007); load_af(0x33, 0x00)
    emit(0x3B)
    capture_sp(); check_de(0xC006); check_af(0x33, 0x00)
    pass_case()
CASES.append(('dec sp', c2))

# 3: ADD HL,SP no carry: HL=1234 SP=C102 -> D336, H=0 C=0, Z kept(1), N=0
def c3():
    load_hl(0x1234); load_sp(0xC102); load_af(0x44, 0x80)
    emit(0x39)                              # add hl,sp
    check_hl(0xD336)                        # preserves AF for check_af
    check_af(0x44, 0x80)
    pass_case()
CASES.append(('add hl,sp plain', c3))

# 4: ADD HL,SP half-carry: HL=0FF0 SP=C010 -> D000, H=1 C=0
def c4():
    load_hl(0x0FF0); load_sp(0xC010); load_af(0x55, 0x00)
    emit(0x39)
    check_hl(0xD000)
    check_af(0x55, 0x20)                    # H set, N=0, Z=0, C=0
    pass_case()
CASES.append(('add hl,sp halfcarry', c4))

# 5: ADD HL,SP full carry: HL=FFF0 SP=C010 -> C000, H=1 C=1
def c5():
    load_hl(0xFFF0); load_sp(0xC010); load_af(0x66, 0x00)
    emit(0x39)
    check_hl(0xC000)
    check_af(0x66, 0x30)                    # H=1 C=1
    pass_case()
CASES.append(('add hl,sp carry', c5))

# 6: LD SP,HL
def c6():
    load_hl(0xC0EF); load_af(0x77, 0x80)
    emit(0xF9)                              # ld sp,hl
    capture_sp(); check_de(0xC0EF); check_af(0x77, 0x80)
    pass_case()
CASES.append(('ld sp,hl', c6))

# 7: ADD SP,+1 from ...0F: H=1 C=0
def c7():
    load_sp(0xC00F); load_af(0x88, 0x80)
    emit(0xE8, 0x01)                        # add sp,1
    capture_sp(); check_de(0xC010); check_af(0x88, 0x20)
    pass_case()
CASES.append(('add sp,+1 halfcarry', c7))

# 8: ADD SP,-1 from C010: ->C00F. offset 0xFF unsigned: (0+F)<=F H=0;
#    (10+FF)>FF C=1
def c8():
    load_sp(0xC010); load_af(0x99, 0x00)
    emit(0xE8, 0xFF)
    capture_sp(); check_de(0xC00F); check_af(0x99, 0x10)
    pass_case()
CASES.append(('add sp,-1 halfcarry', c8))

# 9: LD HL,SP+8 flags: SP=C239,e=8 -> HL=C241, H=1 C=0 (9+8>0xF half-carry)
def c9():
    load_sp(0xC239); load_af(0xAA, 0x00)
    emit(0xF8, 0x08)
    check_hl(0xC241)                        # no capture_sp here: it would clobber HL
    check_af(0xAA, 0x20)
    pass_case()
CASES.append(('ld hl,sp+8', c9))

# 10: DAA 0x0B +6 -> 0x11, N=0
def c10():
    load_af(0x0B, 0x00)
    emit(0x27)
    check_af(0x11, 0x00)
    pass_case()
CASES.append(('daa 0b->11', c10))

# 11: DAA 0x45 unchanged
def c11():
    load_af(0x45, 0x00)
    emit(0x27)
    check_af(0x45, 0x00)
    pass_case()
CASES.append(('daa 45 keep', c11))

# 12: DAA 0x9A -> 0x00, Z=1 (result is zero), C=1
def c12():
    load_af(0x9A, 0x00)
    emit(0x27)
    check_af(0x00, 0x90)
    pass_case()
CASES.append(('daa 9a->00 c', c12))

# 13: DAA sub 0x1E N=1 H=0 C=0 -> unchanged 0x1E (hardware: no lo>9 adjust in sub branch)
def c13():
    load_af(0x1E, 0x40)
    emit(0x27)
    check_af(0x1E, 0x40)
    pass_case()
CASES.append(('daa sub 1e keep', c13))

# 14: DAA sub H: A=0x20 N=1 H=1 -> 0x1A, H=0
def c14():
    load_af(0x20, 0x60)
    emit(0x27)
    check_af(0x1A, 0x40)
    pass_case()
CASES.append(('daa sub h 20->1a', c14))

# 15: DAA sub C: A=0x45 N=1 H=1 C=1 -> 0xDF, C=1
def c15():
    load_af(0x45, 0x70)
    emit(0x27)
    check_af(0xDF, 0x50)
    pass_case()
CASES.append(('daa sub c 45->df', c15))

# 16: CPL: A=0x00 -> FF, N=1 H=1, C preserved(1), Z preserved(0)
def c16():
    load_af(0x00, 0x90)                     # Z=1? no: 0x90 = N... use C=1: 0x10|Z? -> 0x90 = Z+C
    emit(0x2F)
    check_af(0xFF, 0xF0)                    # Z kept(0x80), N=0x40, H=0x20, C=0x10
    pass_case()
CASES.append(('cpl flags', c16))

# 17: SCF: C=1, N=0, H=0, Z kept
def c17():
    load_af(0x12, 0x40)                     # N=1 (should clear), Z=0
    emit(0x37)
    check_af(0x12, 0x10)
    pass_case()
CASES.append(('scf', c17))

# 18: CCF: C toggled 0->1, N=0 H=0
def c18():
    load_af(0x34, 0x80)                     # Z=1, C=0 -> C=1
    emit(0x3F)
    check_af(0x34, 0x90)                    # Z kept, C=1
    pass_case()
CASES.append(('ccf set', c18))

# 19: CCF: C toggled 1->0
def c19():
    load_af(0x56, 0x90)
    emit(0x3F)
    check_af(0x56, 0x80)
    pass_case()
CASES.append(('ccf clear', c19))

# 20: LD (nn),SP stores lo at nn, hi at nn+1
# (SP must sit over writable RAM: the pass_case CALL pushes its return
#  address at SP-1/SP-2, and 0xABCD would land in cartridge space)
def c20():
    load_sp(0xC010)
    emit(0x08); emit(*word(0xC100))         # ld (C100),sp
    emit(0xFA); emit(*word(0xC100))         # ld a,(C100)
    cp_a(0x10)
    emit(0xFA); emit(*word(0xC101))
    cp_a(0xC0)
    pass_case()
CASES.append(('ld (nn),sp', c20))

# 21: LD r,r' does not touch flags: B=55 -> C via LD C,B (48)
# verify C first but push AF around the cp (it trashes flags); check_af's
# pop bc uses BC as scratch so it must run after the C check
def c21():
    load_af(0x77, 0x90)                     # Z=1 C=1
    emit(0x06, 0x55)                        # ld b,$55
    emit(0x48)                              # ld c,b
    emit(0xF5)                              # push af
    emit(0x79); cp_a(0x55)                  # ld a,c ; cp -> c must be 55
    emit(0xF1)                              # pop af
    check_af(0x77, 0x90)
    pass_case()
CASES.append(('ld c,b no flags', c21))

# 22: LD A,(HL) etc covered elsewhere; ADD A,imm half-carry: 0F+01 -> 10, H=1
def c22():
    load_af(0x0F, 0x00)
    emit(0xC6, 0x01)                        # add a,1
    check_af(0x10, 0x20)
    pass_case()
CASES.append(('add a,1 h', c22))

# 23: ADC with carry-in: A=0x00, C=1, +0x00 -> 0x01
def c23():
    load_af(0x00, 0x10)
    emit(0xCE, 0x00)                        # adc a,0
    check_af(0x01, 0x00)
    pass_case()
CASES.append(('adc carry-in', c23))

# 24: SBC borrow: A=0x00, C=1: 0-1-1 = 0xFE, N=1 H=1 C=1
def c24():
    load_af(0x00, 0x10)
    emit(0xDE, 0x01)                        # sbc a,1
    check_af(0xFE, 0x70)
    pass_case()
CASES.append(('sbc borrow', c24))

# 25: CP equal: Z=1 N=1
def c25():
    load_af(0x42, 0x00)
    emit(0xFE, 0x42)                        # cp 42
    check_af(0x42, 0xC0)
    pass_case()
CASES.append(('cp equal', c25))

# 26: DAA carry+6 no double: A=0x99 C=1 (sub? no add) -> 0x99+0x60 = F9? canonical: C set -> +60: FF+... compute: A=99,C=1,N=0,H=0: a>99? no. C=1 -> +0x60 -> 0xF9. C=1.
def c26():
    load_af(0x99, 0x10)
    emit(0x27)
    check_af(0xF9, 0x10)
    pass_case()
CASES.append(('daa c-set add 99->f9', c26))

# 27: INC (HL) flags: value 0F -> 10, H=1, Z=0, N=0, C kept
def c27():
    load_hl(0xC110); load_af(0x0F, 0x10)
    emit(0x77)                              # ld (hl),a
    load_af(0x99, 0x10)                     # C=1 to check preserved
    emit(0x34)                              # inc (hl)
    check_af(0x99, 0x30)                    # H=1,C=1,Z=0,N=0 (before readback cp)
    emit(0xFA); emit(*word(0xC110)); cp_a(0x10)
    pass_case()
CASES.append(('inc (hl)', c27))

# 28: BIT n,(HL): bit=0 -> Z=1, H=1, N=0, C kept
def c28():
    load_hl(0xC111); load_af(0x55, 0x10)
    emit(0x77)
    load_af(0x12, 0x10)                     # C=1
    emit(0xCB, 0x46)                        # bit 0,(hl) -> 55: bit0=1 -> Z=0
    check_af(0x12, 0x30)                    # H=1, C=1, Z=0
    emit(0xCB, 0x7E)                        # bit 7,(hl) -> 55 bit7=0 -> Z=1
    check_af(0x12, 0xB0)                    # Z=1 H=1 C=1, N=0 (BIT clears N)
    pass_case()
CASES.append(('bit (hl)', c28))

# ---- main: run all cases, then 'D' ----
label('main')
emit(0xF3)                                   # di
for i, (name, builder) in enumerate(CASES):
    builder()
emit(0x3E, 0x44)                             # ld a,'D'
fixups.append((len(code)+1, 'putc')); emit(0xCD, 0x00, 0x00)  # call putc
jmp(0xC3, 'halt')                            # jp halt (halt is far beyond jr range)

# ---- place code into rom at 0x0150 ----
start = 0x0150
rom[start:start+len(code)] = code
for pos, tgt in fixups:
    name = tgt
    if name == 'main':
        addr = start + labels['main']
    else:
        addr = start + labels[name]
    rel = addr - (start + pos + 1)
    if rom[start+pos-1] in (0x18, 0x20, 0x28, 0x30, 0x38):
        rom[start+pos] = rel & 0xFF          # jr operand sits AT pos
    else:
        rom[start+pos:start+pos+2] = word(addr)

rom[0x0100] = 0x00
rom[0x0101:0x0104] = bytes([0xC3, 0x50, 0x01])
rom[0x0147] = 0x00
open('test/roms/conformance.gb', 'wb').write(bytes(rom))
print(f"built conformance.gb: {len(CASES)} cases, {len(code)} bytes of code")
for i, (name, _) in enumerate(CASES):
    print(f"  case {i}: {name}")
