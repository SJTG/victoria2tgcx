# Plan: favours negotiated with characters (cabecillas, Trust)

2026-11-10. Extends `docs/plan-character-driven-1109-v3.md` (D24, D25, D31, D34).
Status: **proposal, board 2b drawn, not approved** (R10). Design canvas:
https://claude.ai/artifact/TnqwwjvJUDYEaXejVjap7D, board "2b · Bill con personajes".

## 1. Why

In-game test of 2026-11-10 (LAW-4 passed: textures, 21 of 21 buttons, buy/promise/count/withdraw).
The user asked for the Price in Favours and Political Favours panels to be reworked:
favours should be negotiated with **characters**, and when a party leader has few
followers it should be better to deal with a different **cabecilla** (party figure).

## 2. Decisions asked (user answers, 2026-11-10)

| # | Decision | Answer |
|---|---|---|
| D37 | Where cabecillas come from | **Mixed**: written by hand in `data/tgcx_leaders.txt` for important countries (ENG...), **auto-generated** elsewhere |
| D38 | Negotiation currency | **Personal relation per character** (Trust), on top of the prestige pool of favours |
| D39 | Order of work | Board and plan first, user approves, then implement |
| D40 | A cabecilla's followers vote by the cabecilla's own stance | **proposed** (refines D31, see 3) |
| D41 | Price follows the chosen character's stance; seat purchase is capped by his followers | **proposed** |

## 3. Model

- A **party** has one leader and zero or more **cabecillas**. Each character has `followers` (seats),
  `stance` rows (as leaders already have) and a **Trust** value with the player (-3..+3, starts 0).
- Seats of a party split as `leader = round(cohesion x seats)` and the rest among the cabecillas (D34 cohesion
  stays fixed per party in data). Example from the board: 85 conservative seats, cohesion 70 ->
  about 60 follow the leader, about 25 a cabecilla. These figures are **illustrative**, not data.
- **D40 refines D31.** D31 blended the leader's stance with the ideology's for the whole bloc. Now the
  leader's followers vote by the leader's stance and each cabecilla's followers by his own. An **auto cabecilla**
  has no stance rows and uses the ideology's stance, so the voting result stays near D31's blend. Both are not
  identical (D31 rounds one blended stance; D40 splits seats), so CHAR-2 compares them and the user reviews the difference.
- **Price (D41).** The table of `docs/law-design.md` (stance -> abstain / aye price) is read with the chosen
  character's stance. Seats bought are capped by his followers; lots of 5 or 25 as today.
- **Trust (D38).** Proposal, numbers to be reviewed by the user (R9): each purchase from a character
  gives +1 Trust, it fades 1 per year toward 0, and Trust >= +2 lowers the price by 1 favour (minimum 0),
  Trust <= -2 raises it by 1. Breaking a promise lowers Trust of the party's characters. Later: events,
  backers, disputes (plan v3 section 4).
- **A bloc with no party** (Reactionary on the board) has no character: priced by bloc stance, as today.

## 4. Bill board 2b (what changes against board 2)

| Area | Change |
|---|---|
| Bloc card | Segmented bar of seats per character; one chip per character (leader, cabecilla, auto) with followers, stance and Trust; selecting a chip picks who you negotiate with |
| Stance, Votes | Stance shown is the selected character's; votes are the sum over characters |
| Price in Favours | Header "Negotiating with <name>"; table highlights his stance row; seat cap line |
| Political Favours | Stays one prestige pool (+3 per month) |
| Debts | Becomes "Debts and Trust" (Trust per character, promises as before) |
| Hemicycle | Abstain dots appear (white) when a cabecilla is neutral |

Native buttons: the chips are new buttons, so LAW-4's "bound=N of M" check must cover them. The tick
for the chosen chip is drawn from the atlas like By vote.

## 5. Feasibility notes (to check before code)

- The vote is **the mod's own tally** (`docs/law-design.md` section 4: `tgcx_yes/no` plus purchases), not the
  engine's per-ideology vote, so splitting a bloc between characters is possible in script.
- Purchase decisions today are per bloc and lot (`tgcx_buy_abstain_conservative_m1` in the log). They
  become per character (`tgcx_buy_<kind>_<character>_<lot>`); the monthly `tgcx_collect_favours`
  and the DLL's native decision handler stay. **Not yet read**: how `gen_laws.py` builds those decisions and
  how many exist for ENG; this is the first step of CHAR-2 and decides the real cost.
- Trust needs persistent state per character (script variables); the DLL only draws (R5).
- Character names are data, not game objects: portraits stay generic TGC art (approved).
- Real parties and seats per country are still unmeasured (CHAR-0). Hand-written cabecillas for ENG are placeholders.

## 6. Cards (in order, after the user approves board 2b)

1. **CHAR-1**: schema in `data/tgcx_leaders.txt` for cabecillas (`followers` or computed rest, `trait`, `stance`),
   `tools/tgcx_leaders.py` auto cabecilla for the remainder, tests in `tools/test_leaders.py`.
2. **CHAR-2**: read `gen_laws.py` purchase decisions; per-character decisions and tally; Trust variables; `test_gen_laws.py`
   compares the result with D31 for blocs with no hand-written cabecilla.
3. **BILL-4**: DLL: chips as native buttons, selected character, segmented bar, price line (new layout in
   `tools/tgcx_bill_gui.py`, regenerate `tgcx_bill_catalog.h`).
4. **LEAD-1** (user): review leaders, cabecillas, followers, Trust numbers [R9].
5. **CHAR-0** in parallel: measure parties per country (`docs/instructions-char-0.md` part B).

Open for the user: where Trust shows outside the Bill window (Parties tab, board 1b), and whether a character
may be "bought off" (permanent allegiance) or only per bill.
