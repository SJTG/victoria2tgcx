#!/usr/bin/env python3
"""LAW-1: build a reviewable political/social bill catalogue from installed TGC.

Preview (pending affinity choices allowed, output outside the live submod):
    python tools/gen_law_catalog.py --preview E:/v2re/logs/tgcx-law1-preview
Release (only user-reviewed groups, explicit output directory required):
    python tools/gen_law_catalog.py --release <staging> [--groups press_rights ...]

This tool never installs anything. The default LAW-0 generator stays available.
"""

import argparse
import re
from pathlib import Path

from gen_laws import (BLOC, DEFAULT_TGC, EV_CHANGED, EV_FAIL_BY, EV_NO_QUORUM, EV_PASS_BY, EV_PASSED, EV_VETOED,
                      ROOT, Gen, as_dict, balanced, chg, chk,
                      flag, gov_in, load, ors, ser, setv, share, when)
from tgc_scan import parse, read
import tgcx_leaders
from tgcx_law_support import MODES, load_support

CATALOG = Path(ROOT) / "data/tgcx_law_catalog.txt"
CATEGORIES = ("political_reforms", "social_reforms")
EV_CATALOG_COUNT = 420000194
EV_DEAL_BROKEN = 420000200     # + 2 * bloc index + slot: a broken deal with that character
SLOTS = range(tgcx_leaders.SLOTS)
TIERS = tgcx_leaders.TIERS
# tgcx_gui_ask_* / tgcx_owe_*: 0 no deal, 1 nothing asked, 2 a pause on new bills,
# ASK_LAW + 64 * group + 8 * target option + ideal option: a law owed.
ASK_FREE, ASK_FREEZE, ASK_LAW = 1, 2, 3


def unique(items, context):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError(f"{context}: duplicate {key}")
        result[key] = value
    return result


def catalog_data(tgc=DEFAULT_TGC, path=CATALOG, selected=None, release=False):
    laws, _, groups, ideologies = load(tgc)
    catalog = unique(parse(read(path)), "catalogue")
    expected = {g for g, body in groups.items() if body["category"] in CATEGORIES}
    if set(catalog) != expected:
        raise ValueError(f"catalogue groups differ from TGC: missing {sorted(expected-set(catalog))}, "
                         f"unknown {sorted(set(catalog)-expected)}")
    chosen = list(catalog) if selected is None else list(selected)
    if not chosen or len(set(chosen)) != len(chosen) or set(chosen)-expected:
        raise ValueError("select distinct political/social groups present in the catalogue")
    affinity = {i: [] for i in ideologies}
    reviews = {}
    for g, body in catalog.items():
        spec = unique(body, g)
        if set(spec) != {"review", *ideologies}:
            raise ValueError(f"{g}: require review status and all {len(ideologies)} ideology entries")
        reviews[g] = spec["review"]
        if reviews[g] not in ("pending", "approved"):
            raise ValueError(f"{g}: unknown review status")
        for i in ideologies:
            row = unique(spec[i], f"{g}/{i}")
            if set(row) != {"ideal", "intensity"} or row["intensity"] not in ("1", "2"):
                raise ValueError(f"{g}/{i}: require ideal and intensity 1 or 2")
            if row["ideal"] not in ["status_quo", *groups[g]["options"]]:
                raise ValueError(f"{g}/{i}: ideal {row['ideal']} is not an option")
            if g in chosen:
                affinity[i].append((g, spec[i]))
    if release and any(reviews[g] != "approved" for g in chosen):
        raise ValueError("release requires user-approved affinity for every selected group; use --preview")
    bills = []
    for g in chosen:
        opts = groups[g]["options"]
        for frm, to in zip(opts, opts[1:]):
            bills += [(g, [("from", frm), ("to", to)]),
                      (g, [("from", to), ("to", frm)])]
    laws = [(k, bills if k == "bills" else v) for k, v in laws]
    return laws, list(affinity.items()), groups, ideologies, chosen, reviews


class CatalogGen(Gen):
    # Decisions the Bill window sends besides purchases/promises (already guarded).
    DLL_SENT = ("tgcx_audience", "tgcx_withdraw", "tgcx_call_vote", "tgcx_collect_favours", "tgcx_refresh_offers")

    def __init__(self, laws, affinity, groups, ideologies, chosen, support, leaders=tgcx_leaders.PATH):
        self.chosen = chosen
        self.support = support
        super().__init__(laws, affinity, groups, ideologies)
        # Characters (D37-D43): two per bloc. Hand-written countries only when the data is enabled.
        self.rules = tgcx_leaders.load_rules(leaders)
        on, data = tgcx_leaders.load(leaders)
        self.char_data = data if on else {}
        self.targets = {}           # (bloc, slot) -> the law asks this character can make
        self.check_characters()

    # --- characters: who leads which seats, what they want, how they feel

    @staticmethod
    def singular(ideology):
        return Gen.pretty(ideology).replace("Anarcho Liberal", "Anarcho-Liberal")

    def check_characters(self):
        for tag, parties in self.char_data.items():
            for p in parties:
                where = f"leaders {tag}.{p.key}"
                if p.bloc not in self.blocs:
                    raise ValueError(f"{where}: bloc {p.bloc} is not an ideology with a stance")
                for who, c in ((where, p), (where + ".cabecilla", p.cabecilla)):
                    if c is None:
                        continue
                    if c.rival and c.rival not in self.all_ideologies:
                        raise ValueError(f"{who}: rival {c.rival} is not an ideology")
                    for g, spec in c.stance.items():
                        if g not in self.groups:
                            raise ValueError(f"{who}: {g} is not a law group")
                        if spec["ideal"] != "status_quo" and spec["ideal"] not in self.groups[g]["options"]:
                            raise ValueError(f"{who}.{g}: {spec['ideal']} is not an option")
                    for g in c.agenda or []:
                        if g not in self.groups:
                            raise ValueError(f"{who}: agenda {g} is not a law group")
        for i in self.blocs:
            for _, chars in self.bloc_variants(i):
                for c in chars:
                    self.agenda(c, i)

    def bloc_variants(self, i):
        """[(condition, [leader, cabecilla])]: the default pair, then one pair per country whose
        data changes this bloc. The default's condition excludes those countries ('' if none)."""
        default = tgcx_leaders.characters(None, i, self.rules, self.singular(i))
        own = [(tag, tgcx_leaders.characters(parties, i, self.rules, self.singular(i)))
               for tag, parties in sorted(self.char_data.items())]
        own = [(tag, chars) for tag, chars in own if chars != default]
        others = "NOT = { " + " ".join(f"tag = {tag}" for tag, _ in own) + " }" if own else ""
        return [(others, default)] + [(f"tag = {tag}", chars) for tag, chars in own]

    def char_spec(self, c, i, g):
        """The {ideal, intensity} row a character holds on a law group: his own, else his ideology's."""
        return c.stance.get(g) or as_dict(self.aff[i][g])

    def char_stance(self, c, i, g, frm, to):
        return self.spec_stance(self.char_spec(c, i, g), g, frm, to)

    def agenda(self, c, i):
        """[(group, ideal option)] he asks for, in order. Automatic: what his ideology feels strongly about."""
        if c.agenda is None:
            groups = [g for g in self.chosen if int(as_dict(self.aff[i][g])["intensity"]) == 2]
        else:
            groups = [g for g in c.agenda if g in self.chosen]     # a --groups subset drops the others
        out = []
        for g in groups:
            ideal = self.char_spec(c, i, g)["ideal"]
            if ideal == "status_quo":
                if c.agenda is not None:
                    raise ValueError(f"leaders: {c.name} has {g} on his agenda but wants the status quo there")
                continue
            out.append((g, ideal))
        return out

    @staticmethod
    def rel(i, s):
        return f"tgcx_rel_{i}_{s}"

    @staticmethod
    def clamp(var):
        return [when(chk(var, 11), setv(var, 10)), when(f"NOT = {{ {chk(var, 0)} }}", setv(var, 0))]

    def rel_change(self, i, s, n):
        return " ".join([chg(self.rel(i, s), n), *self.clamp(self.rel(i, s))])

    def rel_init(self):
        """Start relations once per country (variables start at 0, which would mean 'refuses').
        A hand-written relation is used as written; an automatic character starts from the base,
        the ruling ideology and the distance to it (tgcx_leaders.start_relation)."""
        lines = []
        for i in self.blocs:
            for cond, chars in self.bloc_variants(i):
                fixed = " ".join(setv(self.rel(i, s), c.relation) for s, c in enumerate(chars) if c.relation >= 0)
                auto = [s for s, c in enumerate(chars) if c.relation < 0]
                base = f"NOT = {{ {flag('rel_init')} }} {cond}".strip()
                if fixed:
                    lines.append(when(base, fixed))
                for r in self.all_ideologies:
                    sets = " ".join(setv(self.rel(i, s), tgcx_leaders.start_relation(self.rules, i, r)) for s in auto)
                    if sets:
                        lines.append(when(f"{base} ruling_party_ideology = {r}", sets))
        return lines + ["set_country_flag = tgcx_rel_init"]

    def stance_lines(self, g, frm, to):
        """Each character's stance on the bill: flags for the script, tgcx_gui_cst_* for the DLL."""
        out = []
        for i in self.blocs:
            for cond, chars in self.bloc_variants(i):
                sets = []
                for s, c in enumerate(chars):
                    code = self.char_stance(c, i, g, frm, to)
                    sets += [f"set_country_flag = tgcx_cs_{i}_{s}_{code}",
                             setv(f"tgcx_gui_cst_{i}_{s}", tgcx_leaders.code_to_int(code))]
                out.append(when(cond, " ".join(sets)) if cond else " ".join(sets))
        return out

    def split_lines(self, i, kinds=("seats", "opposed")):
        """A character's seats: his share of the bloc's five-seat packets (leader: nearest, halves up)."""
        lines = []
        for kind in kinds:
            source, out = f"tgcx_{kind}_{i}", "cseats" if kind == "seats" else "copp"
            lines += [setv(f"tgcx_gui_{out}_{i}_{s}", 0) for s in SLOTS]
            for cond, chars in self.bloc_variants(i):
                for k in range(1, 21):
                    lead = 5 * tgcx_leaders.packets(chars[0].share, k)
                    lines.append(when(f"{cond} {chk(source, 5*k)} NOT = {{ {chk(source, 5*k+5)} }}".strip(), " ".join([
                        setv(f"tgcx_gui_{out}_{i}_0", lead), setv(f"tgcx_gui_{out}_{i}_1", 5*k - lead)])))
        return lines

    def band_lines(self, i, s):
        """tgcx_gui_band: 0 refuses ... 4 ally, from relation + his stance on the bill + his rival in power."""
        r, band = self.rules, f"tgcx_gui_band_{i}_{s}"
        lines = [setv("tgcx_eff", 0)]
        lines += [when(chk(self.rel(i, s), n), chg("tgcx_eff", 1)) for n in range(1, 11)]
        lines += [when(flag(f"cs_{i}_{s}_{code}"), chg("tgcx_eff", n)) for code, n in r.shift.items() if n]
        for cond, chars in self.bloc_variants(i):
            if chars[s].rival and r.rival_rules:
                lines.append(when(f"{cond} ruling_party_ideology = {chars[s].rival}".strip(), chg("tgcx_eff", r.rival_rules)))
        lines.append(setv(band, 0))
        lines += [when(chk("tgcx_eff", r.bands[name]), setv(band, n))
                  for n, name in enumerate(tgcx_leaders.BANDS, 1)]
        return lines

    def ask_value(self, g, cur, ideal, steps, days):
        """(ask, days) for moving group g `steps` options from index cur toward index ideal."""
        if steps == 0:
            return ASK_FREE, 0
        target = cur + (1 if ideal > cur else -1) * min(steps, abs(ideal - cur))
        return ASK_LAW + 64 * self.chosen.index(g) + 8 * target + ideal, days

    def offer_lines(self, i, s):
        """tgcx_gui_ask_* / tgcx_gui_days_* per tier: what this character asks for his followers now.

        The first agenda law that is not at his ideal (nor the bill's own group); else a pause on
        new bills. The band sets how far and how soon. Records every law ask in self.targets."""
        r = self.rules
        band = f"tgcx_gui_band_{i}_{s}"
        var = {t: (f"tgcx_gui_ask_{i}_{s}_{t}", f"tgcx_gui_days_{i}_{s}_{t}") for t in TIERS}
        lines = [setv(v, 0) for t in TIERS for v in var[t]] + [setv("tgcx_pick", 0)]
        lines.append(when(chk(band, 4), " ".join([setv(var[t][0], ASK_FREE) for t in TIERS] + [setv("tgcx_pick", 1)])))
        targets = self.targets.setdefault((i, s), set())

        def in_band(n, effect):
            return when(f"{chk(band, n)} NOT = {{ {chk(band, n+1)} }}", effect)
        for cond, chars in self.bloc_variants(i):
            for g, ideal_name in self.agenda(chars[s], i):
                opts = self.groups[g]["options"]
                ideal = opts.index(ideal_name)
                for cur, option in enumerate(opts):
                    if cur == ideal:
                        continue
                    inner = []
                    for n, name in enumerate(tgcx_leaders.BANDS[:3], 1):
                        sets = []
                        for t in TIERS:
                            ask, days = self.ask_value(g, cur, ideal, *r.ask[name][t])
                            if ask >= ASK_LAW:
                                targets.add(ask)
                            sets += [setv(var[t][0], ask), setv(var[t][1], days)]
                        inner.append(in_band(n, " ".join(sets)))
                    lines.append(when(
                        f"{cond} NOT = {{ {chk('tgcx_pick', 1)} }} {chk(band, 1)} {g} = {option} "
                        f"NOT = {{ {flag(f'billgroup_{g}')} }}".strip(),
                        " ".join(inner + [setv("tgcx_pick", 1)])))
        # Nothing on his agenda is open: he asks for quiet instead.
        for n, name in enumerate(tgcx_leaders.BANDS[:3], 1):
            sets = []
            for t in TIERS:
                days = r.freeze[name][t]
                sets += [setv(var[t][0], ASK_FREEZE if days else ASK_FREE), setv(var[t][1], days)]
            lines.append(when(f"NOT = {{ {chk('tgcx_pick', 1)} }} {chk(band, n)} NOT = {{ {chk(band, n+1)} }}", " ".join(sets)))
        return lines

    def decode(self, ask):
        """A law ask -> (group, target option index, ideal option index)."""
        g, rest = divmod(ask - ASK_LAW, 64)
        return self.chosen[g], rest // 8, rest % 8

    def debt_check(self, i, s):
        """A law owed to this character is paid once the law is at the target or nearer his ideal."""
        owe, lines = f"tgcx_owe_{i}_{s}", []
        for ask in sorted(self.targets.get((i, s), ())):
            g, target, ideal = self.decode(ask)
            opts = self.groups[g]["options"]
            paid = ors([f"{g} = {o}" for o in opts[min(target, ideal):max(target, ideal) + 1]])
            lines.append(when(f"{chk(owe, ask)} NOT = {{ {chk(owe, ask+1)} }} {paid}", " ".join([
                setv(owe, 0), f"remove_country_modifier = tgcx_due_{i}_{s}", self.rel_change(i, s, self.rules.kept)])))
        return lines

    def all_debt_checks(self):
        return [line for i in self.blocs for s in SLOTS for line in self.debt_check(i, s)]

    def build_deals(self):
        """One decision per character and tier: his followers among the bloc's opposing seats
        abstain or vote Aye, for what he asks at the current relation. No favours, no lots (D38)."""
        days_values = sorted({d for band in self.rules.ask.values() for _, d in band.values() if d})
        freeze_values = sorted({d for band in self.rules.freeze.values() for d in band.values() if d})
        for i in self.blocs:
            bloc = self.singular(i)
            for s in SLOTS:
                who = "leader" if s == 0 else "cabecilla"
                offer = [*self.band_lines(i, s), *self.offer_lines(i, s)]
                for n, tier in enumerate(TIERS, 1):
                    ask, days = f"tgcx_gui_ask_{i}_{s}_{tier}", f"tgcx_gui_days_{i}_{s}_{tier}"
                    deal, owe, mine = f"tgcx_deal_{i}_{s}", f"tgcx_owe_{i}_{s}", f"tgcx_gui_copp_{i}_{s}"
                    apply = []
                    for k in range(1, 21):
                        seats = 5 * k
                        moves = [chg("tgcx_no", -seats), chg(f"tgcx_left_{i}", -seats), chg(f"tgcx_buy_{i}_total", seats)]
                        if tier == "abstain":
                            moves += [chg("tgcx_margin", seats), chg("tgcx_quorum", -seats)]
                        else:
                            moves += [chg("tgcx_yes", seats), chg("tgcx_margin", 2 * seats), chg(f"tgcx_buy_{i}_yes", seats)]
                        apply.append(when(f"{chk(mine, seats)} NOT = {{ {chk(mine, seats+5)} }}", " ".join(moves)))
                    apply.append(setv(deal, n))
                    for value in sorted(self.targets[(i, s)]):
                        apply.append(when(f"{chk(ask, value)} NOT = {{ {chk(ask, value+1)} }}", setv(owe, value)))
                    for d in days_values:
                        apply.append(when(f"{chk(ask, ASK_LAW)} {chk(days, d)} NOT = {{ {chk(days, d+1)} }}",
                                          f"add_country_modifier = {{ name = tgcx_due_{i}_{s} duration = {d} }}"))
                    for d in freeze_values:
                        apply.append(when(f"{chk(ask, ASK_FREEZE)} NOT = {{ {chk(ask, ASK_LAW)} }} "
                                          f"{chk(days, d)} NOT = {{ {chk(days, d+1)} }}",
                                          f"add_country_modifier = {{ name = tgcx_freeze duration = {d} }}"))
                    potential = ["ai = no", flag("law_active"), self.house_at(i, .001)]
                    # He deals once per bill, has seats to move, accepts, and is owed no other law.
                    allow = [f"NOT = {{ {chk(deal, 1)} }}", chk(mine, 5), chk(ask, ASK_FREE),
                             f"OR = {{ NOT = {{ {chk(ask, ASK_LAW)} }} NOT = {{ {chk(owe, 1)} }} }}"]
                    refresh, fresh = self.fresh_guard(i)
                    effect = [*refresh, *self.rel_init(), *self.split_lines(i, ("opposed",)), *offer,
                              when(" ".join([fresh, *potential, *allow]), " ".join(apply))]
                    self.decision(
                        f"tgcx_deal_{tier}_{i}_{s}",
                        f"{bloc} {who}: {'abstain' if tier == 'abstain' else 'vote Aye'}",
                        f"Propose a deal to the {bloc} {who}. His followers among the bloc's opposing seats "
                        f"{'abstain instead of voting Nay' if tier == 'abstain' else 'vote Aye'}. In exchange he asks for a "
                        "law on his agenda, moved toward what he wants within a deadline, or for no new bills for a while. "
                        "The better the relation with him, the less he asks. A friend may ask nothing and an enemy refuses. "
                        "One deal per character and bill. If the chamber changed, count the votes first.",
                        potential, allow, effect)

    def build_refresh(self):
        """What every character asks now (the Bill window's view). The DLL sends it when a bill opens."""
        lines = [*self.rel_init(), *self.all_debt_checks()]
        for i in self.blocs:
            lines += self.split_lines(i)
            for s in SLOTS:
                lines += self.band_lines(i, s) + self.offer_lines(i, s)
        lines.append(setv("tgcx_gui_offers", 1))
        self.decision(
            "tgcx_refresh_offers", "Sound out the leaders",
            "Ask each party leader and cabecilla what he would want for his followers' votes on the bill. "
            "With the TGCX DLL this is done automatically.",
            ["ai = no", flag("law_active")], [], lines)

    def extra_bill_flags(self):
        return ["tgcx_catalog_bill", "tgcx_target_valid"] + [
            f"tgcx_cs_{i}_{s}_{code}" for i in self.blocs for s in SLOTS for code in tgcx_leaders.CODES] + [
            f"tgcx_billgroup_{g}" for g in self.chosen] + [
            f"tgcx_support_{mode}" for mode in MODES] + [
            f"tgcx_bucket_{i}_{k}" for i in self.blocs for k in range(21)] + [
            f"tgcx_from_{g}_{opt}" for g in self.chosen for opt in self.groups[g]["options"]]

    @staticmethod
    def house_at(ideology, fraction):
        return f"upper_house = {{ ideology = {ideology} value = {fraction:.6f} }}"

    def allocation_block(self):
        """Balanced rounding of twenty five-seat packets.

        Round to nearest five, then correct excess/deficit using only blocs
        rounded up/down respectively, in installed ideology order. Each valid
        bloc receives either floor or ceiling of its true packet count. This
        avoids a large remainder-ranking program in the 32-bit engine.
        """
        lines = [setv("tgcx_house_total", 0)]
        for i in self.blocs:
            lines += [setv(f"tgcx_seats_{i}", 0), setv(f"tgcx_remainder_{i}", 0),
                      f"clr_country_flag = tgcx_allocated_{i}"]
            lines += [f"clr_country_flag = tgcx_bucket_{i}_{k}" for k in range(21)]
            for k in range(20):
                limits = f"NOT = {{ {self.house_at(i, (k+1)/20)} }}"
                if k:
                    limits = f"{self.house_at(i, k/20)} {limits}"
                remainder = when(self.house_at(i, k/20 + .025), " ".join([
                    chg(f"tgcx_seats_{i}", 5), chg("tgcx_house_total", 5),
                    f"set_country_flag = tgcx_allocated_{i}",
                    f"clr_country_flag = tgcx_bucket_{i}_{k}",
                    f"set_country_flag = tgcx_bucket_{i}_{k+1}"]))
                lines.append(when(limits, " ".join([
                    setv(f"tgcx_seats_{i}", 5*k), chg("tgcx_house_total", 5*k),
                    f"set_country_flag = tgcx_bucket_{i}_{k}", remainder])))
            lines.append(when(self.house_at(i, 1), " ".join([
                setv(f"tgcx_seats_{i}", 100), chg("tgcx_house_total", 100),
                f"set_country_flag = tgcx_bucket_{i}_20"])))
        for i in self.blocs:
            lines.append(when(f"{chk('tgcx_house_total', 105)} {flag(f'allocated_{i}')}",
                              " ".join([chg(f"tgcx_seats_{i}", -5), chg("tgcx_house_total", -5)])))
        for i in self.blocs:
            lines.append(when(f"NOT = {{ {chk('tgcx_house_total', 100)} }} "
                              f"NOT = {{ {flag(f'allocated_{i}')} }} {self.house_at(i, .001)}",
                              " ".join([chg(f"tgcx_seats_{i}", 5), chg("tgcx_house_total", 5)])))
        return lines

    def fresh_guard(self, ideology):
        """Validate cached allocation and the selected bloc's current support.

        If quantized chamber inputs or support changed, spending waits for Count.
        This guards the effect itself, including delayed/queued commands (P21).
        """
        chamber = []
        for i in self.blocs:
            up, down = [], []
            for k in range(21):
                bucket = flag(f"bucket_{i}_{k}")
                if k:
                    up.append(f"AND = {{ {bucket} {self.house_at(i, k/20-.025)} "
                              f"NOT = {{ {self.house_at(i, k/20)} }} }}")
                upper = f"NOT = {{ {self.house_at(i, k/20+.025)} }}" if k < 20 else ""
                down.append(f"AND = {{ {bucket} {self.house_at(i, k/20)} {upper} }}")
            rounded_up = flag(f"allocated_{i}")
            chamber.append(f"OR = {{ AND = {{ {rounded_up} {ors(up)} }} "
                           f"AND = {{ NOT = {{ {rounded_up} }} {ors(down)} }} }}")
        raw = f"tgcx_support_{ideology}"
        current = f"tgcx_current_support_{ideology}"
        refresh = [setv(current, 0)]
        values = sorted(set(v for rule in self.support[ideology].values() for v in rule.values))
        for mode in MODES:
            refresh.append(when(flag(f"support_{mode}"), " ".join(self.support[ideology][mode].script(current))))
        same = ors(["AND = { " + " ".join([
            chk(raw, v), f"NOT = {{ {chk(raw, v+1)} }}",
            chk(current, v), f"NOT = {{ {chk(current, v+1)} }}"]) + " }" for v in values])
        return refresh, " ".join([*chamber, same, chk("tgcx_house_total", 100),
                                  f"NOT = {{ {chk('tgcx_house_total', 105)} }}"])

    def baseline_block(self, i):
        raw, baseline = f"tgcx_support_{i}", f"tgcx_base_yes_{i}"
        lines = [setv(raw, 0), setv(baseline, 0)]
        values = sorted(set(v for rule in self.support[i].values() for v in rule.values))
        for mode in MODES:
            lines.append(when(flag(f"support_{mode}"), " ".join(self.support[i][mode].script(raw))))
        for k in range(1, 21):
            choices = []
            for value in values:
                if not value:
                    continue
                packets = ((2*k-1)*1000 + 2*value-1) // (2*value)
                if packets <= 20:
                    choices.append(f"AND = {{ {chk(raw, value)} {chk(f'tgcx_seats_{i}', 5*packets)} }}")
            if choices:
                lines.append(when(ors(choices), chg(baseline, 5)))
        return lines

    def count_block(self):
        lines = [setv(v, 0) for v in ("tgcx_yes", "tgcx_no", "tgcx_margin", "tgcx_quorum")]
        # Read-only DLL view model, written only by the synchronized script.
        # Refreshing it here also migrates active saves made before the GUI.
        lines += [setv("tgcx_gui_schema", 1), setv("tgcx_gui_active", 0),
                  when(flag("law_active"), setv("tgcx_gui_active", 1)), setv("tgcx_gui_bill_id", 0),
                  setv("tgcx_gui_crown_audience", 0),
                  when(flag("crown_signs"), setv("tgcx_gui_crown_audience", 1))]
        for bid, (g, frm, to) in enumerate(self.bills, 1):
            source = flag(f"from_{g}_{frm}")
            if (g, frm, to) == ("press_rights", "censored_press", "free_press"):
                source = f"OR = {{ {source} NOT = {{ {flag('catalog_bill')} }} }}"
            lines.append(when(f"{flag(f'law_{g}_{to}')} {source}", setv("tgcx_gui_bill_id", bid)))
        for i in self.blocs:
            lines += [setv(f"tgcx_gui_stance_{i}", 0), setv(f"tgcx_gui_promised_{i}", 0),
                      when(flag(f"promised_{i}"), setv(f"tgcx_gui_promised_{i}", 1))]
            for stance, value in (("p2", 2), ("p1", 1), ("m1", -1), ("m2", -2)):
                lines.append(when(flag(f"stance_{i}_{stance}"), setv(f"tgcx_gui_stance_{i}", value)))
        # The Bill's Crown panel: the same rule the vote applies, plus the
        # ruling party and government it depends on (1-based; 0 = other).
        lines += [setv("tgcx_gui_ruling", 0), setv("tgcx_gui_government", 0),
                  setv("tgcx_gui_crown_veto", 0), setv("tgcx_gui_crown_signs", 0)]
        lines += [when(f"ruling_party_ideology = {i}", setv("tgcx_gui_ruling", n))
                  for n, i in enumerate(self.all_ideologies, 1)]
        lines += [when(f"government = {g}", setv("tgcx_gui_government", n))
                  for n, g in enumerate(self.limited + self.full, 1)]
        lines += [when(gov_in(self.limited), setv("tgcx_gui_crown_veto", 1)),
                  when(self.crown_signs(), setv("tgcx_gui_crown_signs", 1))]
        # Only the accepted LAW-0 transition exists without catalogue mode flags.
        lines.append(when(f"NOT = {{ {flag('catalog_bill')} }} {flag('law_press_rights_free_press')}",
                          "set_country_flag = tgcx_support_add_political_reform"))
        lines += self.allocation_block()
        yes = " ".join([chg("tgcx_yes", 5), chg("tgcx_margin", 5), chg("tgcx_quorum", 5)])
        for i in self.blocs:
            raw, baseline, opposed = (f"tgcx_support_{i}", f"tgcx_base_yes_{i}", f"tgcx_opposed_{i}")
            lines += self.baseline_block(i) + [setv(opposed, 0), setv(f"tgcx_left_{i}", 0)]
            for k in range(1, 21):
                seat = chk(f"tgcx_seats_{i}", 5*k)
                base = chk(baseline, 5*k)
                lines += [when(base, yes), when(f"{seat} NOT = {{ {base} }}", chg(opposed, 5))]
            for k in range(1, 21):
                seat = chk(opposed, 5*k)
                promised = flag(f"promised_{i}")
                bought_yes = chk(f"tgcx_buy_{i}_yes", 5*k)
                bought_any = chk(f"tgcx_buy_{i}_total", 5*k)
                lines += [
                    when(f"{seat} OR = {{ {promised} {bought_yes} }}", yes),
                    when(f"{seat} NOT = {{ {promised} }} NOT = {{ {bought_any} }}", " ".join([
                        chg("tgcx_no", 5), chg("tgcx_margin", -5), chg("tgcx_quorum", 5),
                        chg(f"tgcx_left_{i}", 5)]))]
        return lines

    def cleanup_block(self):
        lines = super().cleanup_block()
        flags, variables, modifiers = self.bill_state
        flags += [f"tgcx_allocated_{i}" for i in self.blocs]
        variables += ["tgcx_house_total"] + [
            f"tgcx_{kind}_{i}" for i in self.blocs
            for kind in ("seats", "remainder", "support", "current_support", "base_yes", "opposed")]
        variables += ["tgcx_gui_active", "tgcx_gui_bill_id", "tgcx_gui_crown_audience", "tgcx_gui_ruling",
                      "tgcx_gui_government", "tgcx_gui_crown_veto", "tgcx_gui_crown_signs", "tgcx_gui_offers"] + [
            f"tgcx_gui_{kind}_{i}" for i in self.blocs for kind in ("stance", "promised")]
        # The characters' part of the bill: deals and the Bill window's view of them.
        # Relations (tgcx_rel_*), debts (tgcx_owe_*, tgcx_due_*) and tgcx_freeze are the country's: kept.
        variables += ["tgcx_eff", "tgcx_pick"] + [f"tgcx_deal_{i}_{s}" for i in self.blocs for s in SLOTS] + [
            f"tgcx_gui_{kind}_{i}_{s}" for i in self.blocs for s in SLOTS for kind in ("band", "cseats", "copp", "cst")] + [
            f"tgcx_gui_{kind}_{i}_{s}_{t}" for i in self.blocs for s in SLOTS for t in TIERS for kind in ("ask", "days")]
        self.bill_state = (flags, variables, modifiers)
        return lines + [f"clr_country_flag = tgcx_allocated_{i}" for i in self.blocs] + [
            setv(v, 0) for v in variables if v in ("tgcx_house_total", "tgcx_eff", "tgcx_pick")
            or v.startswith(("tgcx_gui_", "tgcx_deal_")) or any(
                v.startswith(f"tgcx_{kind}_") for kind in ("seats", "remainder", "support", "current_support", "base_yes", "opposed"))]

    def build_bills(self, count, report, legislature):
        for g in self.chosen:
            opts = self.groups[g]["options"]
            for direction, pairs in (("up", list(zip(opts, opts[1:]))),
                                     ("down", list(zip(opts[1:], opts)))):
                available, branches = [], []
                descriptions = []
                for frm, to in pairs:
                    allow = ser(as_dict(self.groups[g]["body"][to]).get("allow", []), 0).replace("\n", " ")
                    available.append(f"AND = {{ {g} = {frm} {allow} }}")
                    stances = [f"set_country_flag = tgcx_stance_{i}_{self.stance(i, g, frm, to)}" for i in self.blocs]
                    branches.append(when(f"{g} = {frm}", " ".join([
                        f"set_country_flag = tgcx_law_{g}_{to}", f"set_country_flag = tgcx_from_{g}_{frm}", *stances,
                        *self.stance_lines(g, frm, to)])))
                    descriptions.append(f"{self.pretty(frm)} -> {self.pretty(to)}")
                self.decision(
                    f"tgcx_bill_{g}_{direction}",
                    f"Bill: {self.pretty(g)} ({'next' if direction == 'up' else 'previous'} option)",
                    f"Negotiate one step in {self.pretty(g)}, following TGC's option order. "
                    + ". ".join(descriptions)
                    + f". Debate: {self.n('debate_days')} days. TGC's conditional rules supply starting votes. "
                    "Party leaders and cabecillas can be offered a deal for their followers' votes. "
                    "The current law and TGC's target restrictions are checked again when voting.",
                    ["ai = no", ors([f"{g} = {frm}" for frm, _ in pairs]),
                     f"NOT = {{ {flag('law_active')} }}", "NOT = { has_country_modifier = tgcx_bill_cooldown }",
                     "NOT = { has_country_modifier = tgcx_freeze }", legislature],
                    [ors(available)],
                    [*self.cleanup_block(), *self.rel_init(), "set_country_flag = tgcx_law_active", setv("tgcx_gui_active", 1),
                     "set_country_flag = tgcx_catalog_bill", f"set_country_flag = tgcx_billgroup_{g}",
                     f"set_country_flag = tgcx_support_{'add' if direction == 'up' else 'remove'}_"
                     f"{'political' if self.groups[g]['category'] == 'political_reforms' else 'social'}_reform",
                     *branches, setv("tgcx_spent", 0),
                     f"add_country_modifier = {{ name = tgcx_debate duration = {self.n('debate_days')} }}"])

    def vote_validation(self):
        lines = ["clr_country_flag = tgcx_target_valid"]
        legislature = gov_in(self.limited + self.full)
        for g, frm, to in self.bills:
            allow = ser(as_dict(self.groups[g]["body"][to]).get("allow", []), 0).replace("\n", " ")
            source = flag(f"from_{g}_{frm}")
            # LAW-0 saves have no source flag. Only its one known transition can migrate.
            if (g, frm, to) == ("press_rights", "censored_press", "free_press"):
                source = f"OR = {{ {source} NOT = {{ {flag('catalog_bill')} }} }}"
            lines.append(when(f"{flag(f'law_{g}_{to}')} {source} {g} = {frm} {allow} {legislature}",
                              "set_country_flag = tgcx_target_valid"))
        return lines, f"AND = {{ {flag('target_valid')} {chk('tgcx_house_total', 100)} NOT = {{ {chk('tgcx_house_total', 105)} }} }}"

    def build_negotiation(self, count, report, cleanup):
        """Deals with characters replace LAW-0's favours, purchase lots and bloc promises (D38)."""
        for i in self.blocs:                # every law ask a character can make, before the debt checks
            for s in SLOTS:
                self.offer_lines(i, s)
        self.build_deals()
        self.build_refresh()

        # Until the Head of State card: the audience costs nothing (it cost favours in LAW-0).
        self.decision(
            "tgcx_audience", "Audience with the Crown",
            "Ask the Crown for an audience. If granted, it will sign this bill even if it dislikes it.",
            ["ai = no", flag("law_active"), f"NOT = {{ {flag('crown_signs')} }}", gov_in(self.limited)], [],
            ["set_country_flag = tgcx_crown_signs"])

        self.decision(
            "tgcx_count_votes", "Count the votes",
            "The whips count the upper house as it stands today. Use it after an election.",
            ["ai = no", flag("law_active")], [], [*count, *report])

        # Call the vote: recount, decide the outcome into flags first, then act (the acts change the tallies).
        validation, valid = self.vote_validation()
        ok = f"{chk('tgcx_margin', 5)} {chk('tgcx_quorum', 50)} {valid}".rstrip()
        crown = self.crown_signs()
        act = [when(f"{ok} {crown}", "set_country_flag = tgcx_outcome_pass"),
               when(f"{ok} NOT = {{ {crown} }}", "set_country_flag = tgcx_outcome_veto"),
               when(f"NOT = {{ {chk('tgcx_margin', 5)} }}", "set_country_flag = tgcx_outcome_changed"),
               when(f"NOT = {{ {chk('tgcx_quorum', 50)} }}", "set_country_flag = tgcx_outcome_changed"),
               when(f"NOT = {{ {valid} }}", "set_country_flag = tgcx_outcome_changed")]
        for g, to in dict.fromkeys((g, to) for g, _, to in self.bills):
            kind = "political_reform" if self.groups[g]["category"] == "political_reforms" else "social_reform"
            act.append(when(f"{flag('outcome_pass')} {flag(f'law_{g}_{to}')}", f"{kind} = {to}"))
        # A passed law moves the relation with each character who was for or against it,
        # and may pay a law owed (the new law is in force by now).
        for i in self.blocs:
            for s in SLOTS:
                liked = ors([flag(f"cs_{i}_{s}_p2"), flag(f"cs_{i}_{s}_p1")])
                disliked = ors([flag(f"cs_{i}_{s}_m1"), flag(f"cs_{i}_{s}_m2")])
                act += [when(f"{flag('outcome_pass')} {liked}", self.rel_change(i, s, self.rules.liked)),
                        when(f"{flag('outcome_pass')} {disliked}", self.rel_change(i, s, self.rules.disliked))]
        act += [when(flag("outcome_pass"), " ".join(self.all_debt_checks())),
                when(flag("outcome_pass"), f"country_event = {EV_PASSED}"),
                when(flag("outcome_veto"), f"country_event = {EV_VETOED} add_country_modifier = {{ name = tgcx_bill_cooldown duration = {self.n('cooldown_days')} }}"),
                when(flag("outcome_changed"), f"country_event = {EV_CHANGED}"),
                when(ors([flag("outcome_pass"), flag("outcome_veto")]), " ".join(cleanup)),
                "clr_country_flag = tgcx_outcome_pass", "clr_country_flag = tgcx_outcome_veto",
                "clr_country_flag = tgcx_outcome_changed"]
        self.decision(
            "tgcx_call_vote", "Call the vote",
            "The upper house votes. It passes if more seats vote Aye than Nay and at least 50 of 100 vote. "
            "Then the Crown signs or vetoes. Deals made for this bill stand whatever the result.",
            ["ai = no", flag("law_active")],
            ["NOT = { has_country_modifier = tgcx_debate }", chk("tgcx_margin", 5), chk("tgcx_quorum", 50)],
            [*count, *validation, *act], picture="hellenic_parliament")

        self.decision(
            "tgcx_withdraw", "Withdraw the bill",
            f"Withdraw the bill. Deals made for it stand, and no bill can be presented for "
            f"{self.n('cooldown_days')} days.",
            ["ai = no", flag("law_active")], [],
            [*cleanup, f"add_country_modifier = {{ name = tgcx_bill_cooldown duration = {self.n('cooldown_days')} }}"])

        self.build_tick()

        # Events: results, reports, broken deals.
        self.event(EV_PASSED, "tgcx_law_passed", "The Bill Passes",
                   "The upper house has passed the bill and the Crown has signed it into law.", "Splendid.")
        self.event(EV_VETOED, "tgcx_law_vetoed", "The Crown Vetoes the Bill",
                   "The upper house passed the bill, but the Crown refused to sign it. The deals made for it stand.",
                   "So be it.")
        self.event(EV_CHANGED, "tgcx_law_changed", "The Count Has Changed",
                   self.changed_text(), "We need more votes.")
        for m in range(5, 101, 5):
            self.event(EV_PASS_BY + m // 5 - 1, f"tgcx_whip_pass_{m}", "The Whips Report",
                       f"If the vote were held today, the bill would pass by {m} seats.", "Good.")
        for m in range(0, 101, 5):
            self.event(EV_FAIL_BY + m // 5, f"tgcx_whip_fail_{m}", "The Whips Report",
                       f"If the vote were held today, the bill would fail: Nay leads by {m} seats." if m else
                       "If the vote were held today, the bill would fail: Aye and Nay are tied.", "We need more votes.")
        for q in range(0, 50, 5):
            self.event(EV_NO_QUORUM + q // 5, f"tgcx_whip_quorum_{q}", "The Whips Report",
                       f"If the vote were held today, only {q} seats would vote, short of the quorum of 50.",
                       "We need more votes.")
        militancy = self.n("broken_debt_militancy")
        for n, i in enumerate(self.all_ideologies):
            if i not in self.blocs:
                continue
            for s in SLOTS:
                who = f"the {self.singular(i)} {'leader' if s == 0 else 'cabecilla'}"
                owe = f"tgcx_owe_{i}_{s}"
                # The deadline passed. A law that is in place after all still pays the debt (checked first).
                self.event(EV_DEAL_BROKEN + 2 * n + s, f"tgcx_deal_broken_{i}_{s}", "A Deal Broken",
                           f"The law we promised {who} was not passed in time. He will not forget it, "
                           "and his supporters are angry.",
                           "We will pay for this.",
                           [*self.debt_check(i, s),
                            when(chk(owe, 1), " ".join([
                                setv(owe, 0), self.rel_change(i, s, self.rules.broken),
                                f"any_pop = {{ scaled_militancy = {{ ideology = {i} factor = {militancy} }} }}"]))],
                           trigger=[chk(owe, 1), f"NOT = {{ has_country_modifier = tgcx_due_{i}_{s} }}"],
                           polled=True)

        self.modifiers = [("tgcx_debate", 6, "Bill in debate", "The upper house is debating a bill. The vote can be called when this ends."),
                          ("tgcx_bill_cooldown", 6, "Bill recently failed", "A bill failed or was withdrawn: no new bill until this ends."),
                          ("tgcx_freeze", 6, "No new bills: a deal", "We agreed to present no new bill until this ends."),
                          ("tgcx_favours_tick", 6, "Politics: this month's round done", "The monthly round of politics runs again when this ends.")]
        for i in self.blocs:
            for s in SLOTS:
                who = f"the {self.singular(i)} {'leader' if s == 0 else 'cabecilla'}"
                self.modifiers.append((f"tgcx_due_{i}_{s}", 6, f"Law owed to {who}",
                                       f"Pass the law promised to {who} before this ends, or the deal is broken."))
        for name, _, title, desc in self.modifiers:
            self.text(name, title)
            self.text(f"{name}_desc", desc)

        # Vic2 displayed every conditional option of the old shared report.
        # New requests count in the decision, then select one ordinary result
        # event through the established LAW-0 firing-effect branches (P21/P34).
        # Keep its ID as a one-option recovery for an already queued save event;
        # no new decision fires this obsolete dispatcher.
        self.event(EV_CATALOG_COUNT, "tgcx_catalog_count", "The Whips Report",
                   "This report was queued by an earlier TGCX candidate. Recount the bill to get its current result.",
                   "Recount the bill.", [*count, *report])

    def files(self):
        files = super().files()
        # Preserve quoted tokens and line breaks while reducing repeated script
        # punctuation whitespace. Both forms have exactly the same script AST.
        for path, content in files.items():
            if path.endswith(".txt"):
                files[path] = re.sub(r'"[^"\n]*"|[ \t]*[{}=][ \t]*',
                                     lambda m: m[0] if m[0].startswith('"') else m[0].strip(), content)
        return files

    def decision(self, name, title, desc, potential, allow, effect, picture="cogs_blue"):
        if name == "tgcx_call_vote":
            # A previous defeat must not hide a newly winning fresh count.
            allow = ["NOT = { has_country_modifier = tgcx_debate }"]
        elif name == "tgcx_audience":
            effect = [*effect, setv("tgcx_gui_crown_audience", 1), setv("tgcx_gui_crown_signs", 1)]
        if name in self.DLL_SENT:
            # The Bill sends these through the native decision click, which
            # does not test potential/allow (LAW-2, FUN_006DCE10). The effect
            # checks them itself, so a stale or repeated command does nothing.
            effect = [when(" ".join([*potential, *allow]), " ".join(effect))]
        super().decision(name, title, desc, potential, allow, effect, picture)

    def build_tick(self):
        """The monthly round (D11's slot; no favours since D38): relations start, laws owed are
        checked, and the Reforms tab learns which bills can be offered. The decision and its
        modifier keep their LAW-0 names (tgcx_collect_favours, tgcx_favours_tick): the DLL sends
        the first when the second is gone, and counts tgcx_favours_ticks."""
        self.decision(
            "tgcx_collect_favours", "The month in politics",
            "Once a month: laws owed to party leaders and cabecillas are checked, and the Reforms tab "
            "learns which bills can be presented. With the TGCX DLL this runs automatically.",
            ["ai = no", "NOT = { has_country_modifier = tgcx_favours_tick }"], [],
            [*self.rel_init(), *self.all_debt_checks(), chg("tgcx_favours_ticks", 1),
             # The Reforms tab offers bills only where a chamber can vote one.
             setv("tgcx_gui_legislature", 0), when(gov_in(self.limited + self.full), setv("tgcx_gui_legislature", 1)),
             *self.offer_block(),
             f"add_country_modifier = {{ name = tgcx_favours_tick duration = {self.n('tick_days')} }}"],
            picture="cogs_yellow")

    def offer_block(self):
        """D14: for each group, 1 + the current law whose next step passes the
        target option's own TGC allow (0 = none). The DLL lights a Reforms row
        only for that law, so a law changed since the collection offers nothing."""
        lines = []
        for g in self.chosen:
            opts = self.groups[g]["options"]
            var = f"tgcx_gui_offer_{g}"
            lines.append(setv(var, 0))
            for n, (frm, to) in enumerate(zip(opts, opts[1:]), 1):
                allow = ser(as_dict(self.groups[g]["body"][to]).get("allow", []), 0).replace("\n", " ")
                lines.append(when(f"{g} = {frm} {allow}", setv(var, n)))
        return lines

    def changed_text(self):
        return ("The vote cannot enact this bill: support, the starting law, the government, or TGC's target "
                "restrictions have changed. The bill stays on the table. Recount or withdraw it.")

    def build_debug(self):
        pass


def generate_catalog(tgc=DEFAULT_TGC, path=CATALOG, selected=None, release=False):
    laws, affinity, groups, ideologies, chosen, reviews = catalog_data(tgc, path, selected, release)
    g = CatalogGen(laws, affinity, groups, ideologies, chosen, load_support(tgc, ideologies))
    g.build()
    files = g.files()
    validate(files)
    return g, files, reviews


def validate(files):
    for name, text in files.items():
        text.encode("cp1252")
        if name.endswith(".txt") and not balanced(text):
            raise ValueError(f"unbalanced script: {name}")
        if Path(name).parent.name == "decisions":
            unique(dict(parse(text))["political_decisions"], "generated decisions")
        if Path(name).parent.name == "events":
            events = [body for _, body in parse(text)]
            ids = [int(dict(body)["id"]) for body in events]
            if len(ids) != len(set(ids)) or any(not 420000000 <= n <= 420999999 for n in ids):
                raise ValueError("duplicate or unreserved event ID")
            for body in events:
                for key, option in body:
                    if key == "option" and any(k in ("trigger", "allow", "limit") for k, _ in option):
                        raise ValueError("conditional event options are not supported by this candidate (P34)")


def review_text(tgc=DEFAULT_TGC, path=CATALOG):
    laws, affinity, groups, ideologies, chosen, reviews = catalog_data(tgc, path)
    aff = {i: dict(body) for i, body in affinity}
    pending = [g for g in chosen if reviews[g] == "pending"]
    lines = ["# LAW-1 affinity proposal", "", f"2026-10-12. **{len(chosen)-len(pending)} groups approved, {len(pending)} awaiting user review.**",
             "Generated from our proposed data plus installed TGC v2.5.2 option names/order.",
             "Intensity 1 = weak; 2 = strong. `status_quo` means oppose change weakly where intensity is 1.",
             "These are design proposals, not claims about historical parties or TGC's own voting AI.",
             "The user approved all base affinity rows on 2026-10-12; later corrections remain possible.",
             "TGC conditional rules supply starting votes; affinity controls bargaining and promises.",
             "There are 14 political + 9 social groups, 46 direction decisions and 144 adjacent transitions.",
             "Pending groups are preview only; release generation refuses unreviewed groups.", ""]
    for g in chosen:
        lines += [f"## {g} ({reviews[g]})", "", "TGC option order: " + " -> ".join(groups[g]["options"]), "",
                  "| Bloc | Proposed ideal | Intensity |", "|---|---|---|"]
        for i in ideologies:
            spec = dict(aff[i][g])
            lines.append(f"| {BLOC[i]} | {spec['ideal']} | {spec['intensity']} |")
        lines.append("")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--preview", type=Path)
    mode.add_argument("--release", type=Path)
    ap.add_argument("--tgc", default=DEFAULT_TGC)
    ap.add_argument("--data", type=Path, default=CATALOG)
    ap.add_argument("--groups", nargs="+")
    a = ap.parse_args()
    output = (a.preview or a.release).resolve()
    live = (Path(ROOT) / "submod").resolve()
    if output == live or output.is_relative_to(live) or live.is_relative_to(output):
        ap.error("use a separate staging directory; this tool does not overwrite the live submod")
    tgc = Path(a.tgc).resolve()
    protected = [tgc, *[p for p in tgc.parents if (p / "v2game.exe").is_file()]]
    if any(output == p or output.is_relative_to(p) or p.is_relative_to(output) for p in protected):
        ap.error("staging must be outside TGC and the installed game")
    try:
        g, files, reviews = generate_catalog(a.tgc, a.data, a.groups, release=bool(a.release))
    except ValueError as exc:
        ap.error(str(exc))
    for source, content in files.items():
        dest = output / Path(source).relative_to(Path(ROOT) / "submod")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(content.encode("cp1252"))
    (output / "tgcx_affinity_review.md").write_text(review_text(a.tgc, a.data), encoding="utf-8")
    print(f"LAW-1 {'preview' if a.preview else 'release staging'}: {len(g.chosen)*2} bill entries, "
          f"{len(g.bills)} transitions, {len(g.blocs)} blocs; {output}")
    if a.preview:
        print("PENDING USER AFFINITY REVIEW; preview is not installed.")


if __name__ == "__main__":
    main()
