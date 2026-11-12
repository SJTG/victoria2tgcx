#!/usr/bin/env python3
"""Exercise LAW-1 generated script without running the game or approving data."""

from pathlib import Path
import sys
import tempfile
import unittest

import tgcx_leaders

from gen_laws import BROKEN_EVENTS, DEFAULT_TGC, ROOT, generate
from gen_law_catalog import (ASK_FREE, ASK_FREEZE, ASK_LAW, CATALOG, EV_CATALOG_COUNT, EV_DEAL_BROKEN, catalog_data,
                             generate_catalog, validate)
from tgcx_law_support import SupportRule, native_weighted_support
from test_gen_laws import Country
from tgc_scan import parse, read


class LawCountry(Country):
    tgc_allow_triggers = set()

    def cond(self, key, value):
        if key == "militancy":
            return self.average_militancy >= float(value)
        if key in ("social_movement_strength", "political_movement_strength"):
            return getattr(self, key, 0) >= float(value)
        if key == "upper_house":
            d = dict(value)
            return int(self.house.get(d["ideology"], 0)*32768) >= int(float(d["value"])*32768)
        if key == "has_global_flag":
            return value in getattr(self, "global_flags", set())
        if key == "year":
            return getattr(self, "year", 1836) >= int(value)
        if key == "tag":
            return getattr(self, "tag", "XXX") == value
        try:
            return super().cond(key, value)
        except SystemExit:
            # Conditions only TGC's own option allow blocks use (D14 offer flags):
            # false unless the test states them, so our own typos still fail.
            if key not in self.tgc_allow_triggers:
                raise
            return getattr(self, "tgc_conditions", {}).get(key, False)

    def run(self, items):
        for key, value in items:
            if key == "any_pop":
                self.punishments = getattr(self, "punishments", []) + [value]
            elif key == "country_event":
                super().run([(key, value)])
                event = self.definitions[int(value)]
                if "immediate" in event:
                    self.run(event["immediate"])
            else:
                super().run([(key, value)])


def tgcx_characters(gen, tag, bloc):
    """The two characters a generator gives a bloc in a country."""
    return next((chars for cond, chars in gen.bloc_variants(bloc) if cond == f"tag = {tag}"),
                gen.bloc_variants(bloc)[0][1])


class CatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.gen, cls.files, cls.reviews = generate_catalog()
        decisions = next(text for path, text in cls.files.items() if Path(path).parent.name == "decisions")
        cls.decisions = {k: dict(v) for k, v in dict(parse(decisions))["political_decisions"]}
        events = next(text for path, text in cls.files.items() if Path(path).parent.name == "events")
        cls.events = {int(dict(v)["id"]): dict(v) for _, v in parse(events)}
        cls.event_trees = {int(dict(v)["id"]): v for _, v in parse(events)}
        names = set()

        def walk(items):
            for k, v in items:
                if k not in ("AND", "OR", "NOT"):
                    names.add(k)
                if isinstance(v, list):
                    walk(v)
        for g in cls.gen.chosen:
            for opt in cls.gen.groups[g]["options"]:
                walk(dict(cls.gen.groups[g]["body"][opt]).get("allow", []))
        LawCountry.tgc_allow_triggers = names - set(cls.gen.groups)

    def country(self, **kw):
        state = dict(house={"liberal": 1.0}, government="democracy", ruling="liberal",
                     prestige=250, war_exhaustion=0, average_militancy=0,
                     average_consciousness=0,
                     laws={g: body["options"][0] for g, body in self.gen.groups.items()})
        state.update(kw)
        c = LawCountry(**state)
        c.definitions = self.events
        c.event_trees = self.event_trees
        return c

    def flat(self, c):
        """Every relation at the base value (tests of the ask tables do not want the computed start)."""
        c.flags.add("tgcx_rel_init")
        for i in self.gen.blocs:
            for slot in (0, 1):
                c.vars[f"tgcx_rel_{i}_{slot}"] = self.gen.rules.start
        return c

    UK = {"conservative": .85, "liberal": .10, "reactionary": .05}

    def deal(self, c, tier, bloc, slot):
        """As the Decisions tab would: sound out the leaders, then click the deal."""
        self.click(c, "tgcx_refresh_offers")
        self.click(c, f"tgcx_deal_{tier}_{bloc}_{slot}")

    def send(self, c, name):
        """As the DLL does: the native click skips potential/allow, the effect checks itself."""
        c.run(self.decisions[name]["effect"])

    def tally(self, c):
        return c.vars["tgcx_yes"], c.vars["tgcx_no"], c.vars["tgcx_quorum"]

    def law_ask(self, group, target, ideal):
        opts = self.gen.groups[group]["options"]
        return ASK_LAW + 64*self.gen.chosen.index(group) + 8*opts.index(target) + opts.index(ideal)

    def click(self, c, name):
        d = self.decisions[name]
        self.assertTrue(c.test(d["potential"]), f"{name}: potential")
        self.assertTrue(c.test(d["allow"]), f"{name}: allow")
        c.run(d["effect"])

    def present(self, c, group, source, direction="up"):
        c.laws[group] = source
        self.click(c, f"tgcx_bill_{group}_{direction}")
        # The bill decision no longer carries its own copy of the count (33 MB -> ~13 MB of script):
        # the DLL sends the count when it sees an active bill with no id, the player can press it too.
        self.assertEqual(c.vars.get("tgcx_gui_bill_id", 0), 0)
        self.click(c, "tgcx_count_votes")

    def vote(self, c):
        c.mods.discard("tgcx_debate")
        self.click(c, "tgcx_call_vote")

    def test_inventory_ids_and_no_debug_cheats(self):
        self.assertEqual(len(self.gen.chosen), 23)
        self.assertEqual(sum(self.gen.groups[g]["category"] == "political_reforms" for g in self.gen.chosen), 14)
        self.assertEqual(len(self.gen.bills), 144)
        self.assertEqual(sum(n.startswith("tgcx_bill_") for n in self.decisions), 46)
        self.assertEqual(len(self.gen.blocs), 9)
        self.assertFalse(any(n.startswith("tgcx_debug_") for n in self.decisions))
        self.assertEqual(BROKEN_EVENTS["reactionary"], 420000105)
        validate(self.files)
        # All nine debts can occur across this complete catalogue. No index-based collisions.
        self.assertTrue(set(BROKEN_EVENTS.values()).issuperset(
            n for n, event in self.events.items() if event["title"].startswith("tgcx_promise_broken_")))

    def test_law0_regeneration_is_unchanged(self):
        _, files = generate(DEFAULT_TGC)
        for path, text in files.items():
            self.assertEqual(Path(path).read_bytes(), text.encode("cp1252"), path)

    def test_all_144_routes_select_exactly_one_target_and_source(self):
        # Walk admission effects for every route. TGC's individual allow trees are
        # verified separately; synthetic route fixtures do not claim all are reachable in 1836.
        for group, frm, to in self.gen.bills:
            with self.subTest(group=group, frm=frm, to=to):
                c = self.country()
                c.laws[group] = frm
                opts = self.gen.groups[group]["options"]
                direction = "up" if opts.index(to) > opts.index(frm) else "down"
                d = self.decisions[f"tgcx_bill_{group}_{direction}"]
                self.assertTrue(c.test(d["potential"]))
                c.run(d["effect"])
                c.run(self.decisions["tgcx_count_votes"]["effect"])     # the DLL sends it (or the player)
                targets = {f for f in c.flags if f.startswith("tgcx_law_") and f != "tgcx_law_active"}
                sources = {f for f in c.flags if f.startswith("tgcx_from_")}
                self.assertEqual(targets, {f"tgcx_law_{group}_{to}"})
                self.assertEqual(sources, {f"tgcx_from_{group}_{frm}"})
                self.assertEqual(c.vars["tgcx_gui_bill_id"], self.gen.bills.index((group, frm, to))+1)
                self.assertEqual(c.vars["tgcx_gui_active"], 1)
                for ideology in self.gen.blocs:
                    self.assertEqual(sum(f.startswith(f"tgcx_stance_{ideology}_") for f in c.flags), 1)

    def test_option_allows_are_preserved_in_each_direction(self):
        for group in self.gen.chosen:
            opts = self.gen.groups[group]["options"]
            for direction, pairs in (("up", zip(opts, opts[1:])), ("down", zip(opts[1:], opts))):
                choices = self.decisions[f"tgcx_bill_{group}_{direction}"]["allow"][0]
                branches = choices[1] if choices[0] == "OR" else [choices]
                for (frm, to), (_, branch) in zip(pairs, branches):
                    self.assertEqual(branch[0], (group, frm))
                    expected = dict(self.gen.groups[group]["body"][to]).get("allow", [])
                    self.assertEqual(branch[1:], expected)

    def test_boundaries_active_bill_and_cooldown(self):
        for group in self.gen.chosen:
            c = self.country()
            c.laws[group] = self.gen.groups[group]["options"][0]
            self.assertFalse(c.test(self.decisions[f"tgcx_bill_{group}_down"]["potential"]))
            c.laws[group] = self.gen.groups[group]["options"][-1]
            self.assertFalse(c.test(self.decisions[f"tgcx_bill_{group}_up"]["potential"]))
        c = self.country()
        self.present(c, "press_rights", "censored_press")
        self.assertFalse(c.test(self.decisions["tgcx_bill_public_meetings_up"]["potential"]))
        self.click(c, "tgcx_withdraw")
        self.assertFalse(c.test(self.decisions["tgcx_bill_press_rights_up"]["potential"]))

    def test_political_social_and_reverse_pass_use_correct_effect(self):
        cases = [("press_rights", "censored_press", "free_press", "up", "liberal"),
                 ("press_rights", "censored_press", "state_press", "down", "reactionary"),
                 ("health_care", "no_health_care", "trinket_health_care", "up", "socialist")]
        for group, frm, to, direction, supporter in cases:
            with self.subTest(group=group, target=to):
                c = self.country(house={supporter: 1.0})
                c.flags.add("medicine_invented")
                self.present(c, group, frm, direction)
                self.vote(c)
                self.assertEqual(c.reform, to)
                self.assertEqual(c.events[-1], 420000100)
                self.assertFalse(any(f.startswith(("tgcx_stance_", "tgcx_from_", "tgcx_law_")) for f in c.flags))

    def test_target_allow_current_law_and_government_rechecked_at_vote(self):
        for change in ("blocker", "law", "government", "technology"):
            c = self.country(house={"socialist": 1.0})
            c.flags.add("medicine_invented")
            self.present(c, "health_care", "no_health_care")
            if change == "blocker": c.flags.add("soc_reform_blocker")
            if change == "law": c.laws["health_care"] = "low_health_care"
            if change == "government": c.government = "absolute_monarchy"
            if change == "technology": c.flags.discard("medicine_invented")
            self.vote(c)
            self.assertFalse(hasattr(c, "reform"), change)
            self.assertEqual(c.events[-1], 420000102, change)
            self.assertIn("tgcx_law_active", c.flags)

    def test_legacy_law0_active_bill_can_finish(self):
        c = self.country()
        c.laws["press_rights"] = "censored_press"
        c.flags.update({"tgcx_law_active", "tgcx_law_press_rights_free_press", "tgcx_stance_liberal_p2",
                        "tgcx_stance_conservative_m1", "tgcx_stance_reactionary_m2"})
        c.vars.update(tgcx_margin=100, tgcx_quorum=100)
        self.vote(c)
        self.assertEqual(c.reform, "free_press")

    def test_pending_review_and_malformed_data_are_rejected(self):
        self.assertTrue(all(status == "approved" for status in self.reviews.values()))
        catalog_data(release=True)
        catalog_data(selected=["press_rights"], release=True)
        original = CATALOG.read_text()
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "tgcx_pending.txt"
            path.write_text(original.replace("review = approved", "review = pending", 1))
            with self.assertRaisesRegex(ValueError, "user-approved"):
                catalog_data(path=path, release=True)
        for text in (original.replace("intensity = 1", "intensity = 3", 1),
                     original.replace("ideal = status_quo", "ideal = nonexistent", 1),
                     original + original):
            with tempfile.TemporaryDirectory() as folder:
                path = Path(folder) / "tgcx_invalid.txt"
                path.write_text(text)
                with self.assertRaises(ValueError):
                    catalog_data(path=path)

    def test_native_thresholds_and_ruling_party_rules(self):
        c = self.country()
        for militancy, expected in ((0, 0), (3, 100), (4, 100), (5, 200), (9, 600)):
            c.average_militancy = militancy
            self.assertEqual(self.gen.support["conservative"]["add_political_reform"].evaluate(c.test), expected)
        c.average_militancy = 0
        for strength, expected in ((.299, 0), (.3, 100), (.4, 100), (.5, 200), (.9, 600)):
            c.political_movement_strength = strength
            self.assertEqual(self.gen.support["conservative"]["add_political_reform"].evaluate(c.test), expected)
        c.political_movement_strength = 0
        c.social_movement_strength = .7
        self.assertEqual(self.gen.support["conservative"]["add_social_reform"].evaluate(c.test), 600)
        self.assertEqual(self.gen.support["liberal"]["add_social_reform"].evaluate(c.test), 400)
        self.assertEqual(self.gen.support["anarcho_liberal"]["add_social_reform"].evaluate(c.test), 1000)
        for i, mode in (("fascist", "add_political_reform"), ("fascist", "remove_social_reform"),
                        ("communist", "add_social_reform"), ("anarcho_liberal", "remove_political_reform")):
            c.ruling = "liberal"
            self.assertEqual(self.gen.support[i][mode].evaluate(c.test), 0)
            c.ruling = i
            self.assertEqual(self.gen.support[i][mode].evaluate(c.test), 1000)

    def test_group_prefix_and_fixed_point_reference(self):
        rule = SupportRule(parse("base = 0 group = { modifier = { factor = .1 militancy = 5 } "
                                 "modifier = { factor = .2 militancy = 1 } }"))
        c = self.country(average_militancy=2)
        self.assertEqual(rule.evaluate(c.test), 0)
        c.average_militancy = 5
        self.assertEqual(rule.evaluate(c.test), 300)
        self.assertEqual(native_weighted_support({"c": 27197, "l": 3932}, {"c": 600, "l": 1000}), 20249)

    def test_fresh_vote_can_pass_after_cached_defeat(self):
        c = self.country(house={"conservative": 1.0}, average_militancy=0)
        self.present(c, "press_rights", "censored_press")
        self.assertEqual(c.vars["tgcx_margin"], -100)
        c.average_militancy = 9
        self.vote(c)
        self.assertEqual(c.reform, "free_press")

    def test_ruling_party_and_movements_refresh_actual_counts(self):
        c = self.country(house={"fascist": 1.0}, ruling="fascist")
        self.present(c, "press_rights", "censored_press")
        self.assertEqual(c.vars["tgcx_yes"], 100)
        c.ruling = "liberal"
        self.click(c, "tgcx_count_votes")
        self.assertEqual((c.vars["tgcx_yes"], c.vars["tgcx_no"]), (0, 100))
        c = self.country(house={"liberal": 1.0})
        c.flags.add("medicine_invented")
        self.present(c, "health_care", "no_health_care")
        self.assertEqual(c.vars["tgcx_yes"], 0)
        c.social_movement_strength = .9
        self.click(c, "tgcx_count_votes")
        self.assertEqual((c.vars["tgcx_yes"], c.vars["tgcx_no"]), (60, 40))

    def test_empty_house_refuses_enactment_and_count_cleanup(self):
        c = self.country(house={})
        self.present(c, "press_rights", "censored_press")
        self.assertEqual(c.vars["tgcx_house_total"], 0)
        self.vote(c)
        self.assertEqual(c.events[-1], 420000102)
        self.assertFalse(hasattr(c, "reform"))
        self.click(c, "tgcx_withdraw")
        self.assertFalse(any(f.startswith(("tgcx_bucket_", "tgcx_allocated_", "tgcx_support_")) for f in c.flags))
        for v in ("seats", "support", "current_support", "base_yes", "opposed"):
            self.assertTrue(all(c.vars.get(f"tgcx_{v}_{i}", 0) == 0 for i in self.gen.blocs))

    def test_generated_program_size_and_idempotence(self):
        self.assertLess(sum(len(s.encode("cp1252")) for s in self.files.values()), 40*1024*1024)
        _, files, _ = generate_catalog(release=True)
        self.assertEqual(self.files, files)

    # --- characters: deals instead of favours (D37-D43). An untagged country has automatic
    # characters: relation 5, the leader leads 70 % of his bloc.

    def test_a_deal_moves_the_characters_followers_once(self):
        c = self.country(house=self.UK)
        self.present(c, "press_rights", "censored_press")
        self.assertEqual(self.tally(c), (10, 90, 100))
        self.assertFalse(c.test(self.decisions["tgcx_deal_aye_communist_0"]["potential"]))  # no seats
        self.click(c, "tgcx_refresh_offers")
        self.assertEqual(c.vars["tgcx_gui_offers"], 1)
        self.assertEqual((c.vars["tgcx_gui_cseats_conservative_0"], c.vars["tgcx_gui_cseats_conservative_1"]), (60, 25))
        self.assertEqual((c.vars["tgcx_gui_copp_conservative_0"], c.vars["tgcx_gui_copp_conservative_1"]), (60, 25))
        # Relation 5, against the bill (-2): effective 3, hostile. Conservatives push no law, so he
        # asks for a pause on new bills: the hostile row of the freeze table.
        r = self.gen.rules
        self.assertEqual(c.vars["tgcx_gui_cst_conservative_0"], -1)
        self.assertEqual(c.vars["tgcx_gui_band_conservative_0"], 1)
        self.assertEqual((c.vars["tgcx_gui_ask_conservative_0_aye"], c.vars["tgcx_gui_days_conservative_0_aye"]),
                         (ASK_FREEZE, r.freeze["hostile"]["aye"]))
        self.click(c, "tgcx_deal_aye_conservative_0")
        self.assertEqual(self.tally(c), (70, 30, 100))
        self.assertIn("tgcx_freeze", c.mods)
        self.assertEqual(c.vars["tgcx_deal_conservative_0"], 2)
        self.assertEqual(c.vars.get("tgcx_owe_conservative_0", 0), 0)      # a pause is not a debt
        self.assertFalse(c.test(self.decisions["tgcx_deal_aye_conservative_0"]["allow"]))  # once per bill
        self.send(c, "tgcx_deal_abstain_conservative_0")                   # a repeated command
        self.assertEqual(self.tally(c), (70, 30, 100))
        self.deal(c, "abstain", "conservative", 1)
        self.assertEqual(self.tally(c), (70, 5, 75))
        self.click(c, "tgcx_count_votes")
        self.assertEqual(self.tally(c), (70, 5, 75))
        # The pause blocks the next bill, not this one.
        self.vote(c)
        self.assertEqual(c.reform, "free_press")
        self.assertFalse(c.test(self.decisions["tgcx_bill_press_rights_down"]["potential"]))
        c.mods.discard("tgcx_freeze")
        self.assertTrue(c.test(self.decisions["tgcx_bill_press_rights_down"]["potential"]))

    def test_a_stale_chamber_or_pressure_refuses_the_deal_until_recount(self):
        c = self.country(house=self.UK)
        self.present(c, "press_rights", "censored_press")
        c.average_militancy = 9
        self.send(c, "tgcx_deal_aye_conservative_0")           # stale pressure: nothing moves
        self.assertEqual(self.tally(c), (10, 90, 100))
        self.assertEqual(c.vars.get("tgcx_deal_conservative_0", 0), 0)
        self.click(c, "tgcx_count_votes")
        self.assertEqual(self.tally(c)[:2], (60, 40))          # 35 Conservatives still opposed: 25 + 10
        self.send(c, "tgcx_deal_aye_conservative_0")
        self.assertEqual(self.tally(c)[:2], (85, 15))
        self.send(c, "tgcx_deal_abstain_conservative_1")
        self.assertEqual(self.tally(c), (85, 5, 90))
        self.click(c, "tgcx_count_votes")
        self.assertEqual(self.tally(c), (85, 5, 90))
        c.average_militancy = 0
        self.click(c, "tgcx_count_votes")      # 85 Conservatives opposed again: 25 Aye, 10 abstain, 50 Nay
        self.assertEqual(self.tally(c), (35, 55, 90))
        for small, big in ((.06, .52), (.04, .68)):
            c = self.country(house=dict(zip(self.gen.blocs, [big, *([small]*8)])))
            c.run(parse(" ".join(self.gen.allocation_block())))
            self.assertEqual(c.vars["tgcx_house_total"], 100)
            self.assertEqual(sum(c.vars[f"tgcx_seats_{i}"] for i in self.gen.blocs), 100)
        c = self.country(house={"conservative": .849, "liberal": .151})
        self.present(c, "press_rights", "censored_press")
        c.house = {"conservative": .851, "liberal": .149}      # same nearest buckets; floor sides changed
        self.send(c, "tgcx_deal_aye_conservative_0")
        self.assertEqual(c.vars.get("tgcx_deal_conservative_0", 0), 0)
        self.click(c, "tgcx_count_votes")
        self.send(c, "tgcx_deal_aye_conservative_0")
        self.assertEqual(c.vars["tgcx_deal_conservative_0"], 2)

    def test_allocation_conservation_and_clipped_deals(self):
        import random
        rng = random.Random(1012)
        allocation = parse(" ".join(self.gen.allocation_block()))
        for _ in range(200):
            cuts = sorted([0, 32768, *[rng.randrange(32769) for _ in range(8)]])
            c = self.country(house={i: (b-a)/32768 for i, a, b in zip(self.gen.blocs, cuts, cuts[1:])})
            c.run(allocation)
            self.assertEqual(c.vars["tgcx_house_total"], 100)
            seats = [c.vars[f"tgcx_seats_{i}"] for i in self.gen.blocs]
            self.assertEqual(sum(seats), 100)
            self.assertTrue(all(0 <= n <= 100 and n % 5 == 0 for n in seats))
            for i in self.gen.blocs:
                self.assertLessEqual(abs(c.vars[f"tgcx_seats_{i}"]-100*c.house[i]), 5.01)
        # The two characters of a bloc always hold all its seats, and never more opposed than seats.
        for i in ("conservative", "liberal"):
            for cond, chars in self.gen.bloc_variants(i):
                for k in range(21):
                    c = self.country()
                    c.vars.update({f"tgcx_seats_{i}": 5*k, f"tgcx_opposed_{i}": 5*k})
                    c.run(parse(" ".join(self.gen.split_lines(i))))
                    lead, rest = (c.vars[f"tgcx_gui_cseats_{i}_{s}"] for s in (0, 1))
                    self.assertEqual((lead + rest, lead % 5, rest >= 0), (5*k, 0, True))
        c = self.country(house={"conservative": .85, "liberal": .15})
        self.present(c, "press_rights", "censored_press")
        self.send(c, "tgcx_deal_aye_conservative_0")
        self.send(c, "tgcx_deal_abstain_conservative_1")
        self.assertEqual(self.tally(c), (75, 0, 75))
        c.house = {"conservative": .1, "liberal": .9}
        self.click(c, "tgcx_count_votes")
        self.assertEqual(self.tally(c), (100, 0, 100))
        self.assertEqual(c.vars["tgcx_left_conservative"], 0)
        self.assertEqual(c.vars["tgcx_buy_conservative_total"], 85)  # clipped while the chamber is small

    def test_partial_native_support_and_fully_supportive_blocs(self):
        c = self.flat(self.country(house={"communist": 1.0}, political_movement_strength=.8))
        self.present(c, "press_rights", "censored_press")
        self.assertEqual(self.tally(c)[:2], (60, 40))          # 40 opposed: the leader leads 30 of them
        self.send(c, "tgcx_deal_abstain_communist_0")
        self.assertEqual(self.tally(c), (60, 10, 70))
        self.send(c, "tgcx_deal_aye_communist_1")
        self.assertEqual(self.tally(c), (70, 0, 70))
        self.click(c, "tgcx_count_votes")
        self.assertEqual(self.tally(c), (70, 0, 70))
        c = self.country(house={"anarcho_liberal": 1.0})
        c.flags.add("medicine_invented")
        self.present(c, "health_care", "no_health_care")
        self.assertEqual(c.vars["tgcx_yes"], 100)
        self.click(c, "tgcx_refresh_offers")
        self.assertFalse(c.test(self.decisions["tgcx_deal_aye_anarcho_liberal_0"]["allow"]))   # nobody to move

    def test_the_start_relation_is_computed_for_automatic_characters(self):
        r = self.gen.rules
        # Ruling ideology and distance on the scale (placeholders in the data): liberal rules.
        c = self.country(house={"conservative": .5, "liberal": .3, "socialist": .2}, tag="FRA")
        self.present(c, "press_rights", "censored_press")
        self.assertEqual(c.vars["tgcx_rel_liberal_0"], r.start + r.init_ruling)
        self.assertEqual(c.vars["tgcx_rel_conservative_0"], r.start + r.init_distance[1])
        self.assertEqual(c.vars["tgcx_rel_socialist_0"], r.start + r.init_distance[1])
        c = self.country(house={"conservative": .5, "liberal": .3, "socialist": .2}, tag="FRA", ruling="socialist")
        self.present(c, "press_rights", "censored_press")
        self.assertEqual(c.vars["tgcx_rel_conservative_0"], r.start + r.init_distance[2])
        self.assertEqual(tgcx_leaders.start_relation(r, "reactionary", "communist"), r.start + r.init_distance[4])

    def test_relation_sets_how_much_he_asks(self):
        r = self.gen.rules
        seen = {}
        for relation in range(11):
            c = self.country(house=self.UK)
            c.flags.add("tgcx_rel_init")                       # relations already started
            c.vars.update({f"tgcx_rel_{i}_{s}": 5 for i in self.gen.blocs for s in (0, 1)})
            c.vars["tgcx_rel_conservative_0"] = relation
            self.present(c, "press_rights", "censored_press")
            self.click(c, "tgcx_refresh_offers")
            effective = relation + r.shift["m1"]
            band = sum(effective >= r.bands[b] for b in r.bands)
            self.assertEqual(c.vars["tgcx_gui_band_conservative_0"], band, relation)
            seen[band] = (c.vars["tgcx_gui_ask_conservative_0_abstain"], c.vars["tgcx_gui_ask_conservative_0_aye"])
            self.assertEqual(c.test(self.decisions["tgcx_deal_aye_conservative_0"]["allow"]), band > 0, relation)
        self.assertEqual(seen[0], (0, 0))                      # an enemy refuses
        self.assertEqual(seen[1], (ASK_FREEZE, ASK_FREEZE))
        self.assertEqual(seen[3], (ASK_FREE, ASK_FREEZE))      # a friend abstains for nothing
        # An ally (9+) asks nothing at all: a Liberal who is for the bill, relation 7 (+2).
        c = self.country(house={"conservative": .5, "liberal": .5}, average_militancy=0)
        c.flags.add("tgcx_rel_init")
        c.vars["tgcx_rel_liberal_0"] = 7
        self.present(c, "press_rights", "censored_press")
        self.click(c, "tgcx_refresh_offers")
        self.assertEqual(c.vars["tgcx_gui_band_liberal_0"], 4)
        self.assertEqual(c.vars["tgcx_gui_ask_liberal_0_aye"], ASK_FREE)

    def test_a_law_owed_is_paid_or_broken(self):
        r = self.gen.rules
        event = EV_DEAL_BROKEN + 2*self.gen.all_ideologies.index("reactionary")

        def owing():
            c = self.flat(self.country(house=self.UK))
            self.present(c, "press_rights", "censored_press")
            self.deal(c, "aye", "reactionary", 0)
            return c
        c = owing()
        # Strongly against (-4): effective 1, hostile. His first open agenda law is centralization
        # (the bill's own group and the laws already at his ideal are skipped): two steps, soon.
        ask = self.law_ask("centralization", "regionalism", "regionalism")
        self.assertEqual(c.vars["tgcx_gui_ask_reactionary_0_aye"], ask)
        self.assertEqual(c.vars["tgcx_gui_days_reactionary_0_aye"], r.ask["hostile"]["aye"][1])
        self.assertEqual(c.vars["tgcx_owe_reactionary_0"], ask)
        self.assertIn("tgcx_due_reactionary_0", c.mods)
        self.assertEqual(self.tally(c), (15, 85, 100))
        self.click(c, "tgcx_withdraw")                         # the deal stands
        self.assertEqual(c.vars["tgcx_owe_reactionary_0"], ask)
        self.assertEqual(c.vars["tgcx_deal_reactionary_0"], 0)
        # Owed one law already: he makes no second law deal, on any bill.
        c.mods.discard("tgcx_bill_cooldown")
        self.present(c, "public_meetings", "no_meeting")
        self.click(c, "tgcx_refresh_offers")
        self.assertGreaterEqual(c.vars["tgcx_gui_ask_reactionary_0_aye"], ASK_LAW)
        self.assertFalse(c.test(self.decisions["tgcx_deal_aye_reactionary_0"]["allow"]))
        # Paid: the law reaches the target; the monthly round notices.
        c.laws["centralization"] = "regionalism"
        self.click(c, "tgcx_collect_favours")
        self.assertEqual(c.vars["tgcx_owe_reactionary_0"], 0)
        self.assertNotIn("tgcx_due_reactionary_0", c.mods)
        self.assertEqual(c.vars["tgcx_rel_reactionary_0"], r.start + r.kept)
        # Broken: the deadline passes.
        c = owing()
        ev = self.events[event]
        self.assertFalse(c.test(ev["trigger"]))
        c.mods.discard("tgcx_due_reactionary_0")
        self.assertTrue(c.test(ev["trigger"]))
        c.run(ev["option"][1:])
        self.assertEqual(c.vars["tgcx_owe_reactionary_0"], 0)
        self.assertEqual(c.vars["tgcx_rel_reactionary_0"], r.start + r.broken)
        self.assertEqual(dict(c.punishments[0])["scaled_militancy"],
                         [("ideology", "reactionary"), ("factor", self.gen.n("broken_debt_militancy"))])
        self.assertFalse(c.test(ev["trigger"]))
        # The deadline passes with the law in place: paid, not broken.
        c = owing()
        c.mods.discard("tgcx_due_reactionary_0")
        c.laws["centralization"] = "regionalism"
        c.run(ev["option"][1:])
        self.assertEqual(c.vars["tgcx_rel_reactionary_0"], r.start + r.kept)
        self.assertFalse(hasattr(c, "punishments"))
        # Relations stay within 0..10.
        c.vars["tgcx_rel_reactionary_0"] = 1
        c.run(parse(self.gen.rel_change("reactionary", 0, r.broken)))
        self.assertEqual(c.vars["tgcx_rel_reactionary_0"], 0)

    def test_a_passed_law_moves_relations(self):
        r = self.gen.rules
        c = self.country(house={"conservative": .6, "liberal": .4}, average_militancy=9)
        self.present(c, "press_rights", "censored_press")
        self.vote(c)
        self.assertEqual(c.reform, "free_press")
        self.assertEqual(c.vars["tgcx_rel_conservative_0"], tgcx_leaders.start_relation(r, "conservative", "liberal") + r.disliked)
        self.assertEqual(c.vars["tgcx_rel_liberal_1"], tgcx_leaders.start_relation(r, "liberal", "liberal") + r.liked)
        self.assertEqual(c.vars["tgcx_rel_socialist_0"], tgcx_leaders.start_relation(r, "socialist", "liberal") + r.liked)   # for it, with or without seats

    def test_hand_written_characters_of_a_country(self):
        if "ENG" not in self.gen.char_data:
            self.skipTest("the shipped leaders data has no ENG block or is disabled")
        tories = next(p for p in self.gen.char_data["ENG"] if p.key == "tories")
        peel = tories.cabecilla
        r = self.gen.rules
        c = self.country(house=self.UK, tag="ENG", ruling="liberal")
        c.laws["public_meetings"] = "yes_meeting"
        self.present(c, "press_rights", "censored_press")
        self.click(c, "tgcx_refresh_offers")
        self.assertEqual(c.vars["tgcx_rel_conservative_0"], tories.relation)
        self.assertEqual(c.vars["tgcx_rel_conservative_1"], peel.relation)
        self.assertEqual(c.vars["tgcx_rel_reactionary_0"], tgcx_leaders.start_relation(r, "reactionary", "liberal"))           # no party: automatic
        lead = 5*((tories.cohesion*17 + 50)//100)
        self.assertEqual((c.vars["tgcx_gui_cseats_conservative_0"], c.vars["tgcx_gui_cseats_conservative_1"]), (lead, 85 - lead))
        # The leader: his own vision is for a free press (+1), but his rival rules.
        shift = r.shift[self.gen.char_stance(tgcx_characters(self.gen, "ENG", "conservative")[0], "conservative",
                                             "press_rights", "censored_press", "free_press")]
        effective = tories.relation + shift + (r.rival_rules if tories.rival == "liberal" else 0)
        band = sum(effective >= r.bands[b] for b in r.bands)
        self.assertEqual(c.vars["tgcx_gui_band_conservative_0"], band)
        if 1 <= band <= 3 and tories.agenda == ["public_meetings"]:
            steps, days = r.ask[list(r.bands)[band-1]]["aye"]
            self.assertEqual((c.vars["tgcx_gui_ask_conservative_0_aye"], c.vars["tgcx_gui_days_conservative_0_aye"]),
                             (self.law_ask("public_meetings", "no_meeting", "no_meeting"), days))
        # The cabecilla moves only his own followers.
        before = self.tally(c)
        if c.test(self.decisions["tgcx_deal_aye_conservative_1"]["allow"]):
            self.click(c, "tgcx_deal_aye_conservative_1")
            moved = 85 - lead
            self.assertEqual(self.tally(c), (before[0] + moved, before[1] - moved, before[2]))
        # Another country keeps the automatic characters.
        other = self.country(house=self.UK, tag="FRA")
        self.present(other, "press_rights", "censored_press")
        self.assertEqual(other.vars["tgcx_rel_conservative_0"], tgcx_leaders.start_relation(r, "conservative", "liberal"))

    def test_gui_metadata_migrates_and_clears_with_the_bill(self):
        c = self.flat(self.country(house={"conservative": .83, "liberal": .12, "reactionary": .05},
                                   government="hms_government"))
        self.present(c, "press_rights", "censored_press")
        expected_id = self.gen.bills.index(("press_rights", "censored_press", "free_press"))+1
        for key in list(c.vars):
            if key.startswith("tgcx_gui_") and not key.startswith(("tgcx_gui_cst_",)): del c.vars[key]
        self.click(c, "tgcx_count_votes")
        self.assertEqual(c.vars["tgcx_gui_schema"], 1)
        self.assertEqual(c.vars["tgcx_gui_bill_id"], expected_id)
        self.assertEqual(c.vars["tgcx_gui_stance_conservative"], -1)
        self.deal(c, "aye", "reactionary", 0)
        self.assertEqual(c.vars["tgcx_deal_reactionary_0"], 2)
        self.click(c, "tgcx_audience")
        self.assertEqual(c.vars["tgcx_gui_crown_audience"], 1)
        self.click(c, "tgcx_withdraw")
        self.assertEqual(c.vars["tgcx_gui_active"], 0)
        self.assertEqual(c.vars["tgcx_gui_bill_id"], 0)
        self.assertEqual(c.vars["tgcx_gui_offers"], 0)
        self.assertEqual(c.vars["tgcx_gui_ask_reactionary_0_aye"], 0)
        self.assertFalse(any(f.startswith(("tgcx_cs_", "tgcx_billgroup_")) for f in c.flags))
        self.assertEqual(c.vars["tgcx_gui_schema"], 1)  # Country schema survives cleanup.
        # A queued obsolete recovery after withdrawal cannot resurrect GUI activity.
        c.run(self.events[EV_CATALOG_COUNT]["option"][1:])
        self.assertEqual(c.vars["tgcx_gui_active"], 0)

    def test_bill_sent_decisions_recheck_their_own_conditions(self):
        # The native decision click does not test potential/allow; the effect must.
        c = self.country(house=self.UK, government="hms_government", ruling="liberal")
        self.send(c, "tgcx_refresh_offers")                    # no bill: nothing
        self.assertNotIn("tgcx_gui_offers", c.vars)
        self.present(c, "press_rights", "censored_press")
        self.assertEqual(c.vars["tgcx_gui_crown_veto"], 1)
        self.assertEqual(c.vars["tgcx_gui_crown_signs"], 0)
        self.assertEqual(c.vars["tgcx_gui_ruling"], self.gen.all_ideologies.index("liberal") + 1)
        self.assertEqual(c.vars["tgcx_gui_government"],
                         (self.gen.limited + self.gen.full).index("hms_government") + 1)
        law = c.laws["press_rights"]
        self.send(c, "tgcx_call_vote")                         # still in debate
        self.assertEqual(c.laws["press_rights"], law)
        self.assertIn("tgcx_law_active", c.flags)
        self.click(c, "tgcx_audience")
        self.assertEqual(c.vars["tgcx_gui_crown_signs"], 1)
        self.click(c, "tgcx_withdraw")
        self.assertNotIn("tgcx_law_active", c.flags)
        c.mods.discard("tgcx_bill_cooldown")
        self.send(c, "tgcx_withdraw")                          # no bill: no new cooldown
        self.assertNotIn("tgcx_bill_cooldown", c.mods)
        self.send(c, "tgcx_deal_aye_conservative_0")           # no bill: no deal
        self.assertEqual(c.vars.get("tgcx_deal_conservative_0", 0), 0)
        self.assertNotIn("tgcx_freeze", c.mods)

    def test_the_monthly_round_starts_relations_and_counts_ticks(self):
        c = self.country(house={"liberal": .6, "conservative": .4}, ruling="liberal", prestige=60)
        self.click(c, "tgcx_collect_favours")
        self.assertEqual(c.vars["tgcx_favours_ticks"], 1)
        self.assertEqual(c.vars["tgcx_gui_legislature"], 1)      # the Reforms tab may offer bills
        self.assertEqual(c.vars["tgcx_rel_liberal_0"], tgcx_leaders.start_relation(self.gen.rules, "liberal", "liberal"))
        self.assertNotIn("tgcx_favours", c.vars)                 # no pool of favours (D38)
        c.vars["tgcx_rel_liberal_0"] = 8
        self.send(c, "tgcx_collect_favours")                     # duplicate within the month
        self.assertEqual(c.vars["tgcx_favours_ticks"], 1)
        c.mods.discard("tgcx_favours_tick")
        self.click(c, "tgcx_collect_favours")
        self.assertEqual(c.vars["tgcx_favours_ticks"], 2)
        self.assertEqual(c.vars["tgcx_rel_liberal_0"], 8)        # started once, then kept

    def test_no_favours_lots_or_bloc_promises_remain(self):
        self.assertFalse(any(n.startswith(("tgcx_buy_", "tgcx_promise_")) for n in self.decisions))
        self.assertEqual(sum(n.startswith("tgcx_deal_") for n in self.decisions), 2*2*len(self.gen.blocs))
        text = next(t for path, t in self.files.items() if Path(path).parent.name == "decisions")
        self.assertNotIn("tgcx_favours=", text.replace("tgcx_favours_ticks", "").replace("tgcx_favours_tick", ""))
        self.assertNotIn("tgcx_spent", text.split("tgcx_deal_abstain", 1)[1].split("tgcx_audience", 1)[0])

    def test_collection_writes_the_reforms_offer_from_tgc_allow(self):
        # D14: 1 + the current law whose next step passes the target option allow.
        c = self.country()
        allow = {g: dict(self.gen.groups[g]["body"][self.gen.groups[g]["options"][1]]).get("allow", [])
                 for g in self.gen.chosen}
        self.click(c, "tgcx_collect_favours")
        values = {g: c.vars[f"tgcx_gui_offer_{g}"] for g in self.gen.chosen}
        self.assertEqual(values, {g: 1 if c.test(allow[g]) else 0 for g in self.gen.chosen})
        self.assertEqual(set(values.values()), {0, 1}, "both an offered and a blocked first step")
        g = next(g for g, v in values.items() if v == 1)
        c.laws[g] = self.gen.groups[g]["options"][1]
        second = dict(self.gen.groups[g]["body"][self.gen.groups[g]["options"][2]]).get("allow", [])             if len(self.gen.groups[g]["options"]) > 2 else None
        c.mods.discard("tgcx_favours_tick")
        self.click(c, "tgcx_collect_favours")
        self.assertEqual(c.vars[f"tgcx_gui_offer_{g}"], 2 if second is not None and c.test(second) else 0)
        c.laws[g] = self.gen.groups[g]["options"][-1]                 # no next step
        c.mods.discard("tgcx_favours_tick")
        self.click(c, "tgcx_collect_favours")
        self.assertEqual(c.vars[f"tgcx_gui_offer_{g}"], 0)

    def test_reports_select_one_event_without_conditional_options(self):
        # The game screenshot showed all option triggers ignored. Do not teach
        # the interpreter a UI capability that the real engine did not provide.
        for eid, tree in self.event_trees.items():
            options = [v for k, v in tree if k == "option"]
            self.assertEqual(len(options), 1, eid)
            self.assertFalse(any(k in ("trigger", "allow", "limit") for k, _ in options[0]), eid)
        decisions = next(s for p, s in self.files.items() if Path(p).parent.name == "decisions")
        self.assertNotIn(f"country_event={EV_CATALOG_COUNT}", decisions)
        c = self.country(house={"conservative": .83, "liberal": .12, "reactionary": .05})
        self.present(c, "press_rights", "censored_press")
        self.assertEqual(c.events, [420000146])  # Nay leads by 80.
        self.assertEqual((c.vars["tgcx_yes"], c.vars["tgcx_no"]), (10, 90))
        c.events.clear()
        self.click(c, "tgcx_count_votes")
        self.assertEqual(c.events, [420000146])
        # Each possible tally must choose exactly one result event, including
        # ties and no-quorum counts; the event always has one ordinary option.
        report = parse("\n".join(self.gen.report_block()))
        for yes in range(0, 101, 5):
            for no in range(0, 101-yes, 5):
                c.vars.update(tgcx_yes=yes, tgcx_no=no,
                              tgcx_margin=yes-no, tgcx_quorum=yes+no)
                c.events.clear()
                c.run(report)
                self.assertEqual(len(c.events), 1, (yes, no))
                self.assertNotEqual(c.events[0], EV_CATALOG_COUNT)
                expected = (420000151+(yes+no)//5 if yes+no < 50 else
                            420000110+(yes-no)//5-1 if yes > no else
                            420000130+(no-yes)//5)
                self.assertEqual(c.events[0], expected, (yes, no))
        # Saves with the obsolete dispatcher queued can still request a real
        # fresh count. New Present/Count requests never use that recovery path.
        c.events.clear()
        c.run(self.events[EV_CATALOG_COUNT]["option"][1:])
        self.assertEqual(c.events, [420000146])


if __name__ == "__main__":
    unittest.main(verbosity=2, testRunner=unittest.TextTestRunner(stream=sys.stdout, verbosity=2))
