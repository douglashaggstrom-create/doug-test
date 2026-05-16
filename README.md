# Eurovision 2026 Live Voting Tracker

Track the jury and televote results of the Eurovision 2026 Grand Final in real time.

## Setup

```bash
pip install flask requests beautifulsoup4
python app.py
```

Open **http://localhost:5000** in your browser.

---

## Live Mode (Tonight)

### Phase 1 — Jury Scores
1. After the jury round ends on TV, click **"Fetch Jury Scores"** — the app will try to scrape from `eurovision.tv`, `eurovisionworld.com`, and `esctoday.com`.
2. If the auto-fetch fails or returns incomplete data, enter each country's jury total manually in the table. A running total at the bottom should reach ≤ 2,030 pts.
3. Click **"Confirm Jury Scores"** to lock in the jury results and open the televote tracker.

### Phase 2 — Televote Reveal
Countries appear in televote reveal order (lowest jury score first, matching the show).  
As each country's televote total is announced on TV:
1. Type the score into the input field.
2. Press **Enter** or click **Reveal ⟶**.

The leaderboard updates instantly with:
- 🏆 Current leader
- ✅ Countries that can still win
- ❌ Mathematically eliminated (even 12 pts from every bloc wouldn't beat the leader)
- Fair-share and trend-floor estimates for unrevealed countries

---

## Test Mode (Verify Before Tonight)

Click **"Load 2025 Test Data"** (top right) to load approximate Eurovision 2025 Basel results:
- **26 countries**, 37 jury blocs (2,146 pts), 38 televote blocs (2,204 pts)
- **Winner: Austria (JJ) — 258 jury + 178 televote = 436 total**

In test mode you can:
- **▶ Auto-reveal next** — reveals one country at a time using the pre-loaded 2025 data
- **⏩ Auto-reveal all** — skips to the final result instantly
- Still type scores manually to verify the elimination logic with custom inputs

> **Note:** The 2025 test scores are approximate figures used for app testing.

---

## Scoring Reference

| | Jury | Televote |
|---|---|---|
| **2026 blocs** | 35 | 36 |
| **Points per bloc** | 58 (1,2,3,4,5,6,7,8,10,12) | 58 |
| **Total pool** | 2,030 pts | 2,088 pts |

**Elimination rule:** A country is out when  
`jury_score + (36 × 12) < current_best_total`

**Floor estimates:**
- *Fair share* = remaining televote pool ÷ unrevealed countries
- *Trend floor* = last revealed country's televote score

---

## Reset

Click **↺ Reset** in the header to return to live 2026 mode and clear all scores.
