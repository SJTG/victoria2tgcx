# Plan v3: characters lead their parties, parties lead their blocs

2026-11-09. Supersedes v2 where they differ; v2's board-by-board tables for
Politics, Bill and Head of State still apply. Design canvas (R10):
https://claude.ai/artifact/TnqwwjvJUDYEaXejVjap7D (boards 1 Politics, 1b Parties tab, 2 Bill, 3 Head of State).

## 1. What changed from v2

| v2 | v3 | Why |
|---|---|---|
| Leaders are faces; the bloc is the unit of stance | **Leaders are persons with tastes; the bloc follows its leader** (D25, D31) | The user wants personality, later events and interaction |
| D25 open: how two parties split a bloc | **The bloc follows the leader of the party with most seats** (ties: first listed) | User, 2026-11-09 |
| D31: traits/policies change nothing in v1 | **A leader's stance changes the bloc's stance** through cohesion; **prices are untouched** | Personality must matter; prices stay reviewable (LAW-1) |
| Three boards | **Four**: Parties is a tab of Politics | User asked for a party view |
| HoS: Born, House, etc. | HoS trimmed: Reigning since, Heir, Prime Minister, Government, Traits; age in the title | No idle information |

## 2. The model

- **Bloc** = ideology holding upper-house seats. Holds 0, 1 or several parties.
- **Party** = a faction with one **leader**, a **cohesion** (0-100) and seats.
- **Leader** = a character with tastes: optional per-law-group stance rows (`ideal`, `intensity`) and a trait label.
- **The bloc's stance** on a bill: `round(cohesion/100 x leader + (1 - cohesion/100) x ideology)` on the -2..+2 scale of `docs/law-design.md` section 3. Integers, halves away from zero. A group the leader has no row for uses the ideology's stance. A bloc with no party uses the ideology's stance.
- Example (mockup and `test_leaders.py`): 1836 UK press law, Tories' leader mildly for free press (+1), ideology against (-1), cohesion 70 -> 0, undecided.

## 3. The Parties tab (first plan)

Board 1b. In: list by bloc with cohesion, leader card, Policies table (Leader | Ideology | Party follows), rank (leads / rival / ruling). Out for now (marked LATER on the board): backers of the leader, disputes. Spec for the card: `docs/instructions-pol-1.md`.

## 4. Cut: first plan, later

| First plan | Later |
|---|---|
| Parties tab, read-only | Backers (members who carry the leader) |
| Cohesion = fixed number from data | Cohesion that moves (events, decisions, results): needs savegame state |
| Formula applied to Bill stances | Disputes visible inside a party |
| Bloc follows largest party's leader | Events and interaction with leaders |
| One country first (UK 1836) | Alliances between blocs |

**Alliances (later, designed apart).** A relation bloc -> bloc with a degree, from "we follow you on everything" to "subjugated", with intermediate degrees. A bloc copies an allied leader's stance with a weight. Not specified until the first plan works.

## 5. Action plan

| Card | Work | Status |
|---|---|---|
| PLAN-0 | Archive Volunteers NEXT.md, new NEXT.md, decisions in AGENTS.md section 9, card instructions | **done** |
| MOCK-0 | Four boards in the canvas | **done** (CSS approximation; real game art needs `E:\v2re\mockups`) |
| BILL-FIX / U-14 | LAW-4 patch + game check | patch written, **not compiled**; check in `docs/instructions-char-0.md` part A |
| LEAD-0 | `data/tgcx_leaders.txt`, `tools/tgcx_leaders.py`, generator hook (off by default), `tools/test_leaders.py` | **done, test passes without TGC**; generator output with `enabled = yes` not run against real TGC |
| CHAR-0 | Measure parties per country; decide whether GH-6 is needed | instructions written, **not run** |
| LEAD-1 | You review leader values [user, R9], enable, run `tools/test_gen_laws.py` | waiting |
| CHAR-1 | Leader registry for more countries (documented sources, nothing invented) | after CHAR-0 |
| POL-1 | Parties tab in the game | after U-14 and CHAR-0 |
| BILL-1..3, U-13 | v2 section 5, with leader cards and the leader-blended stance | after POL-1 data exists |
| GOV-0..2 | Head of State per board 3 | after Bill |

## 6. What was implemented and what it does not do yet

- **Generator hook**: with `enabled = yes`, each bill's stance flags are set per country tag: countries with data get the blended stance, every other country keeps the ideology's. With `enabled = no` (shipped) the output is identical to before.
- **Known gap**: the bill decision's description text still lists the ideology stances for everyone; it does not show the blended stance for the UK.
- **Known risk**: the generated flags use the `random_owned` IF emulation per tag. `tools/test_gen_laws.py` and `tools/test_law_catalog.py` need an installed TGC and were **not run** here; run them before enabling.
- Party seats in the data file are the mockup's example (85 / 10), not measured. In the game the upper house holds seats per ideology only (`CCountry+0x8B0`); party seats need CHAR-0 or an estimate.

## 7. Decisions

| ID | Decision | Status |
|---|---|---|
| D24 | Party = faction, leader = character, ideology = seat bloc | closed (user, 2026-11-09) |
| D25 | Bloc follows the leader of its party with most seats; ties first listed | **closed** (user, 2026-11-09) |
| D26 | Leader names: documented where possible, else generated per culture and fixed by id | proposed |
| D27 | Leaders fixed per party and date first; ageing/death later | proposed |
| D28-D30, D32, D33 | As in v2 section 6 | unchanged |
| D31 | Leader stance changes bloc stance (via cohesion); prices unchanged | **closed** (user, 2026-11-09; revises v2) |
| D34 | Cohesion: fixed per party in data for the first plan; dynamic later | **closed** (user, 2026-11-09) |
| D35 | Parties is a tab of the Politics window | **closed** (user, 2026-11-09) |
| D36 | Alliances between blocs, with degrees (full follow ... subjugated) | **later**, designed apart (user idea, 2026-11-09) |

## 8. Risks

1. **No compile, no game here.** Everything in Rust and the GUI is written blind; each card is "done, not tested in game" until you see it.
2. **Overlay technique unproven** (LAW-4 is its test); portraits and names depend on it or on route B.
3. **CParty unmapped.** Reading parties from the executable needs RE if CHAR-0 (a) is not 0.
4. **Hand-written data.** Leaders, stances and cohesion are content, not code: UK 1836 only, reviewed by you.
5. **Hidden variable.** Cohesion is shown on the Parties tab and in the Bill cards so the player never meets an unexplained stance.
