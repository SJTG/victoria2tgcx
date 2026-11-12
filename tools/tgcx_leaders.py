#!/usr/bin/env python3
"""Characters: party leaders, cabecillas, vision, agenda and relation (D25, D34, D37-D43).

    python tools/tgcx_leaders.py            # print the loaded characters and rules

Pure data and arithmetic, no TGC needed. tools/gen_law_catalog.py turns it into
the negotiation script and tools/tgcx_bill_gui.py into the DLL's tables. See
data/tgcx_leaders.txt for the file format.

The legacy leader-blended bloc stance (D31) stays for tools/gen_laws.py, behind
`blend_bloc_stance = yes`.
"""

import os
import sys
from dataclasses import dataclass, field

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tgc_scan import parse, read  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATH = os.path.join(ROOT, "data", "tgcx_leaders.txt")
SLOTS = 2                                   # characters per bloc: leader, cabecilla
TIERS = ("abstain", "aye")
BANDS = ("hostile", "neutral", "friendly", "ally")   # band 1..4; 0 = refuses
CODES = ("p2", "p1", "z", "m1", "m2")
RESERVED = ("enabled", "blend_bloc_stance", "relation", "auto")


@dataclass
class Character:
    name: str
    share: int                      # percent of the bloc's seats he leads
    relation: int = -1              # start value; -1 = the rules' default
    rival: str = ""                 # a bloc; "" = none
    trait: str = ""
    stance: dict = field(default_factory=dict)   # law group -> {"ideal": str, "intensity": int}
    agenda: list = None             # law groups in order; None = automatic
    auto: bool = False


@dataclass
class Party:
    key: str
    bloc: str
    leader: str
    seats: int
    cohesion: int
    trait: str = ""
    stance: dict = field(default_factory=dict)
    relation: int = -1
    rival: str = ""
    agenda: list = None
    cabecilla: Character = None


@dataclass
class Rules:
    start: int
    shift: dict                     # stance code -> change of the effective relation
    rival_rules: int
    bands: dict                     # band name -> lowest effective relation
    ask: dict                       # band -> tier -> (steps, days)
    freeze: dict                    # band -> tier -> days
    kept: int
    broken: int
    liked: int
    disliked: int
    auto_cohesion: int
    init_ruling: int = 0            # start relation bonus when the bloc's ideology rules
    init_scale: dict = None         # ideology -> position on the left-right scale (unlisted: no distance term)
    init_distance: dict = None      # distance on that scale -> start relation change


def _stance(rows, where):
    stance = {}
    for g, spec in rows or []:
        s = dict(spec)
        if s.get("intensity") not in ("1", "2") or "ideal" not in s:
            raise ValueError(f"{where}.{g}: needs ideal and intensity 1 or 2")
        stance[g] = {"ideal": s["ideal"], "intensity": int(s["intensity"])}
    return stance


def _relation(d, where):
    if "relation" not in d:
        return -1
    r = int(d["relation"])
    if not 0 <= r <= 10:
        raise ValueError(f"{where}: relation {r} outside 0..10")
    return r


def _agenda(d, where):
    if "agenda" not in d:
        return None
    if not isinstance(d["agenda"], list) or any(k for k, _ in d["agenda"]):
        raise ValueError(f"{where}: agenda is a list of law groups")
    groups = [v for _, v in d["agenda"]]
    if len(set(groups)) != len(groups):
        raise ValueError(f"{where}: agenda repeats a group")
    return groups


def load_rules(path=PATH):
    """The relation rules and the automatic characters' numbers. Fails loudly on a missing key."""
    top = dict(parse(read(path)))
    if "relation" not in top or "auto" not in top:
        raise ValueError("leaders data needs the relation and auto blocks")
    r, auto = dict(top["relation"]), dict(top["auto"])
    shift = {k: int(v) for k, v in r["stance_shift"]}
    bands = {k: int(v) for k, v in r["bands"]}
    if set(shift) != set(CODES) or list(bands) != list(BANDS):
        raise ValueError("relation: stance_shift needs p2 p1 z m1 m2; bands need hostile neutral friendly ally in order")
    if sorted(bands.values()) != list(bands.values()) or len(set(bands.values())) != 4 or not 1 <= bands["hostile"] or bands["ally"] > 10:
        raise ValueError("relation: bands must rise within 1..10")
    ask, freeze = {}, {}
    for band in BANDS[:3]:
        rows, pauses = dict(dict(r["ask"])[band]), dict(dict(r["freeze"])[band])
        ask[band], freeze[band] = {}, {}
        for tier in TIERS:
            a = dict(rows[tier])
            steps, days = int(a["steps"]), int(a["days"])
            if not 0 <= steps <= 5 or days < 0 or (steps and not days):
                raise ValueError(f"relation.ask.{band}.{tier}: steps 0..5, and days when steps > 0")
            ask[band][tier] = (steps, days)
            freeze[band][tier] = int(pauses[tier])
            if freeze[band][tier] < 0:
                raise ValueError(f"relation.freeze.{band}.{tier}: negative days")
    start, coh = int(r["start"]), int(auto["cohesion"])
    if not 0 <= start <= 10 or not 0 <= coh <= 100:
        raise ValueError("relation.start is 0..10 and auto.cohesion 0..100")
    init = dict(r.get("start_relation", []))
    scale = {k: int(v) for k, v in dict(init.get("scale", [])).items()}
    distance = {int(k.removeprefix("d")): int(v) for k, v in dict(init.get("distance", [])).items()}
    if any(not 0 <= v <= 20 for v in scale.values()) or any(not 1 <= k <= 20 for k in distance):
        raise ValueError("relation.start_relation: scale positions 0..20, distance keys d1..d20")
    return Rules(start, shift, int(r["rival_rules"]), bands, ask, freeze,
                 int(r["kept"]), int(r["broken"]), int(r["law_liked"]), int(r["law_disliked"]), coh,
                 int(init.get("ruling", 0)), scale, distance)


def load_flags(path=PATH):
    """-> (enabled, blend_bloc_stance)."""
    top = dict(parse(read(path)))
    out = []
    for key in ("enabled", "blend_bloc_stance"):
        value = top.get(key, "no")
        if value not in ("yes", "no"):
            raise ValueError(f"{key} must be yes or no, not {value!r}")
        out.append(value == "yes")
    return tuple(out)


def load(path=PATH):
    """-> (enabled, {tag: [Party, ...]}). Fails loudly on a malformed row."""
    enabled, countries = False, {}
    for key, body in parse(read(path)):
        if key == "enabled":
            if body not in ("yes", "no"):
                raise ValueError(f"enabled must be yes or no, not {body!r}")
            enabled = body == "yes"
            continue
        if key in RESERVED:
            continue
        if not isinstance(body, list):
            raise ValueError(f"{key}: expected a country block")
        parties = []
        for pkey, pbody in body:
            d = dict(pbody)
            where = f"{key}.{pkey}"
            missing = [k for k in ("bloc", "leader", "seats", "cohesion") if k not in d]
            if missing:
                raise ValueError(f"{where}: missing {', '.join(missing)}")
            coh, seats = int(d["cohesion"]), int(d["seats"])
            if not 0 <= coh <= 100:
                raise ValueError(f"{where}: cohesion {coh} outside 0..100")
            if seats < 0:
                raise ValueError(f"{where}: negative seats")
            second = None
            if "cabecilla" in d:
                c = dict(d["cabecilla"])
                if "name" not in c:
                    raise ValueError(f"{where}.cabecilla: missing name")
                second = Character(c["name"], 100 - coh, _relation(c, where + ".cabecilla"), c.get("rival", ""),
                                   c.get("trait", ""), _stance(c.get("stance"), where + ".cabecilla"),
                                   _agenda(c, where + ".cabecilla"))
            parties.append(Party(pkey, d["bloc"], d["leader"], seats, coh, d.get("trait", ""),
                                 _stance(d.get("stance"), where), _relation(d, where), d.get("rival", ""),
                                 _agenda(d, where), second))
        countries[key] = parties
    return enabled, countries


def lead_party(parties, bloc):
    """The party the bloc follows: most seats, first listed on a tie; None if the bloc has none."""
    best = None
    for p in parties:
        if p.bloc == bloc and (best is None or p.seats > best.seats):
            best = p
    return best


def characters(parties, bloc, rules, singular):
    """The bloc's two characters: [leader, cabecilla]. `parties` is the country's list or None."""
    party = lead_party(parties, bloc) if parties else None
    if party is None:
        coh = rules.auto_cohesion
        return [Character(f"{singular} leader", coh, auto=True), Character(f"{singular} whip", 100 - coh, auto=True)]
    leader = Character(party.leader, party.cohesion, party.relation, party.rival, party.trait, party.stance, party.agenda)
    second = party.cabecilla or Character(f"{singular} whip", 100 - party.cohesion, auto=True)
    return [leader, second]


def packets(share, k):
    """Of k five-seat packets, how many the leader (share percent) leads: nearest, halves up.
    The cabecilla leads the other k - packets(share, k)."""
    return (share * k + 50) // 100


def band_of(rules, effective):
    """0 refuses, 1 hostile, 2 neutral, 3 friendly, 4 ally."""
    return sum(effective >= rules.bands[b] for b in BANDS)


def code_to_int(code):
    """Stance code of gen_laws ('z', 'p1', 'p2', 'm1', 'm2') -> -2..+2."""
    if code == "z":
        return 0
    return int(code[1]) * (1 if code[0] == "p" else -1)


def int_to_code(n):
    return "z" if n == 0 else (f"p{n}" if n > 0 else f"m{-n}")


def blend(cohesion, leader, base):
    """round(c * leader + (1 - c) * base), c in percent, halves away from zero, integers only."""
    num = cohesion * leader + (100 - cohesion) * base
    q, r = divmod(abs(num), 100)
    if 2 * r >= 100:
        q += 1
    return q if num >= 0 else -q


def effective_code(party, base_code, leader_code):
    """Legacy D31: stance code of the party's bloc, leader and ideology blended by cohesion."""
    return int_to_code(blend(party.cohesion, code_to_int(leader_code), code_to_int(base_code)))


if __name__ == "__main__":
    on, data = load()
    rules = load_rules()
    print("enabled:", on, "| blend_bloc_stance:", load_flags()[1])
    print("rules:", rules)
    for tag, ps in data.items():
        for p in ps:
            print(f"{tag} {p.key}: {p.bloc}, {p.leader}, {p.seats} seats, cohesion {p.cohesion}%, "
                  f"relation {p.relation}, {len(p.stance)} stance rows, agenda {p.agenda}, "
                  f"cabecilla {p.cabecilla.name if p.cabecilla else '-'}")


def start_relation(rules, bloc, ruling):
    """Computed start relation of an automatic character: the base, +ruling bonus when his bloc's
    ideology rules, and a change by the distance on the left-right scale to the ruling ideology."""
    value = rules.start
    if bloc == ruling:
        value += rules.init_ruling
    pos, at = (rules.init_scale or {}).get(bloc), (rules.init_scale or {}).get(ruling)
    if pos is not None and at is not None and pos != at:
        d = abs(pos - at)
        steps = [k for k in (rules.init_distance or {}) if k <= d]
        if steps:
            value += rules.init_distance[max(steps)]
    return max(0, min(10, value))
