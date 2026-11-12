#!/usr/bin/env python3
"""Checks for characters (D25, D34, D37-D43) and the legacy leader-blended stance (D31).

    python tools/test_leaders.py

Needs no TGC: the law group is written out here. Exits with 1 on the first
difference.
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gen_laws  # noqa: E402
import tgcx_leaders as L  # noqa: E402
from tgc_scan import parse, read  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def check(name, got, want):
    if got != want:
        print(f"FAIL {name}: got {got!r}, want {want!r}")
        sys.exit(1)
    print(f"ok   {name}")


def write_tmp(text):
    f = tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False)
    f.write(text)
    f.close()
    return f.name


# --- blend: halves round away from zero, 0 and 100 keep one side
check("blend 70% of +1 and -1", L.blend(70, 1, -1), 0)
check("blend 100% is the leader", L.blend(100, 2, -2), 2)
check("blend 0% is the ideology", L.blend(0, 2, -2), -2)
check("blend half rounds up", L.blend(50, 1, 0), 1)
check("blend half rounds away from zero (negative)", L.blend(50, -1, 0), -1)
check("blend 85% of 2 and 1", L.blend(85, 2, 1), 2)
for a in range(-2, 3):
    check(f"code round trip {a}", L.code_to_int(L.int_to_code(a)), a)

# --- the shipped file loads: characters on, the legacy bloc blend off
enabled, data = L.load()
check("shipped file enables its countries", enabled, True)
check("shipped file keeps the legacy blend off", L.load_flags()[1], False)
check("shipped file has ENG parties", sorted(p.key for p in data["ENG"]), ["tories", "whigs"])

# --- rules and characters
R = L.load_rules()
check("bands rise", [R.bands[b] for b in L.BANDS], sorted(R.bands[b] for b in L.BANDS))
check("band of a relation below hostile", L.band_of(R, R.bands["hostile"] - 1), 0)
check("band of the ally threshold", L.band_of(R, R.bands["ally"]), 4)
auto = L.characters(None, "liberal", R, "Liberal")
check("automatic pair shares the bloc", [c.share for c in auto], [R.auto_cohesion, 100 - R.auto_cohesion])
check("automatic pair is marked", [c.auto for c in auto], [True, True])
eng = L.characters(data["ENG"], "conservative", R, "Conservative")
tories = L.lead_party(data["ENG"], "conservative")
check("leader comes from the largest party", (eng[0].name, eng[0].share), (tories.leader, tories.cohesion))
check("written cabecilla leads the rest", (eng[1].name, eng[1].share, eng[1].auto),
      (tories.cabecilla.name, 100 - tories.cohesion, False))
whigs = L.characters(data["ENG"], "liberal", R, "Liberal")
check("a party without a cabecilla gets a whip", (whigs[1].name, whigs[1].auto), ("Liberal whip", True))
check("a bloc without a party is automatic", L.characters(data["ENG"], "reactionary", R, "Reactionary"),
      L.characters(None, "reactionary", R, "Reactionary"))
for share in (0, 30, 50, 70, 85, 100):
    lead = [L.packets(share, k) for k in range(21)]
    rest = [k - n for k, n in enumerate(lead)]
    check(f"packets {share}%: both sides never shrink as the bloc grows",
          (lead == sorted(lead), rest == sorted(rest), lead[20]), (True, True, share // 5))

# --- several parties in one bloc: the bloc follows the one with most seats; ties keep the first listed
TWO = """enabled = yes
ENG = {
	big = { bloc = conservative leader = "A" seats = 55 cohesion = 70 }
	small = { bloc = conservative leader = "B" seats = 30 cohesion = 45 }
	tie1 = { bloc = liberal leader = "C" seats = 5 cohesion = 60 }
	tie2 = { bloc = liberal leader = "D" seats = 5 cohesion = 60 }
}
"""
on, d = L.load(write_tmp(TWO))
check("enabled yes", on, True)
check("largest party leads", L.lead_party(d["ENG"], "conservative").leader, "A")
check("tie keeps first listed", L.lead_party(d["ENG"], "liberal").leader, "C")
check("bloc without parties", L.lead_party(d["ENG"], "reactionary"), None)

# --- malformed rows fail loudly
for name, text in [("cohesion above 100", 'ENG = { p = { bloc = a leader = "x" seats = 1 cohesion = 101 } }'),
                   ("missing leader", "ENG = { p = { bloc = a seats = 1 cohesion = 5 } }"),
                   ("bad intensity", 'ENG = { p = { bloc = a leader = "x" seats = 1 cohesion = 5 stance = { g = { ideal = o intensity = 3 } } } }'),
                   ("relation above 10", 'ENG = { p = { bloc = a leader = "x" seats = 1 cohesion = 5 relation = 11 } }'),
                   ("cabecilla without a name", 'ENG = { p = { bloc = a leader = "x" seats = 1 cohesion = 5 cabecilla = { relation = 3 } } }'),
                   ("agenda repeats a group", 'ENG = { p = { bloc = a leader = "x" seats = 1 cohesion = 5 agenda = { g g } } }')]:
    try:
        L.load(write_tmp(text))
        check(name + " raises", False, True)
    except ValueError:
        check(name + " raises", True, True)

# --- the generator: press_rights 1 -> 2 in the 1836 UK, with the shipped example
laws = parse(read(os.path.join(ROOT, "data", "tgcx_laws.txt")))
aff = parse(read(os.path.join(ROOT, "data", "tgcx_affinity.txt")))
groups = {"press_rights": {"category": "political_reforms", "options": ["state_press", "censored_press", "free_press"], "body": {}}}
ideologies = ["liberal", "conservative", "reactionary"]
g = gen_laws.Gen(laws, aff, groups, ideologies)
check("legacy blend off: the generator has no leaders", g.leaders, {})
base = [g.stance(i, "press_rights", "censored_press", "free_press") for i in g.blocs]
check("ideology stances (law-design §3 example)", dict(zip(g.blocs, base)), {"liberal": "p2", "conservative": "m1", "reactionary": "m2"})
check("disabled: one flag per bloc, as before", g.stance_flag_effects("press_rights", "censored_press", "free_press"),
      [f"set_country_flag = tgcx_stance_{i}_{c}" for i, c in zip(g.blocs, base)])

LEGACY = """ENG = {
	tories = { bloc = conservative leader = "Duke of Wellington" seats = 85 cohesion = 70
		stance = { press_rights = { ideal = free_press intensity = 1 } } }
	whigs = { bloc = liberal leader = "Viscount Melbourne" seats = 10 cohesion = 85 }
}
"""
g.leaders = L.load(write_tmp(LEGACY))[1]          # as with `blend_bloc_stance = yes`
g.check_leaders()
# Tories: leader free_press intensity 1 is +1 for the 1 -> 2 bill; ideology -1; cohesion 70 -> round(0.4) = 0
check("Tories blend to undecided", g.led_stance("ENG", "conservative", "press_rights", "censored_press", "free_press"), "z")
# Whigs have no stance row: the ideology's stance stands
check("Whigs keep the ideology stance", g.led_stance("ENG", "liberal", "press_rights", "censored_press", "free_press"), "p2")
# A bloc with no party keeps the ideology's stance
check("Reactionaries (no party) keep the ideology stance", g.led_stance("ENG", "reactionary", "press_rights", "censored_press", "free_press"), "m2")
fx = g.stance_flag_effects("press_rights", "censored_press", "free_press")
check("enabled: default branch + one branch per tag", len(fx), 2)
check("other countries keep the ideology flags", "NOT = { tag = ENG }" in fx[0] and "tgcx_stance_conservative_m1" in fx[0], True)
check("ENG gets the blended flag", "tgcx_stance_conservative_z" in fx[1] and "tgcx_stance_conservative_m1" not in fx[1], True)

# --- bad data is refused at generation
g.leaders = L.load(write_tmp('enabled = yes\nGBR = { p = { bloc = conservative leader = "x" seats = 1 cohesion = 50 stance = { press_rights = { ideal = nonsense intensity = 1 } } } }'))[1]
try:
    g.check_leaders()
    check("unknown option refused", False, True)
except SystemExit:
    check("unknown option refused", True, True)

print("all ok")
