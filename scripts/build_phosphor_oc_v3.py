import struct
import zlib
import hashlib
import os
import re
from test_exact_deflate import compress_exact_deflate

base_dir = r"C:\Users\robog\.gemini\antigravity\scratch\avalon_nano3s_cfw"
phos_kdimg_path = r"C:\Users\robog\.gemini\antigravity\brain\fa92c2a8-e9d0-4bb6-98ce-77c4af552528\.user_uploaded\media_1795469395369_aa437c79.kdimg"
phos_mm_path = os.path.join(base_dir, r"phosphor_app\release\linux\app\mm_miner")
phos_dash_path = os.path.join(base_dir, r"phosphor_app\release\linux\resource\www\html\dashboard.html")
phos_ubi_path = os.path.join(base_dir, "phosphor_app_ubi.bin")
out_kdimg_path = os.path.join(base_dir, "Phosphor_OS_Nano3S_OC_v3.kdimg")

# ==============================================================================
# 1. Clean Two-Pass RISC-V64 Macro-Assembler
# ==============================================================================
REG = {
    "zero": 0, "ra": 1, "sp": 2, "gp": 3, "tp": 4,
    "t0": 5, "t1": 6, "t2": 7, "s0": 8, "s1": 9,
    "a0": 10, "a1": 11, "a2": 12, "a3": 13, "a4": 14, "a5": 15,
    "a6": 16, "a7": 17, "s2": 18, "s3": 19, "s4": 20, "s5": 21,
    "s6": 22, "s7": 23, "s8": 24, "s9": 25, "s10": 26, "s11": 27,
    "t3": 28, "t4": 29, "t5": 30, "t6": 31,
}

def enc_i(op, rd, f3, rs1, imm):
    return ((imm & 0xfff) << 20) | (REG[rs1] << 15) | (f3 << 12) | (REG[rd] << 7) | op

def enc_s(op, f3, rs1, rs2, imm):
    imm &= 0xfff
    return ((imm >> 5) << 25) | (REG[rs2] << 20) | (REG[rs1] << 15) | (f3 << 12) | ((imm & 0x1f) << 7) | op

def enc_r(op, rd, f3, rs1, rs2, f7=0):
    return (f7 << 25) | (REG[rs2] << 20) | (REG[rs1] << 15) | (f3 << 12) | (REG[rd] << 7) | op

def enc_u(op, rd, imm20):
    return ((imm20 & 0xfffff) << 12) | (REG[rd] << 7) | op

def enc_b(f3, rs1, rs2, off):
    assert (off & 1) == 0 and -4096 <= off < 4096, f"Branch out of range: {off}"
    imm = off & 0x1fff
    return (((imm >> 12) & 1) << 31) | (((imm >> 5) & 0x3f) << 25) | (REG[rs2] << 20) | \
           (REG[rs1] << 15) | (f3 << 12) | (((imm >> 1) & 0xf) << 8) | (((imm >> 11) & 1) << 7) | 0x63

def enc_j(rd, off):
    assert (off & 1) == 0 and -1048576 <= off < 1048576, f"JAL out of range: {off}"
    imm = off & 0x1fffff
    return (((imm >> 20) & 1) << 31) | (((imm >> 1) & 0x3ff) << 21) | (((imm >> 11) & 1) << 20) | \
           (((imm >> 12) & 0xff) << 12) | (REG[rd] << 7) | 0x6f

def split_pcrel(pc, target):
    delta = target - pc
    hi = (delta + 0x800) & 0xfffff000
    if hi >= 0x80000000:
        hi -= 0x100000000
    lo = delta - hi
    assert -2048 <= lo <= 2047
    return (hi >> 12) & 0xfffff, lo

def emit_call_raw(pc, target):
    hi20, lo12 = split_pcrel(pc, target)
    return [enc_u(0x17, "t0", hi20), enc_i(0x67, "ra", 0, "t0", lo12)]

class Asm:
    def __init__(self, base_vaddr):
        self.base = base_vaddr
        self.ops = []
        self.labels = {}

    def pc(self):
        return self.base + sum(o[0] for o in self.ops)

    def label(self, name):
        self.labels[name] = self.pc()

    def w(self, word):
        self.ops.append((4, lambda pc, L, w=word: struct.pack("<I", w)))

    def raw(self, data):
        self.ops.append((len(data), lambda pc, L, d=data: d))

    def align4(self):
        pad = (-self.pc()) & 3
        if pad:
            self.raw(b"\x00" * pad)

    def addi(self, rd, rs1, imm): self.w(enc_i(0x13, rd, 0, rs1, imm))
    def mv(self, rd, rs1): self.addi(rd, rs1, 0)
    def slli(self, rd, rs1, sh): self.w(enc_i(0x13, rd, 1, rs1, sh))
    def add(self, rd, rs1, rs2): self.w(enc_r(0x33, rd, 0, rs1, rs2, 0))
    def sub(self, rd, rs1, rs2): self.w(enc_r(0x33, rd, 0, rs1, rs2, 0x20))
    def mul(self, rd, rs1, rs2): self.w(enc_r(0x33, rd, 0, rs1, rs2, 1))
    def divu(self, rd, rs1, rs2): self.w(enc_r(0x33, rd, 5, rs1, rs2, 1))
    def remu(self, rd, rs1, rs2): self.w(enc_r(0x33, rd, 7, rs1, rs2, 1))
    def divw(self, rd, rs1, rs2): self.w(enc_r(0x3b, rd, 4, rs1, rs2, 1))
    def lb(self, rd, off, rs1): self.w(enc_i(0x03, rd, 0, rs1, off))
    def lh(self, rd, off, rs1): self.w(enc_i(0x03, rd, 1, rs1, off))
    def lw(self, rd, off, rs1): self.w(enc_i(0x03, rd, 2, rs1, off))
    def ld(self, rd, off, rs1): self.w(enc_i(0x03, rd, 3, rs1, off))
    def lbu(self, rd, off, rs1): self.w(enc_i(0x03, rd, 4, rs1, off))
    def lhu(self, rd, off, rs1): self.w(enc_i(0x03, rd, 5, rs1, off))
    def sb(self, rs2, off, rs1): self.w(enc_s(0x23, 0, rs1, rs2, off))
    def sh(self, rs2, off, rs1): self.w(enc_s(0x23, 1, rs1, rs2, off))
    def sw(self, rs2, off, rs1): self.w(enc_s(0x23, 2, rs1, rs2, off))
    def sd(self, rs2, off, rs1): self.w(enc_s(0x23, 3, rs1, rs2, off))
    def ret(self): self.w(enc_i(0x67, "zero", 0, "ra", 0))

    def li(self, rd, val):
        if -2048 <= val <= 2047:
            self.addi(rd, "zero", val)
        else:
            hi = (val + 0x800) & 0xfffff000
            if hi >= 0x80000000: hi -= 0x100000000
            lo = val - hi
            self.w(enc_u(0x37, rd, (hi >> 12) & 0xfffff))
            if lo != 0:
                self.addi(rd, rd, lo)

    def la(self, rd, target):
        def fn(pc, L):
            t = L[target] if isinstance(target, str) else target
            hi20, lo12 = split_pcrel(pc, t)
            return struct.pack("<II", enc_u(0x17, rd, hi20), enc_i(0x13, rd, 0, rd, lo12))
        self.ops.append((8, fn))

    def call(self, target):
        def fn(pc, L):
            t = L[target] if isinstance(target, str) else target
            hi20, lo12 = split_pcrel(pc, t)
            return struct.pack("<II", enc_u(0x17, "t0", hi20), enc_i(0x67, "ra", 0, "t0", lo12))
        self.ops.append((8, fn))

    def br(self, f3, rs1, rs2, label_name):
        self.ops.append((4, lambda pc, L: struct.pack("<I", enc_b(f3, rs1, rs2, L[label_name] - pc))))

    def beq(self, r1, r2, lbl): self.br(0, r1, r2, lbl)
    def bne(self, r1, r2, lbl): self.br(1, r1, r2, lbl)
    def blt(self, r1, r2, lbl): self.br(4, r1, r2, lbl)
    def bge(self, r1, r2, lbl): self.br(5, r1, r2, lbl)
    def bgeu(self, r1, r2, lbl): self.br(7, r1, r2, lbl)
    def j(self, lbl):
        self.ops.append((4, lambda pc, L: struct.pack("<I", enc_j("zero", L[lbl] - pc))))

    def build(self):
        out = bytearray()
        pc = self.base
        for sz, fn in self.ops:
            b = fn(pc, self.labels)
            assert len(b) == sz
            out.extend(b)
            pc += sz
        return bytes(out)

# ==============================================================================
# 2. Known Addresses in Phosphor OS mm_miner
# ==============================================================================
FOPEN_PLT   = 0x00038FC0
FGETS_PLT   = 0x00039030
FCLOSE_PLT  = 0x00039100
SSCANF_PLT  = 0x00039280
SNPRINTF_PLT= 0x00039000

LCD_CREATE_SCREEN = 0x00049388
LCD_CREATE_LABEL  = 0x00049414
LV_OBJ_ALIGN      = 0x000742C8
LV_OBJ_SET_BG_COL = 0x0007D4F8
LV_OBJ_SET_TXT_COL= 0x0007E0E2
LV_COLOR_HEX      = 0x0009BCC6
LV_LABEL_SET_TEXT = 0x000C19F6
LV_TIMER_CREATE   = 0x000A21D0
LV_OBJ_SET_SIZE   = 0x00073F6E
LV_OBJ_SET_WIDTH  = 0x0007CCA6
LV_OBJ_SET_HEIGHT = 0x0007CD72
LV_OBJ_SET_BD_COL = 0x0007D8D0
LV_OBJ_SET_BD_W   = 0x0007D962
LV_OBJ_SET_LN_W   = 0x0007DDD8
LV_OBJ_SET_RADIUS = 0x0007E2CA
LV_CHART_CREATE   = 0x000B81FE
LV_CHART_SET_TYPE = 0x000B8234
LV_CHART_SET_CNT  = 0x000B839A
LV_CHART_SET_RNG  = 0x000B8496
LV_CHART_SET_DIV  = 0x000B8636
LV_CHART_ADD_SER  = 0x000B8C72
LV_CHART_SET_NEXT = 0x000B950E

FONT_14 = 0x0015E328   # lv_font_montserrat_14 (full ASCII + dot + degree)
FONT_32 = 0x001696D8   # lv_font_montserrat_32 (full ASCII + dot + degree)

G_PVT_TEMP   = 0x001AE7B0  # int16_t[12]
G_CALI_INFO  = 0x001AEA50  # +2:pwr(u16), +4:tart(u16), +6:volt(u16), +8:pll(u16)
LCDS_UI      = 0x001AD088  # 24 bytes/entry, +16 = lv_obj_t*

# Clean zero-init RW scratch in .bss tail (0x005ef700..0x005ef800)
BSS_STATE    = 0x005EF700
# Layout of BSS_STATE:
#   +0x00: uint32_t oc_lvl (0..7)
#   +0x08: lv_obj_t *scr_power
#   +0x10: lv_obj_t *scr_cores
#   +0x18: lv_obj_t *p_lbl_tag
#   +0x20: lv_obj_t *p_lbl_watts
#   +0x28: lv_obj_t *p_lbl_vbus
#   +0x30: lv_obj_t *p_lbl_ibus
#   +0x38: lv_obj_t *p_lbl_vcore
#   +0x40: lv_obj_t *p_lbl_foot
#   +0x48: lv_obj_t *c_lbl_clk
#   +0x50: lv_obj_t *c_lbl_minmax
#   +0x58: lv_obj_t *c_lbl_hash
#   +0x60..+0xB8: lv_obj_t *c_lbl_chip[12] (12 * 8 = 96 bytes -> ends at +0xC0)

# Place all our code + rodata inside unused Bitstream Vera license text at 0x00607000..0x00607898 (2200 bytes)
# AND 0x00607900..0x00607fff (1792 bytes), keeping "STATUS=S," at 0x006078a8 UNTOUCHED!

# ==============================================================================
# 3. Assemble Block A @ 0x00607900:
#    - phosphor_apply_oc (8-mode UC/UV/Eff OC/OC with exact 26mV VRM steps)
#    - hook_regular_switch (1 -> 2 -> 3 -> 25 -> 26 -> 1)
#    - hook_get_screen_index (25 -> 18, 26 -> 19)
#    - hook_switch_screen (18 -> scr_power, 19 -> scr_cores)
#    - read_lcdv2 helper
#    - rodata strings & tables
# ==============================================================================
a = Asm(0x00607900)

# --- 3A. phosphor_apply_oc (hooked from cali_param_get @ 0x0003b9e0) ---
a.label("phosphor_apply_oc")
a.w(0xFD045703)  # displaced: lhu a4, -48(s0)
a.w(0x00E79523)  # displaced: sh  a4, 10(a5)
a.addi("sp", "sp", -48)
a.sd("ra", 40, "sp")
a.sd("s1", 32, "sp")
a.sd("s2", 24, "sp")
a.mv("s1", "a5")              # s1 = &g_cali_info
a.la("t0", BSS_STATE)
a.sw("zero", 0, "t0")         # default oc_lvl = 0

a.la("a0", "str_oc_path")
a.la("a1", "str_r")
a.call(FOPEN_PLT)
a.beq("a0", "zero", "oc_done")
a.sd("a0", 16, "sp")
a.mv("a2", "a0")
a.li("a1", 16)
a.mv("a0", "sp")
a.call(FGETS_PLT)
a.mv("s2", "a0")
a.ld("a0", 16, "sp")
a.call(FCLOSE_PLT)
a.beq("s2", "zero", "oc_done")

# Expect "oc <1..7>"
a.lbu("t0", 0, "sp"); a.li("t1", ord("o")); a.bne("t0", "t1", "oc_done")
a.lbu("t0", 1, "sp"); a.li("t1", ord("c")); a.bne("t0", "t1", "oc_done")
a.lbu("t0", 2, "sp"); a.li("t1", ord(" ")); a.bne("t0", "t1", "oc_done")
a.lbu("t0", 3, "sp")
a.addi("t0", "t0", -ord("1"))  # 0..6
a.li("t1", 7)
a.bgeu("t0", "t1", "oc_done")

# Store oc_lvl = t0 + 1 in BSS_STATE[0]
a.addi("t2", "t0", 1)
a.la("t1", BSS_STATE)
a.sw("t2", 0, "t1")

# Table entry: 8 bytes (<hhhh = d_pwr, d_volt, d_pll, 0)
a.slli("t0", "t0", 3)
a.la("t1", "oc_table")
a.add("t1", "t1", "t0")

def emit_add_clamped(cali_off, tab_off, min_v, max_v, tag):
    a.lhu("t2", cali_off, "s1")
    a.lh("t3", tab_off, "t1")      # signed 16-bit offset!
    a.add("t2", "t2", "t3")
    a.li("t3", min_v)
    a.bge("t2", "t3", f"ok_min_{tag}")
    a.mv("t2", "t3")
    a.label(f"ok_min_{tag}")
    a.li("t3", max_v)
    a.bge("t3", "t2", f"ok_max_{tag}")
    a.mv("t2", "t3")
    a.label(f"ok_max_{tag}")
    a.sh("t2", cali_off, "s1")

emit_add_clamped(2, 0,   45,  145, "pwr")
emit_add_clamped(6, 2, 3200, 3750, "volt")
emit_add_clamped(8, 4,  120,  520, "pll")

a.label("oc_done")
a.ld("ra", 40, "sp")
a.ld("s1", 32, "sp")
a.ld("s2", 24, "sp")
a.addi("sp", "sp", 48)
a.ret()

# --- 3B. hook_regular_switch (called from 0x000450b6 in lcd_regular_show_switch) ---
# 6-screen rotation: 1 (Main) -> 25 (Power) -> 26 (Cores) -> 27 (Chart) -> 2 (Clock) -> 3 (Logo) -> 1
a.label("hook_regular_switch")
a.li("t0", 1);  a.beq("a5", "t0", "rs_to_25")
a.li("t0", 25); a.beq("a5", "t0", "rs_to_26")
a.li("t0", 26); a.beq("a5", "t0", "rs_to_27")
a.li("t0", 27); a.beq("a5", "t0", "rs_to_2")
a.li("t0", 2);  a.beq("a5", "t0", "rs_to_3")
a.li("a5", 1);  a.ret()
a.label("rs_to_25"); a.li("a5", 25); a.ret()
a.label("rs_to_26"); a.li("a5", 26); a.ret()
a.label("rs_to_27"); a.li("a5", 27); a.ret()
a.label("rs_to_2");  a.li("a5", 2);  a.ret()
a.label("rs_to_3");  a.li("a5", 3);  a.ret()

# --- 3C. hook_get_screen_index (called from 0x0004a9b4, a0=show_id, a1=sub_id) ---
# 25 -> 18 (Power), 26 -> 19 (Cores), 27 -> 20 (Live Chart); else jumps to original 0x0004a9bc
a.label("hook_get_screen_index")
a.li("t0", 25); a.bne("a0", "t0", "gsi_chk26")
a.li("a0", 18); a.ret()
a.label("gsi_chk26")
a.li("t0", 26); a.bne("a0", "t0", "gsi_chk27")
a.li("a0", 19); a.ret()
a.label("gsi_chk27")
a.li("t0", 27); a.bne("a0", "t0", "gsi_orig")
a.li("a0", 20); a.ret()
a.label("gsi_orig")
# Execute original 8 bytes of get_screen_index (0x4a9b4..0x4a9bc) then jump to 0x4a9bc
a.raw(bytes.fromhex("557186e5a2e18009"))  # c.addi16sp sp,-224; sd ra,216(sp); sd s0,208(sp); addi s0,sp,224
a.la("t0", 0x0004A9BC)
a.w(enc_i(0x67, "zero", 0, "t0", 0))      # jr t0

# --- 3D. hook_switch_screen (called from 0x0004a5f6, -36(s0) = ui_idx) ---
# Returns a5 = lv_obj_t *scr (for ui_idx 18, 19, 20, lazily creates screen!)
a.label("hook_switch_screen")
a.lw("a4", -36, "s0")
a.li("t0", 18); a.beq("a4", "t0", "sw_power")
a.li("t0", 19); a.beq("a4", "t0", "sw_cores")
a.li("t0", 20); a.beq("a4", "t0", "sw_chart")
# Original lcds_ui[a4].scr
a.la("a3", LCDS_UI)
a.mv("a5", "a4")
a.slli("a5", "a5", 1)
a.add("a5", "a5", "a4")
a.slli("a5", "a5", 3)
a.add("a5", "a5", "a3")
a.ld("a5", 16, "a5")
a.ret()

a.label("sw_power")
a.addi("sp", "sp", -16); a.sd("ra", 8, "sp")
a.la("t0", BSS_STATE)
a.ld("a5", 0x08, "t0")
a.bne("a5", "zero", "sw_ret")
a.call(0x000CF000)            # init_power_screen() @ bno=191 -> returns scr in a0
a.mv("a5", "a0")
a.j("sw_ret")

a.label("sw_cores")
a.addi("sp", "sp", -16); a.sd("ra", 8, "sp")
a.la("t0", BSS_STATE)
a.ld("a5", 0x10, "t0")
a.bne("a5", "zero", "sw_ret")
a.call(0x000CF450)            # init_cores_screen() @ bno=191 -> returns scr in a0
a.mv("a5", "a0")
a.j("sw_ret")

a.label("sw_chart")
a.addi("sp", "sp", -16); a.sd("ra", 8, "sp")
a.la("t0", BSS_STATE)
a.ld("a5", 0xC0, "t0")
a.bne("a5", "zero", "sw_ret")
a.call(0x000CF860)            # init_chart_screen() @ bno=191 -> returns scr in a0
a.mv("a5", "a0")

a.label("sw_ret")
a.ld("ra", 8, "sp"); a.addi("sp", "sp", 16)
a.ret()

# --- 3D2. hook_hw_update (jumped from lcd_hardware_update @ 0x00045432) ---
# Intercepts show_id == 25, 26, 27 and calls lcd_update(show_id, 0) directly!
a.label("hook_hw_update")
a.lhu("a0", -38, "s0")
a.li("t0", 25); a.beq("a0", "t0", "hw_custom")
a.li("t0", 26); a.beq("a0", "t0", "hw_custom")
a.li("t0", 27); a.beq("a0", "t0", "hw_custom")
# Original check at 0x00045432..0x00045442
a.lw("a5", -36, "s0")
a.bne("a5", "zero", "hw_orig")
a.lhu("a5", -38, "s0")
a.beq("a5", "zero", "hw_exit")
a.label("hw_orig")
a.la("t0", 0x00045442)
a.w(enc_i(0x67, "zero", 0, "t0", 0))  # jr 0x00045442
a.label("hw_custom")
a.li("a1", 0)
a.call(0x0004AA6A)                    # lcd_update(25 or 26, 0)
a.label("hw_exit")
a.la("t0", 0x0004550A)
a.w(enc_i(0x67, "zero", 0, "t0", 0))  # jr 0x0004550A (epilogue)

# --- 3E. read_lcdv2(uint32_t out[7]) -> returns count (7 on success) ---
# Reads /run/phosphor-lcd-telemetry: "LCDV2 %*d %u %u %u %d %u %u %u"
# out[0]=mode, out[1]=power_W, out[2]=hash_x100, out[3]=tmax, out[4]=fan_pct, out[5]=vbus_mV, out[6]=ibus_uA1
a.label("read_lcdv2")
a.addi("sp", "sp", -176)
a.sd("ra", 168, "sp")
a.sd("s1", 160, "sp")
a.sd("s2", 152, "sp")
a.mv("s1", "a0")              # s1 = out[7]
a.li("s2", 0)
a.la("a0", 0x00601B10)        # existing Phosphor string "/run/phosphor-lcd-telemetry"
a.la("a1", "str_r")
a.call(FOPEN_PLT)
a.beq("a0", "zero", "rl_done")
a.sd("a0", 144, "sp")
a.mv("a2", "a0")
a.li("a1", 120)
a.addi("a0", "sp", 16)        # buf at sp+16
a.call(FGETS_PLT)
a.mv("t1", "a0")
a.sd("t1", 136, "sp")
a.ld("a0", 144, "sp")
a.call(FCLOSE_PLT)
a.ld("t1", 136, "sp")
a.beq("t1", "zero", "rl_done")
# sscanf(buf, "LCDV2 %*d %u %u %u %d %u %u %u", &out[0]..&out[6])
# RV64 ABI: a0..a7 = first 8 args, 9th arg (&out[6]) on stack at 0(sp)!
a.addi("t0", "s1", 24); a.sd("t0", 0, "sp")   # 9th arg: &out[6] (ibus_uA1)
a.addi("a7", "s1", 20)                        # 8th arg: &out[5] (vbus_mV)
a.addi("a6", "s1", 16)                        # 7th arg: &out[4] (fan_pct)
a.addi("a5", "s1", 12)                        # 6th arg: &out[3] (tmax)
a.addi("a4", "s1", 8)                         # 5th arg: &out[2] (hash_x100)
a.addi("a3", "s1", 4)                         # 4th arg: &out[1] (power_W)
a.mv("a2", "s1")                              # 3rd arg: &out[0] (mode)
a.la("a1", "str_lcdv2_fmt")
a.addi("a0", "sp", 16)
a.call(SSCANF_PLT)
a.mv("s2", "a0")
a.label("rl_done")
a.mv("a0", "s2")
a.ld("ra", 168, "sp")
a.ld("s1", 160, "sp")
a.ld("s2", 152, "sp")
a.addi("sp", "sp", 176)
a.ret()

# --- 3E2. make_lbl(a0=scr, a1=font, a2=text, a3=hex_col, a4=x, a5=y) -> returns lbl in a0 ---
a.label("make_lbl")
a.addi("sp", "sp", -32)
a.sd("ra", 24, "sp"); a.sd("s1", 16, "sp"); a.sd("s2", 8, "sp"); a.sd("s3", 0, "sp")
a.mv("s2", "a4"); a.mv("s3", "a5")
a.call(LCD_CREATE_LABEL)
a.mv("s1", "a0")
a.li("a1", 9)  # LV_ALIGN_CENTER
a.mv("a2", "s2"); a.mv("a3", "s3")
a.call(LV_OBJ_ALIGN)
a.mv("a0", "s1")
a.ld("ra", 24, "sp"); a.ld("s1", 16, "sp"); a.ld("s2", 8, "sp"); a.ld("s3", 0, "sp")
a.addi("sp", "sp", 32)
a.ret()

# --- 3F. Rodata strings & tables ---
a.align4()
a.label("oc_table")
# 7 entries * 8 bytes (<hhhh = d_pwr, d_volt, d_pll, 0)
for row in [
    (-12, -52, -40, 0),  # 1: UC -2
    ( -6, -26, -20, 0),  # 2: UC -1
    ( -3, -26,   0, 0),  # 3: UV
    (  4, -26,  20, 0),  # 4: Eff OC
    (  7,  26,  20, 0),  # 5: OC +1
    ( 10,  52,  35, 0),  # 6: OC +2
    ( 12,  78,  50, 0),  # 7: OC +3
]:
    a.raw(struct.pack("<hhhh", *row))

a.label("str_oc_path");   a.raw(b"/data/userdata/phosphor-oc.conf\x00")
a.label("str_r");         a.raw(b"r\x00")
a.label("str_lcdv2_fmt"); a.raw(b"LCDV2 %*d %u %u %u %d %u %u %u\x00")
a.label("str_vbus_cap");  a.raw(b"VBUS\x00")
a.label("str_ibus_cap");  a.raw(b"IBUS\x00")
a.label("str_dash");      a.raw(b"--\x00")
a.label("str_cores_hdr"); a.raw(b"A3197S CORES\x00")
a.label("str_fmt_tag");   a.raw(b"%s  |  %s\x00")
a.label("str_fmt_w");     a.raw(b"%u.%u W\x00")
a.label("str_fmt_v");     a.raw(b"%u.%02u V\x00")
a.label("str_fmt_a");     a.raw(b"%u.%02u A\x00")
a.label("str_fmt_vc");    a.raw(b"%u mV  |  %u.%u J/TH\x00")
a.label("str_fmt_vc0");   a.raw(b"%u mV  |  -- J/TH\x00")
a.label("str_fmt_foot");  a.raw(b"FAN %u%%  |  %d\xc2\xb0C\x00")
a.label("str_fmt_clk");   a.raw(b"%u MHz  %u.%02u V\x00")
a.label("str_fmt_c");     a.raw(b"%d\xc2\xb0\x00")
a.label("str_fmt_mm");    a.raw(b"%d\xc2\xb0 / %d\xc2\xb0 / %d\xc2\xb0C\x00")
a.label("str_fmt_th");    a.raw(b"%u.%02u TH/s\x00")
a.label("str_chart_hdr"); a.raw(b"POWER LIVE\x00")
a.label("str_ch_w");      a.raw(b"%u.%uW\x00")
a.label("str_ch_v");      a.raw(b"%u.%uV\x00")
a.label("str_ch_a");      a.raw(b"%u.%02uA\x00")
a.label("str_ch_foot");   a.raw(b"%u.%02u TH/s  |  %d\xc2\xb0C\x00")

# Fixed-width 8-byte mode strings (indexed by mode * 8)
a.align4()
a.label("mode_names")
for s in [b"LOW", b"MED", b"HIGH", b"AUTO"]:
    a.raw(s.ljust(8, b"\x00"))
a.label("oc_names")
for s in [b"STOCK", b"UC -2", b"UC -1", b"UV", b"EFF OC", b"OC +1", b"OC +2", b"OC +3"]:
    a.raw(s.ljust(8, b"\x00"))

block_a = a.build()
print(f"Block A (0x00607900): {len(block_a)} bytes (ends at 0x{0x607900+len(block_a):08x}, limit 0x00608000)")
assert 0x00607900 + len(block_a) <= 0x00608000

L_A = a.labels  # export label addresses for Block B!

# ==============================================================================
# 4. Assemble Block B @ 0x000CF000 (bno=191, unused lv_spangroup widget, 4096B, clen=2316!):
#    - init_power_screen  @ 0x000CF000
#    - update_power_screen
#    - init_cores_screen  @ 0x000CF450
#    - update_cores_screen
# ==============================================================================
b = Asm(0x000CF000)

def emit_make_lbl(asm, scr_reg, font_addr, text_addr, hex_col, x, y, bss_off):
    asm.mv("a0", scr_reg)
    asm.la("a1", font_addr)
    asm.la("a2", text_addr)
    asm.li("a3", hex_col)
    asm.li("a4", x)
    asm.li("a5", y)
    asm.call(L_A["make_lbl"])
    if bss_off is not None:
        asm.sd("a0", bss_off, "s1")

# --- 4A. init_power_screen @ 0x00607000 ---
b.label("init_power_screen")
b.addi("sp", "sp", -32)
b.sd("ra", 24, "sp"); b.sd("s1", 16, "sp"); b.sd("s2", 8, "sp"); b.sd("s3", 0, "sp")
b.la("s1", BSS_STATE)
b.call(LCD_CREATE_SCREEN)
b.mv("s3", "a0")               # s3 = scr_power
b.sd("s3", 0x08, "s1")

# Set dark navy Phosphor background #030810
b.li("a0", 0x030810)
b.call(LV_COLOR_HEX)
b.mv("a1", "a0")
b.mv("a0", "s3")
b.li("a2", 0)
b.call(LV_OBJ_SET_BG_COL)

# Labels (symmetric 240x240 layout):
emit_make_lbl(b, "s3", FONT_14, L_A["str_dash"],     0x8DC5FF,   0, -86, 0x18)  # tag: HIGH | EFF OC
emit_make_lbl(b, "s3", FONT_32, L_A["str_dash"],     0xF3A965,   0, -46, 0x20)  # watts: 137.6 W
emit_make_lbl(b, "s3", FONT_14, L_A["str_vbus_cap"], 0xA0B7CA, -54,  -6, None)  # caption VBUS
emit_make_lbl(b, "s3", FONT_14, L_A["str_dash"],     0xB0DCFD, -54,  16, 0x28)  # 28.04 V
emit_make_lbl(b, "s3", FONT_14, L_A["str_ibus_cap"], 0xA0B7CA,  54,  -6, None)  # caption IBUS
emit_make_lbl(b, "s3", FONT_14, L_A["str_dash"],     0xB0DCFD,  54,  16, 0x30)  # 4.91 A
emit_make_lbl(b, "s3", FONT_14, L_A["str_dash"],     0x9AEF9E,   0,  54, 0x38)  # 3424 mV | 20.8 J/TH
emit_make_lbl(b, "s3", FONT_14, L_A["str_dash"],     0xA0B7CA,   0,  82, 0x40)  # FAN 68% | 74°C

# Initial update + 1000ms timer
b.li("a0", 0)
b.call("update_power_screen")
b.la("a0", "update_power_screen")
b.li("a1", 1000)
b.li("a2", 0)
b.call(LV_TIMER_CREATE)

b.mv("a0", "s3")
b.ld("ra", 24, "sp"); b.ld("s1", 16, "sp"); b.ld("s2", 8, "sp"); b.ld("s3", 0, "sp")
b.addi("sp", "sp", 32)
b.ret()

# --- 4B. update_power_screen(lv_timer_t *) ---
b.label("update_power_screen")
b.addi("sp", "sp", -144)
b.sd("ra", 136, "sp"); b.sd("s1", 128, "sp"); b.sd("s2", 120, "sp"); b.sd("s3", 112, "sp"); b.sd("s4", 104, "sp")
# Stack: [0..27] = lcdv2[7] (u32), [32..95] = char txt[64]
b.la("s1", BSS_STATE)
b.mv("a0", "sp")
b.call(L_A["read_lcdv2"])
b.li("t0", 7)
b.blt("a0", "t0", "up_done")

# 1. Tag: "%s  |  %s" (mode_names[mode&3], oc_names[oc_lvl&7])
b.lw("t0", 0, "sp")           # mode
b.li("t1", 3); b.blt("t0", "t1", "up_m_ok"); b.li("t0", 2); b.label("up_m_ok")
b.slli("t0", "t0", 3); b.la("a3", L_A["mode_names"]); b.add("a3", "a3", "t0")
b.lw("t0", 0, "s1")           # oc_lvl
b.li("t1", 8); b.blt("t0", "t1", "up_o_ok"); b.li("t0", 0); b.label("up_o_ok")
b.slli("t0", "t0", 3); b.la("a4", L_A["oc_names"]); b.add("a4", "a4", "t0")
b.addi("a0", "sp", 32); b.li("a1", 64); b.la("a2", L_A["str_fmt_tag"])
b.call(SNPRINTF_PLT)
b.ld("a0", 0x18, "s1"); b.addi("a1", "sp", 32); b.call(LV_LABEL_SET_TEXT)

# Compute s2 = vbus_mV, s3 = ibus_mA
b.lw("s2", 20, "sp")          # vbus_mV
b.lw("t0", 24, "sp")          # ibus_uA_plus_1
b.li("s3", 0)
b.beq("t0", "zero", "up_i0")
b.addi("t0", "t0", -1)
b.li("t1", 1000); b.divu("s3", "t0", "t1")  # s3 = ibus_mA
b.label("up_i0")

# 2. Watts: power_x10 = (vbus_mV * ibus_mA) / 100000; if 0 -> power_W * 10
b.mul("t0", "s2", "s3")
b.li("t1", 100000); b.divu("s4", "t0", "t1")  # s4 = watts_x10
b.bne("s4", "zero", "up_w_ok")
b.lw("t0", 4, "sp"); b.li("t1", 10); b.mul("s4", "t0", "t1")
b.label("up_w_ok")
b.li("t1", 10); b.divu("a3", "s4", "t1"); b.remu("a4", "s4", "t1")
b.addi("a0", "sp", 32); b.li("a1", 64); b.la("a2", L_A["str_fmt_w"])
b.call(SNPRINTF_PLT)
b.ld("a0", 0x20, "s1"); b.addi("a1", "sp", 32); b.call(LV_LABEL_SET_TEXT)

# 3. VBUS: "%u.%02u V"
b.li("t1", 1000); b.divu("a3", "s2", "t1"); b.remu("t0", "s2", "t1")
b.li("t1", 10); b.divu("a4", "t0", "t1")
b.addi("a0", "sp", 32); b.li("a1", 64); b.la("a2", L_A["str_fmt_v"])
b.call(SNPRINTF_PLT)
b.ld("a0", 0x28, "s1"); b.addi("a1", "sp", 32); b.call(LV_LABEL_SET_TEXT)

# 4. IBUS: "%u.%02u A"
b.li("t1", 1000); b.divu("a3", "s3", "t1"); b.remu("t0", "s3", "t1")
b.li("t1", 10); b.divu("a4", "t0", "t1")
b.addi("a0", "sp", 32); b.li("a1", 64); b.la("a2", L_A["str_fmt_a"])
b.call(SNPRINTF_PLT)
b.ld("a0", 0x30, "s1"); b.addi("a1", "sp", 32); b.call(LV_LABEL_SET_TEXT)

# 5. Vcore & J/TH: vcore = g_cali_info.voltage (+6), jth_x10 = (watts_x10 * 100) / hash_x100
b.la("t0", G_CALI_INFO); b.lhu("a3", 6, "t0")
b.lw("t2", 8, "sp")           # hash_x100
b.beq("t2", "zero", "up_j0")
b.li("t1", 100); b.mul("t0", "s4", "t1"); b.divu("t0", "t0", "t2")  # jth_x10
b.li("t1", 10); b.divu("a4", "t0", "t1"); b.remu("a5", "t0", "t1")
b.addi("a0", "sp", 32); b.li("a1", 64); b.la("a2", L_A["str_fmt_vc"])
b.call(SNPRINTF_PLT)
b.j("up_vc_set")
b.label("up_j0")
b.addi("a0", "sp", 32); b.li("a1", 64); b.la("a2", L_A["str_fmt_vc0"])
b.call(SNPRINTF_PLT)
b.label("up_vc_set")
b.ld("a0", 0x38, "s1"); b.addi("a1", "sp", 32); b.call(LV_LABEL_SET_TEXT)

# 6. Footer: "FAN %u%%  |  %d°C"
b.lw("a3", 16, "sp")          # fan_pct
b.lw("a4", 12, "sp")          # tmax
b.addi("a0", "sp", 32); b.li("a1", 64); b.la("a2", L_A["str_fmt_foot"])
b.call(SNPRINTF_PLT)
b.ld("a0", 0x40, "s1"); b.addi("a1", "sp", 32); b.call(LV_LABEL_SET_TEXT)

b.label("up_done")
b.ld("ra", 136, "sp"); b.ld("s1", 128, "sp"); b.ld("s2", 120, "sp"); b.ld("s3", 112, "sp"); b.ld("s4", 104, "sp")
b.addi("sp", "sp", 144)
b.ret()

# Pad to 0x000CF450 so init_cores_screen has a fixed known entry address!
cur_pc = b.pc()
print(f"Power screen code ends at 0x{cur_pc:08x} (target <= 0x000cf450)")
assert cur_pc <= 0x000CF450, f"Power screen code overflowed 0x000cf450: 0x{cur_pc:08x}"
b.raw(b"\x00" * (0x000CF450 - cur_pc))

# --- 4C. init_cores_screen @ 0x000CF450 ---
b.label("init_cores_screen")
b.addi("sp", "sp", -48)
b.sd("ra", 40, "sp"); b.sd("s1", 32, "sp"); b.sd("s2", 24, "sp"); b.sd("s3", 16, "sp"); b.sd("s4", 8, "sp"); b.sd("s5", 0, "sp")
b.la("s1", BSS_STATE)
b.call(LCD_CREATE_SCREEN)
b.mv("s3", "a0")               # s3 = scr_cores
b.sd("s3", 0x10, "s1")

b.li("a0", 0x030810)
b.call(LV_COLOR_HEX)
b.mv("a1", "a0"); b.mv("a0", "s3"); b.li("a2", 0)
b.call(LV_OBJ_SET_BG_COL)

emit_make_lbl(b, "s3", FONT_14, L_A["str_cores_hdr"], 0x8DC5FF, 0, -90, None)
emit_make_lbl(b, "s3", FONT_14, L_A["str_dash"],      0xE5F3FF, 0, -66, 0x48)  # 426 MHz  3.86 V
emit_make_lbl(b, "s3", FONT_14, L_A["str_dash"],      0xA0B7CA, 0,  64, 0x50)  # 69° / 72° / 74°C
emit_make_lbl(b, "s3", FONT_14, L_A["str_dash"],      0x9AEF9E, 0,  88, 0x58)  # 6.62 TH/s

# Loop s4 = 0..11 to create 3x4 symmetric grid of 12 ASIC temp labels:
#   row = s4 / 4 (0..2), col = s4 % 4 (0..3)
#   x = -69 + col * 46   (-69, -23, +23, +69)
#   y = -32 + row * 32   (-32,   0, +32)
b.li("s4", 0)
b.label("ic_loop")
b.mv("a0", "s3")
b.la("a1", FONT_14)
b.la("a2", L_A["str_dash"])
b.li("a3", 0x9AEF9E)
b.call(LCD_CREATE_LABEL)
b.mv("s2", "a0")
# Store at s1 + 0x60 + s4*8
b.slli("t0", "s4", 3); b.addi("t0", "t0", 0x60); b.add("t0", "s1", "t0")
b.sd("s2", 0, "t0")
# x = (s4 & 3) * 46 - 69
b.li("t1", 4); b.remu("t0", "s4", "t1")
b.li("t2", 46); b.mul("t0", "t0", "t2"); b.addi("a2", "t0", -69)
# y = (s4 / 4) * 32 - 32
b.divu("t0", "s4", "t1"); b.slli("t0", "t0", 5); b.addi("a3", "t0", -32)
b.mv("a0", "s2"); b.li("a1", 9)
b.call(LV_OBJ_ALIGN)
b.addi("s4", "s4", 1)
b.li("t0", 12)
b.blt("s4", "t0", "ic_loop")

b.li("a0", 0)
b.call("update_cores_screen")
b.la("a0", "update_cores_screen")
b.li("a1", 1000)
b.li("a2", 0)
b.call(LV_TIMER_CREATE)

b.mv("a0", "s3")
b.ld("ra", 40, "sp"); b.ld("s1", 32, "sp"); b.ld("s2", 24, "sp"); b.ld("s3", 16, "sp"); b.ld("s4", 8, "sp"); b.ld("s5", 0, "sp")
b.addi("sp", "sp", 48)
b.ret()

# --- 4D. update_cores_screen(lv_timer_t *) ---
b.label("update_cores_screen")
b.addi("sp", "sp", -160)
b.sd("ra", 152, "sp"); b.sd("s1", 144, "sp"); b.sd("s2", 136, "sp"); b.sd("s3", 128, "sp")
b.sd("s4", 120, "sp"); b.sd("s5", 112, "sp"); b.sd("s6", 104, "sp"); b.sd("s7", 96, "sp")
b.la("s1", BSS_STATE)

# 1. Clock & Vcore: "%u MHZ  %u.%02u V"
b.la("t0", G_CALI_INFO)
b.lhu("a3", 8, "t0")          # pll MHz
b.lhu("t1", 6, "t0")          # volt mV
b.li("t2", 1000); b.divu("a4", "t1", "t2"); b.remu("t1", "t1", "t2")
b.li("t2", 10); b.divu("a5", "t1", "t2")
b.addi("a0", "sp", 32); b.li("a1", 64); b.la("a2", L_A["str_fmt_clk"])
b.call(SNPRINTF_PLT)
b.ld("a0", 0x48, "s1"); b.addi("a1", "sp", 32); b.call(LV_LABEL_SET_TEXT)

# 2. Loop s2 = 0..11 over g_pvt_temp[12] (int16_t): track s3=min, s4=max, s5=sum, s6=cnt
b.li("s2", 0); b.li("s3", 999); b.li("s4", -99); b.li("s5", 0); b.li("s6", 0)
b.label("uc_loop")
b.la("t0", G_PVT_TEMP); b.slli("t1", "s2", 1); b.add("t0", "t0", "t1")
b.lh("s7", 0, "t0")           # s7 = chip temp (°C)
# Load lbl pointer into t3 -> save at sp+92? No, recompute from s1+0x60+s2*8
b.li("t0", 1)
b.blt("s7", "t0", "uc_na")
# Valid temp: update min/max/sum/cnt
b.bge("s7", "s3", "uc_nmin"); b.mv("s3", "s7"); b.label("uc_nmin")
b.bge("s4", "s7", "uc_nmax"); b.mv("s4", "s7"); b.label("uc_nmax")
b.add("s5", "s5", "s7"); b.addi("s6", "s6", 1)
# Format "%d°"
b.addi("a0", "sp", 32); b.li("a1", 16); b.la("a2", L_A["str_fmt_c"]); b.mv("a3", "s7")
b.call(SNPRINTF_PLT)
# Color: >=82 red (#ff7875), >=75 amber (#f3a965), else mint (#9aef9e)
b.li("a0", 0x9AEF9E)
b.li("t0", 75); b.blt("s7", "t0", "uc_col_ok")
b.li("a0", 0xF3A965)
b.li("t0", 82); b.blt("s7", "t0", "uc_col_ok")
b.li("a0", 0xFF7875)
b.label("uc_col_ok")
b.call(LV_COLOR_HEX)
b.mv("a1", "a0")
b.slli("t0", "s2", 3); b.addi("t0", "t0", 0x60); b.add("t0", "s1", "t0"); b.ld("a0", 0, "t0")
b.li("a2", 0)
b.call(LV_OBJ_SET_TXT_COL)
b.slli("t0", "s2", 3); b.addi("t0", "t0", 0x60); b.add("t0", "s1", "t0"); b.ld("a0", 0, "t0")
b.addi("a1", "sp", 32)
b.call(LV_LABEL_SET_TEXT)
b.j("uc_next")

b.label("uc_na")
b.slli("t0", "s2", 3); b.addi("t0", "t0", 0x60); b.add("t0", "s1", "t0"); b.ld("a0", 0, "t0")
b.la("a1", L_A["str_dash"])
b.call(LV_LABEL_SET_TEXT)

b.label("uc_next")
b.addi("s2", "s2", 1)
b.li("t0", 12)
b.blt("s2", "t0", "uc_loop")

# 3. Min / Avg / Max footer
b.beq("s6", "zero", "uc_hash")
b.divw("a4", "s5", "s6")
b.mv("a3", "s3"); b.mv("a5", "s4")
b.addi("a0", "sp", 32); b.li("a1", 64); b.la("a2", L_A["str_fmt_mm"])
b.call(SNPRINTF_PLT)
b.ld("a0", 0x50, "s1"); b.addi("a1", "sp", 32); b.call(LV_LABEL_SET_TEXT)

# 4. Hashrate footer from read_lcdv2
b.label("uc_hash")
b.mv("a0", "sp")
b.call(L_A["read_lcdv2"])
b.li("t0", 3)
b.blt("a0", "t0", "uc_done")
b.lw("t0", 8, "sp")           # hash_x100
b.li("t1", 100); b.divu("a3", "t0", "t1"); b.remu("a4", "t0", "t1")
b.addi("a0", "sp", 32); b.li("a1", 64); b.la("a2", L_A["str_fmt_th"])
b.call(SNPRINTF_PLT)
b.ld("a0", 0x58, "s1"); b.addi("a1", "sp", 32); b.call(LV_LABEL_SET_TEXT)

b.label("uc_done")
b.ld("ra", 152, "sp"); b.ld("s1", 144, "sp"); b.ld("s2", 136, "sp"); b.ld("s3", 128, "sp")
b.ld("s4", 120, "sp"); b.ld("s5", 112, "sp"); b.ld("s6", 104, "sp"); b.ld("s7", 96, "sp")
b.addi("sp", "sp", 160)
b.ret()

# Pad to 0x000CF860 so init_chart_screen has a fixed known entry address!
cur_pc = b.pc()
print(f"Cores screen code ends at 0x{cur_pc:08x} (target <= 0x000cf860)")
assert cur_pc <= 0x000CF860, f"Cores screen code overflowed 0x000cf860: 0x{cur_pc:08x}"
b.raw(b"\x00" * (0x000CF860 - cur_pc))

# --- 4E. init_chart_screen @ 0x000CF860 (Live W / V / A chart) ---
# BSS_STATE offsets:
#   +0xC0: scr_chart, +0xC8: chart_obj, +0xD0: ser_w, +0xD8: ser_v, +0xE0: ser_a
#   +0xE8: lbl_w, +0xF0: lbl_v, +0xF8: lbl_a, +0x100: lbl_foot
b.label("init_chart_screen")
b.addi("sp", "sp", -32)
b.sd("ra", 24, "sp"); b.sd("s1", 16, "sp"); b.sd("s2", 8, "sp"); b.sd("s3", 0, "sp")
b.la("s1", BSS_STATE)
b.call(LCD_CREATE_SCREEN)
b.mv("s3", "a0")                # s3 = scr_chart
b.sd("s3", 0xC0, "s1")

# Dark navy background #030810
b.li("a0", 0x030810); b.call(LV_COLOR_HEX)
b.mv("a1", "a0"); b.mv("a0", "s3"); b.li("a2", 0); b.call(LV_OBJ_SET_BG_COL)

# Header + 3 color-coded live readout labels + footer
emit_make_lbl(b, "s3", FONT_14, L_A["str_chart_hdr"], 0x8DC5FF,   0, -88, None)
emit_make_lbl(b, "s3", FONT_14, L_A["str_dash"],      0xF3A965, -62, -66, 0xE8)  # Watts (amber)
emit_make_lbl(b, "s3", FONT_14, L_A["str_dash"],      0x8DC5FF,   0, -66, 0xF0)  # Volts (cyan)
emit_make_lbl(b, "s3", FONT_14, L_A["str_dash"],      0x9AEF9E,  62, -66, 0xF8)  # Amps  (mint)
emit_make_lbl(b, "s3", FONT_14, L_A["str_dash"],      0xA0B7CA,   0,  82, 0x100) # TH/s | °C

# Create lv_chart (176x104 centered at x=0, y=+8)
b.mv("a0", "s3"); b.call(LV_CHART_CREATE)
b.mv("s2", "a0")                # s2 = chart
b.sd("s2", 0xC8, "s1")

b.mv("a0", "s2"); b.li("a1", 176); b.li("a2", 104); b.call(LV_OBJ_SET_SIZE)
b.mv("a0", "s2"); b.li("a1", 9);   b.li("a2", 0);   b.li("a3", 8); b.call(LV_OBJ_ALIGN)
b.mv("a0", "s2"); b.li("a1", 1);   b.call(LV_CHART_SET_TYPE)    # LV_CHART_TYPE_LINE = 1
b.mv("a0", "s2"); b.li("a1", 48);  b.call(LV_CHART_SET_CNT)     # 48 samples (48s window)
b.mv("a0", "s2"); b.li("a1", 0);   b.li("a2", 0); b.li("a3", 100); b.call(LV_CHART_SET_RNG)
b.mv("a0", "s2"); b.li("a1", 3);   b.li("a2", 4); b.call(LV_CHART_SET_DIV)

# Chart styling: bg #071222, border 1px #1E3A5F, radius 10, line_width 2 (ITEMS), point size 0 (INDICATOR)
b.li("a0", 0x071222); b.call(LV_COLOR_HEX)
b.mv("a1", "a0"); b.mv("a0", "s2"); b.li("a2", 0); b.call(LV_OBJ_SET_BG_COL)
b.li("a0", 0x1E3A5F); b.call(LV_COLOR_HEX)
b.mv("a1", "a0"); b.mv("a0", "s2"); b.li("a2", 0); b.call(LV_OBJ_SET_BD_COL)
b.mv("a0", "s2"); b.li("a1", 1);  b.li("a2", 0);       b.call(LV_OBJ_SET_BD_W)
b.mv("a0", "s2"); b.li("a1", 10); b.li("a2", 0);       b.call(LV_OBJ_SET_RADIUS)
b.mv("a0", "s2"); b.li("a1", 2);  b.li("a2", 0x50000); b.call(LV_OBJ_SET_LN_W)    # LV_PART_ITEMS
b.mv("a0", "s2"); b.li("a1", 0);  b.li("a2", 0x20000); b.call(LV_OBJ_SET_WIDTH)   # LV_PART_INDICATOR
b.mv("a0", "s2"); b.li("a1", 0);  b.li("a2", 0x20000); b.call(LV_OBJ_SET_HEIGHT)

# Add 3 series: W (#F3A965), V (#8DC5FF), A (#9AEF9E) on PRIMARY_Y (0)
b.li("a0", 0xF3A965); b.call(LV_COLOR_HEX)
b.mv("a1", "a0"); b.mv("a0", "s2"); b.li("a2", 0); b.call(LV_CHART_ADD_SER); b.sd("a0", 0xD0, "s1")
b.li("a0", 0x8DC5FF); b.call(LV_COLOR_HEX)
b.mv("a1", "a0"); b.mv("a0", "s2"); b.li("a2", 0); b.call(LV_CHART_ADD_SER); b.sd("a0", 0xD8, "s1")
b.li("a0", 0x9AEF9E); b.call(LV_COLOR_HEX)
b.mv("a1", "a0"); b.mv("a0", "s2"); b.li("a2", 0); b.call(LV_CHART_ADD_SER); b.sd("a0", 0xE0, "s1")

# Initial sample + 1000ms timer
b.li("a0", 0); b.call("update_chart_screen")
b.la("a0", "update_chart_screen"); b.li("a1", 1000); b.li("a2", 0); b.call(LV_TIMER_CREATE)

b.mv("a0", "s3")
b.ld("ra", 24, "sp"); b.ld("s1", 16, "sp"); b.ld("s2", 8, "sp"); b.ld("s3", 0, "sp")
b.addi("sp", "sp", 32)
b.ret()

# --- 4F. update_chart_screen(lv_timer_t *) ---
b.label("update_chart_screen")
b.addi("sp", "sp", -144)
b.sd("ra", 136, "sp"); b.sd("s1", 128, "sp"); b.sd("s2", 120, "sp"); b.sd("s3", 112, "sp"); b.sd("s4", 104, "sp")
b.la("s1", BSS_STATE)
b.mv("a0", "sp")
b.call(L_A["read_lcdv2"])
b.li("t0", 7)
b.blt("a0", "t0", "uch_done")

# s2 = vbus_mV, s3 = ibus_mA, s4 = watts_x10
b.lw("s2", 20, "sp")
b.lw("t0", 24, "sp")
b.li("s3", 0)
b.beq("t0", "zero", "uch_i0")
b.addi("t0", "t0", -1); b.li("t1", 1000); b.divu("s3", "t0", "t1")
b.label("uch_i0")
b.mul("t0", "s2", "s3"); b.li("t1", 100000); b.divu("s4", "t0", "t1")
b.bne("s4", "zero", "uch_w_ok")
b.lw("t0", 4, "sp"); b.li("t1", 10); b.mul("s4", "t0", "t1")
b.label("uch_w_ok")

# 1. Update top readout labels: W, V, A
b.li("t1", 10); b.divu("a3", "s4", "t1"); b.remu("a4", "s4", "t1")
b.addi("a0", "sp", 32); b.li("a1", 32); b.la("a2", L_A["str_ch_w"]); b.call(SNPRINTF_PLT)
b.ld("a0", 0xE8, "s1"); b.addi("a1", "sp", 32); b.call(LV_LABEL_SET_TEXT)

b.li("t1", 1000); b.divu("a3", "s2", "t1"); b.remu("t0", "s2", "t1")
b.li("t1", 100);  b.divu("a4", "t0", "t1")
b.addi("a0", "sp", 32); b.li("a1", 32); b.la("a2", L_A["str_ch_v"]); b.call(SNPRINTF_PLT)
b.ld("a0", 0xF0, "s1"); b.addi("a1", "sp", 32); b.call(LV_LABEL_SET_TEXT)

b.li("t1", 1000); b.divu("a3", "s3", "t1"); b.remu("t0", "s3", "t1")
b.li("t1", 10);   b.divu("a4", "t0", "t1")
b.addi("a0", "sp", 32); b.li("a1", 32); b.la("a2", L_A["str_ch_a"]); b.call(SNPRINTF_PLT)
b.ld("a0", 0xF8, "s1"); b.addi("a1", "sp", 32); b.call(LV_LABEL_SET_TEXT)

# 2. Push normalized 0..100 points to chart:
#    W: watts_x10 / 15 (0..150W -> 0..100)
b.li("t1", 15); b.divu("a2", "s4", "t1")
b.li("t0", 100); b.blt("a2", "t0", "uch_w_c"); b.li("a2", 100); b.label("uch_w_c")
b.ld("a0", 0xC8, "s1"); b.ld("a1", 0xD0, "s1"); b.call(LV_CHART_SET_NEXT)

#    V: (vbus_mV - 20000) / 100 (20..30V -> 0..100)
b.li("t0", 20000); b.li("a2", 0); b.blt("s2", "t0", "uch_v_c")
b.sub("t0", "s2", "t0"); b.li("t1", 100); b.divu("a2", "t0", "t1")
b.li("t0", 100); b.blt("a2", "t0", "uch_v_c"); b.li("a2", 100); b.label("uch_v_c")
b.ld("a0", 0xC8, "s1"); b.ld("a1", 0xD8, "s1"); b.call(LV_CHART_SET_NEXT)

#    A: ibus_mA / 60 (0..6A -> 0..100)
b.li("t1", 60); b.divu("a2", "s3", "t1")
b.li("t0", 100); b.blt("a2", "t0", "uch_a_c"); b.li("a2", 100); b.label("uch_a_c")
b.ld("a0", 0xC8, "s1"); b.ld("a1", 0xE0, "s1"); b.call(LV_CHART_SET_NEXT)

# 3. Footer: "%u.%02u TH/s  |  %d°C"
b.lw("t0", 8, "sp"); b.li("t1", 100); b.divu("a3", "t0", "t1"); b.remu("a4", "t0", "t1")
b.lw("a5", 12, "sp")
b.addi("a0", "sp", 32); b.li("a1", 64); b.la("a2", L_A["str_ch_foot"]); b.call(SNPRINTF_PLT)
b.ld("a0", 0x100, "s1"); b.addi("a1", "sp", 32); b.call(LV_LABEL_SET_TEXT)

b.label("uch_done")
b.ld("ra", 136, "sp"); b.ld("s1", 128, "sp"); b.ld("s2", 120, "sp"); b.ld("s3", 112, "sp"); b.ld("s4", 104, "sp")
b.addi("sp", "sp", 144)
b.ret()

block_b = b.build()
print(f"Block B (0x000CF000): {len(block_b)} bytes (ends at 0x{0xCF000+len(block_b):08x}, limit 0x000d0000)")
assert 0x000CF000 + len(block_b) <= 0x000D0000

# ==============================================================================
# 5. Patch Phosphor OS mm_miner (ino=118)
# ==============================================================================
with open(phos_mm_path, "rb") as f:
    mm = bytearray(f.read())

def patch_mm_code(vaddr, new_bytes, expected=None):
    off = vaddr - 0x10000
    if expected is not None:
        actual = bytes(mm[off:off+len(expected)])
        assert actual == expected, f"Mismatch at 0x{vaddr:08x}: exp {expected.hex()}, got {actual.hex()}"
    mm[off:off+len(new_bytes)] = new_bytes

# Hook 1: cali_param_get @ 0x0003b9e0 -> phosphor_apply_oc
patch_mm_code(0x0003B9E0, struct.pack("<II", *emit_call_raw(0x0003B9E0, L_A["phosphor_apply_oc"])),
              expected=struct.pack("<II", 0xFD045703, 0x00E79523))

# Hook 2: lcd_regular_show_switch @ 0x000450b6..0x000450e5 (replace %4 wrap with call to hook_regular_switch)
# Original 0x450b6..0x450e2 computes next show_id in a5 and stores to -18(s0), then jumps to 0x450e6!
# At 0x450b0: lhu a5, -18(s0); sext.w a5, a5 -> at 0x450b6 a5 holds current show_id!
# Replace 0x450b6..0x450e6 (48 bytes) with: call hook_regular_switch; sh a5, -18(s0); j 0x450e6 (+ nops)
# Wait: also at 0x450f2..0x45112 it loads priority from lcd_const_table[idx] into ptr->priority!
# For idx 25/26, if we load lcd_const_table[1] instead of [25]/[26], we don't touch bno=411/412!
# Let's check: 0x450f2..0x45114 is: lhu a5, -18(s0); ... a4 = *(uint32*)(0x1ac110 + a5*0x86); sw a4, 0(a5_ptr)?
# Let's handle 0x450b6..0x450e6 cleanly first:
rs_patch = bytearray()
rs_patch.extend(struct.pack("<II", *emit_call_raw(0x000450B6, L_A["hook_regular_switch"])))  # 8B @ 450b6
rs_patch.extend(struct.pack("<I", enc_s(0x23, 1, "s0", "a5", -18)))                           # 4B @ 450be: sh a5, -18(s0)
rs_patch.extend(struct.pack("<I", enc_j("zero", 0x000450E6 - 0x000450C2)))                    # 4B @ 450c2: j 0x450e6
rs_patch.extend(b"\x00" * (0x450E6 - 0x450C6))                                                # 32B zeros (deflate headroom!)
patch_mm_code(0x000450B6, bytes(rs_patch), expected=bytes.fromhex("852781273e879b57f7419bd7e7013d9f0d8bbb07f74081272317f4fe8357e4fe812781c78357e4fe11a085472317f4fe"))

# At 0x450f2..0x45114 (34B): original code copied all 32 bits of lcd_const_table[idx] into ptr->0,
# which overwrote ptr->show_id (+0..+1) when idx was clamped to 1!
# Fix: copy ONLY the upper 16 bits (+2..+3 = priority/flags) from lcd_const_table[idx < 25 ? idx : 1],
# leaving ptr->show_id (+0..+1, already stored at 0x450ee) intact!
stub_450c6 = struct.pack("<IIIIIII",
    enc_i(0x03, "a5", 5, "s0", -18),        # 0x450c6: lhu a5, -18(s0)
    enc_i(0x13, "t0", 0, "zero", 25),       # 0x450ca: li  t0, 25
    enc_b(4, "a5", "t0", 8),                # 0x450ce: blt a5, t0, 0x450d6
    enc_i(0x13, "a5", 0, "zero", 1),        # 0x450d2: li  a5, 1
    enc_i(0x13, "t0", 0, "zero", 134),      # 0x450d6: li  t0, 134
    enc_r(0x33, "a4", 0, "a5", "t0", 1),    # 0x450da: mul a4, a5, t0
    enc_j("zero", 0x000450F6 - 0x000450DE), # 0x450de: j   0x450f6
)
patch_mm_code(0x000450C6, stub_450c6)
tail_450f2 = struct.pack("<IIIIIIIIH",
    enc_j("zero", 0x000450C6 - 0x000450F2), # 0x450f2: j    0x450c6
    enc_u(0x37, "a5", 0x1ac),               # 0x450f6: lui  a5, 0x1ac
    enc_i(0x13, "a5", 0, "a5", 272),        # 0x450fa: addi a5, a5, 272
    enc_r(0x33, "a5", 0, "a5", "a4", 0),    # 0x450fe: add  a5, a5, a4
    enc_i(0x03, "a4", 5, "a5", 2),          # 0x45102: lhu  a4, 2(a5)  (flags/prio ONLY!)
    enc_i(0x03, "a5", 3, "s0", -32),        # 0x45106: ld   a5, -32(s0)
    enc_s(0x23, 1, "a5", "a4", 2),          # 0x4510a: sh   a4, 2(a5)  (preserve show_id @ +0!)
    enc_j("zero", 0x00045114 - 0x0004510E), # 0x4510e: j    0x45114
    0x0001,                                 # 0x45112: c.nop
)
patch_mm_code(0x000450F2, tail_450f2,
              expected=bytes.fromhex("8357e4fe1b870700930760083307f702b7c71a0093870711ba979843833704fe98c3"))

# Hook 3: get_screen_index @ 0x0004a9b4 -> jump to hook_get_screen_index (using auipc+jr t0)
hi20, lo12 = split_pcrel(0x0004A9B4, L_A["hook_get_screen_index"])
patch_mm_code(0x0004A9B4, struct.pack("<II", enc_u(0x17, "t0", hi20), enc_i(0x67, "zero", 0, "t0", lo12)),
              expected=bytes.fromhex("557186e5a2e18009"))

# Hook 4: lcd_switch_screen @ 0x0004a5f6..0x0004a60e (24 bytes!) -> call hook_switch_screen + j 0x4a60e + zeros!
sw_patch = bytearray()
sw_patch.extend(struct.pack("<II", *emit_call_raw(0x0004A5F6, L_A["hook_switch_screen"])))  # 8B @ 4a5f6
sw_patch.extend(struct.pack("<I", enc_j("zero", 0x0004A60E - 0x0004A5FE)))                  # 4B @ 4a5fe
sw_patch.extend(b"\x00" * (0x4A60E - 0x4A602))                                              # 12B zeros!
patch_mm_code(0x0004A5F6, bytes(sw_patch),
              expected=bytes.fromhex("b7d71a00938687080327c4fdba878607ba978e07b6979c6b"))

# Hook 5: lcd_hardware_update @ 0x00045432..0x00045442 (16B) -> jump to hook_hw_update (+ 8B zeros)
hi20, lo12 = split_pcrel(0x00045432, L_A["hook_hw_update"])
patch_mm_code(0x00045432, struct.pack("<II", enc_u(0x17, "t0", hi20), enc_i(0x67, "zero", 0, "t0", lo12)) + b"\x00" * 8,
              expected=bytes.fromhex("8327c4fd812789e78357a4fd8127e1c7"))

# Write Block B @ 0x000CF000..0x000D0000 (bno=191, unused lv_spangroup)
mm[0x000CF000 - 0x10000 : 0x000D0000 - 0x10000] = block_b + b"\x00" * (0x1000 - len(block_b))
# Zero unused Bitstream Vera license text @ 0x00607000..0x006078a0 so bno=478 compresses tightly!
def vaddr_to_seg_off(v): return 0x1D7000 + (v - 0x00600000)
mm[vaddr_to_seg_off(0x00607000) : vaddr_to_seg_off(0x006078A0)] = b"\x00" * 0x8A0
# Confirm "STATUS=S," at 0x006078a8 is untouched!
assert mm[vaddr_to_seg_off(0x006078A8) : vaddr_to_seg_off(0x006078B2)] == b"STATUS=S,\x00"
# Write Block A @ 0x00607900..0x00608000
mm[vaddr_to_seg_off(0x00607900) : vaddr_to_seg_off(0x00607900) + len(block_a)] = block_a

print("Patched Phosphor mm_miner (8-mode UC/UV/OC + 2 new 240x240 LCD screens) successfully.")

# ==============================================================================
# 6. Patch Phosphor OS dashboard.html (ino=77, exact 44,022 bytes) with 8-mode UC/UV/OC
# ==============================================================================
with open(phos_dash_path, "rb") as f:
    orig_dash = f.read()
assert len(orig_dash) == 44022

prefix = orig_dash[:20480]  # bno=0..4 untouched!
suffix = orig_dash[20480:].decode("utf-8")

power_card_marker = """      <p id="mode-note">Waiting for controller status.</p>
    </article>
  </div>"""
assert power_card_marker in suffix

oc_card_html = """      <p id="mode-note">Waiting for controller status.</p>
    </article>
    <article class="card">
      <h2>Tuning (UC / UV / OC)</h2>
      <div class="actions" id="oc-modes">
        <button value="1" disabled>UC -2</button><button value="2" disabled>UC -1</button><button value="3" disabled>UV</button><button value="0" disabled>Stock</button><button value="4" disabled>Eff OC</button><button value="5" disabled>OC +1</button><button value="6" disabled>OC +2</button><button value="7" disabled>OC +3</button>
      </div>
      <p id="oc-note">Select tuning preset.</p>
    </article>
  </div>"""
suffix = suffix.replace(power_card_marker, oc_card_html, 1)

load_marker = "loadCooling().catch(() => {});"
assert load_marker in suffix

# Share readConf/saveConf between cooling and tuning to save ~180 bytes in bno=10
suffix = suffix.replace(
    "const value = await apiShell('if [ -f ' + coolingPath + ' ]; then cat ' + coolingPath + '; fi');",
    "const value = await readConf(coolingPath);", 1
)
suffix = suffix.replace(
    """const command = setting
      ? 'f=$(mktemp ' + coolingPath + '.XXXXXX) || exit 1; printf %s ' + "'" + setting + "'" +
        ' > "$f" && mv -f "$f" ' + coolingPath + ' && echo SAVED; rm -f "$f"'
      : 'rm -f ' + coolingPath + ' && echo SAVED';
    if (await apiShell(command) !== 'SAVED') throw new Error('Setting was not saved');""",
    "if (await saveConf(coolingPath, setting) !== 'SAVED') throw 0;", 1
)

oc_js = """const readConf=p=>apiShell('if [ -f '+p+' ]; then cat '+p+'; fi'),saveConf=(p,v)=>apiShell(v?'f=$(mktemp '+p+'.XXXXXX)||exit 1;printf %s \\x27'+v+'\\x27>"$f"&&mv -f "$f" '+p+'&&echo SAVED;rm -f "$f"':'rm -f '+p+'&&echo SAVED');
const ocPath='/data/userdata/phosphor-oc.conf',ocBtns=[...el('oc-modes').querySelectorAll('button')];let ocLvl=0;
const ocD=[[0,0,0],[-40,-52,-12],[-20,-26,-6],[0,-26,-3],[20,-26,4],[20,26,7],[35,52,10],[50,78,12]];
function drawOc(){for(const b of ocBtns){b.disabled=!switchable||sending;b.setAttribute('aria-pressed',Number(b.value)===ocLvl);}const t=ocD[ocLvl]||ocD[0];show('oc-note',ocLvl?(t[0]>0?'+':'')+t[0]+' MHz / '+(t[1]>0?'+':'')+t[1]+' mV / '+(t[2]>0?'+':'')+t[2]+' W':'Stock (0 MHz / 0 mV)');}
async function loadOc(){const v=await readConf(ocPath),m=/^oc ([1-7])$/.exec(v.trim());ocLvl=m?Number(m[1]):0;drawOc();}
for(const b of ocBtns)b.onclick=async()=>{const lvl=Number(b.value);if(sending||!switchable||lvl<0||lvl>7)return;sending=true;for(const x of[...modeButtons,...hardwareButtons,...ocBtns])x.disabled=true;show('feedback','Applying tuning…');try{if(await saveConf(ocPath,lvl?'oc '+lvl:'')!=='SAVED')throw 0;ocLvl=lvl;const cur=currentProfile,alt=cur===2?1:2;await rpc('ascset|0,workmode,set,'+alt);await new Promise(r=>setTimeout(r,1200));await rpc('ascset|0,workmode,set,'+cur);show('feedback','Tuning saved.');}catch{show('feedback','Tuning failed.');}finally{sending=false;drawOc();refresh();}};
const _origRender=renderStats;renderStats=raw=>{_origRender(raw);drawOc();};
loadOc().catch(()=>{});
loadCooling().catch(() => {});"""
suffix = suffix.replace(load_marker, oc_js, 1)

# Compact suffix cleanly so all blocks bno=5..10 fit their exact UBIFS deflate targets
suffix = suffix.replace(
    "Auto increases duty as ASIC temperature rises above the target. The factory target caps the setting. The manual curve sets a minimum duty. Both modes retain factory protection and reach full duty by 90 °C.",
    "Auto targets ASIC temp; manual curve sets min PWM. Factory thermal protection stays active (100% by 90 °C)."
)
suffix = suffix.replace("Drag the five points or enter their values below the graph.", "Drag points or edit values below.")
suffix_compact = re.sub(r"^\s*//[^\n]*$", "", suffix, flags=re.M)
suffix_compact = re.sub(r"\n[ \t]+", "\n", suffix_compact)
suffix_compact = re.sub(r"\n{2,}", "\n", suffix_compact)
suffix_compact = re.sub(r">\n<", "><", suffix_compact)
for old_s, new_s in [
    ("Last observed increase in accepted shares: ", "Last share: "),
    ("Waiting for a change in accepted shares.", "Waiting for shares."),
    ("Waiting for an active pool and share counters.", "Waiting for pool."),
    ("Enter a valid target or a non-decreasing fan curve.", "Invalid fan setting."),
    ("Could not save cooling settings.", "Cooling save failed."),
    ("Cooling settings saved.", "Cooling saved."),
    ("Reset the filter usage counter after cleaning?", "Reset filter counter?"),
    ("Profile changes are locked by the controller (ADJ=0).", "Locked (ADJ=0)."),
    ("Profile availability is unknown.", "Profile unavailable."),
    ("Same sample as the device LCD", "Device LCD sample"),
    ("LCD sample unavailable or stale", "LCD sample stale"),
    ("Waiting for controller status.", "Waiting..."),
    ("Waiting for pool status.", "Waiting..."),
    ("Filter counter unavailable.", "Filter N/A."),
    ("Filter usage counter: ", "Filter: "),
    ("The factory lighting mode also controls the LCD backlight.", "Controls LED & LCD backlight."),
    ("Charts show the last 120 readings in this session.", "Last 120 samples."),
    ("The miner accepted the command.", "Command accepted."),
    ("The miner rejected the command.", "Command rejected."),
    ("Could not reach the miner API.", "API unreachable."),
    ("document.createElement(", "dc("),
]:
    suffix_compact = suffix_compact.replace(old_s, new_s)
suffix_compact = suffix_compact.replace("const el = id => document.getElementById(id);", "const el=id=>document.getElementById(id),dc=t=>document.createElement(t);", 1)
nl_pos = suffix_compact.find("\n", 12300)
suffix_compact = suffix_compact[:nl_pos + 1] + "/*" + "=" * 140 + "*/\n" + suffix_compact[nl_pos + 1:]

suffix_bytes = suffix_compact.encode("utf-8")
new_total = len(prefix) + len(suffix_bytes)
print(f"New dashboard.html size before pad: {new_total} (target 44022, diff={44022 - new_total:+d})")
assert new_total <= 44022
rem = 44022 - new_total
pad = (b"\n<!-- " + (b"=" * (rem - 10)) + b" -->") if rem >= 10 else (b" " * rem)
new_dash = prefix + suffix_bytes + pad
assert len(new_dash) == 44022

# ==============================================================================
# 7. Patch phosphor_app_ubi.bin in-place and write Phosphor_OS_Nano3S_OC_v2.kdimg
# ==============================================================================
def patch_ubi_image(ubi_path, file_replacements):
    with open(ubi_path, "rb") as f:
        ubi = bytearray(f.read())
    peb_size = 0x20000
    patched_blocks = 0
    overflows = []
    for peb_i in range(len(ubi) // peb_size):
        peb_start = peb_i * peb_size
        peb = ubi[peb_start : peb_start + peb_size]
        if peb[:4] != b"UBI#" or peb[0x800:0x804] != b"UBI!":
            continue
        if struct.unpack(">I", peb[0x808:0x80C])[0] != 0:
            continue
        leb_start = peb_start + 0x1000
        off = 0
        while off + 24 <= (peb_size - 0x1000):
            abs_off = leb_start + off
            if struct.unpack("<I", ubi[abs_off : abs_off + 4])[0] != 0x06101831:
                break
            crc, sqnum, nlen, ntype, group = struct.unpack("<IQIBB", ubi[abs_off+4 : abs_off+22])
            if ntype == 1:
                inum, k = struct.unpack("<II", ubi[abs_off+24 : abs_off+32])
                bno = k & 0x1FFFFFFF
                if inum in file_replacements:
                    usize, ctype = struct.unpack("<IH", ubi[abs_off+40 : abs_off+46])
                    blk_raw = file_replacements[inum][bno * 4096 : bno * 4096 + usize]
                    old_cdata = bytes(ubi[abs_off+48 : abs_off+nlen])
                    old_raw = zlib.decompress(old_cdata, -15) if ctype == 2 else old_cdata[:usize]
                    if blk_raw != old_raw:
                        target_clen = nlen - 48
                        raw_z = zlib.compressobj(9, zlib.DEFLATED, -15)
                        zlen = len(raw_z.compress(blk_raw) + raw_z.flush())
                        print(f"  Checking ino={inum} bno={bno}: zlen={zlen} target={target_clen} (headroom={target_clen - zlen:+d})")
                        if ctype == 2 and zlen > target_clen:
                            overflows.append((inum, bno, zlen, target_clen))
                        else:
                            new_cdata = compress_exact_deflate(blk_raw, target_clen) if ctype == 2 else blk_raw
                            ubi[abs_off+48 : abs_off+nlen] = new_cdata
                            new_crc = (~zlib.crc32(ubi[abs_off+8 : abs_off+nlen])) & 0xFFFFFFFF
                            struct.pack_into("<I", ubi, abs_off + 4, new_crc)
                            patched_blocks += 1
                            print(f"  Patched ino={inum} bno={bno} (target_clen={target_clen})")
            off = (off + nlen + 7) & ~7
    if overflows:
        raise AssertionError(f"UBIFS deflate overflows: {overflows}")
    print(f"Patched {patched_blocks} UBIFS data blocks.")
    return bytes(ubi)

new_app_ubi = patch_ubi_image(phos_ubi_path, {
    118: bytes(mm),
    77:  new_dash,
})

with open(phos_kdimg_path, "rb") as f:
    kdimg = bytearray(f.read())
assert struct.unpack("<I", kdimg[16:20])[0] == 1
off = 0x200
p_magic, flash_off, p_size, flag1, max_size, flag2, content_off, content_size = struct.unpack("<IIIIIIII", kdimg[off:off+32])
assert len(new_app_ubi) == content_size
kdimg[content_off : content_off + content_size] = new_app_ubi
new_sha = hashlib.sha256(new_app_ubi).digest()
kdimg[off + 32 : off + 64] = new_sha
new_hdr_crc = zlib.crc32(kdimg[0x200:0x300]) & 0xFFFFFFFF
struct.pack_into("<I", kdimg, 20, new_hdr_crc)

with open(out_kdimg_path, "wb") as f:
    f.write(kdimg)

print(f"Updated app_ubi SHA256: {new_sha.hex()}")
print(f"Updated kdimg header CRC32: 0x{new_hdr_crc:08x}")
print(f"SUCCESS! Wrote {len(kdimg)} bytes to {out_kdimg_path}")
