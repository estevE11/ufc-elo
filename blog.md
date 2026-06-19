# Building a UFC Elo Rating System

Most “who’s the GOAT?” debates never end because we argue past each other without a shared scoreboard. This project is an attempt to build one: a complete historical record of UFC bouts, fed into a custom Elo model that tracks both pound-for-pound and divisional ratings as they evolve over time.

The goal is not to settle every argument forever. It is to make the assumptions explicit, tunable, and reproducible.

---

## Architecture

The system has four layers, each with a single responsibility:

1. **Data ingestion** — A scraper pulls every completed UFC event from [ufcstats.com](http://ufcstats.com), normalizing fighters, results, weight classes, and championship context into structured records. It supports full historical backfills and incremental weekly updates.
2. **Rating engine** — Fights are replayed chronologically. Each bout updates two parallel rating tracks per fighter: a global pound-for-pound score and a division-specific score.
3. **Historical snapshots** — After every fight, the engine records the state of the ratings. These snapshots are forward-filled monthly so that any point in time can be queried — including for fighters who are inactive but still ranked.
4. **Visualization** — Timeline charts by division, P4P leaderboards over time, and animated bar-chart races that show how the top ten shifts year by year.

All tuning parameters — starting Elo, K-factor, loss penalty, carry-over percentage, result multipliers — are defined separately from the computation logic, so the entire history can be recalculated when assumptions change.

---

## The Rating Model

Each fighter carries two kinds of rating:

| Track | Description |
|-------|-------------|
| **P4P** | Global pound-for-pound Elo |
| **Divisional** | Per-weight-class Elo (lightweight, welterweight, featherweight, etc.) |

Every fight is processed **oldest to newest**. For each bout, the engine:

1. Initializes the fighter in a new division if needed (see carry-over below).
2. Computes the **expected win probability** from both fighters’ current ratings.
3. Applies an **adjusted K-factor** based on how the fight ended.
4. Updates winner and loser ratings — with a heavier penalty on losses.

The standard expected-score formula:

\[
E_A = \frac{1}{1 + 10^{(R_B - R_A) / 400}}
\]

A win against a higher-rated opponent moves the needle more. A loss against a weaker one hurts more. The rival’s rating always matters — there is no update that ignores who you fought.

---

## Design Decisions

### 1. The 90% weight-class carry-over

When a fighter moves divisions, they should not start from zero. A champion dropping from lightweight to welterweight is not a regional unknown — they arrive with a reputation.

**Rule:** On first appearance in a new division:

- If their previous division Elo is **above the baseline (1000)**, carry over **90%** of it — but never debut below **1000**.
- If their previous division Elo is **at or below 1000**, start at **1000** with no penalty.

This prevents absurd cases like a top lightweight debuting at featherweight with a deflated ~950 rating simply because a flat percentage was applied blindly. The carry-over fires once, at division debut. After that, only fight results move the divisional score.

The intuition: crossing weight classes is a transition, not a reset. A fighter’s proven quality should follow them — dampened slightly to reflect the uncertainty of a new division, but never erased.

> **Future plot:** Division-change debut ratings — Volkanovski, Poirier, and others who moved weight classes mid-career.

---

### 2. Result multipliers (finish quality)

Not all wins carry the same information. A dominant knockout tells you more about the gap between two fighters than a razor-thin split decision where judges disagreed.

| Result | Multiplier | Rationale |
|--------|------------|-----------|
| KO/TKO | 1.3 | Decisive finish — high signal |
| Submission | 1.3 | Same tier as KO/TKO |
| Unanimous decision | 1.0 | Baseline |
| Majority decision | 0.8 | Narrower margin of victory |
| Split decision | 0.7 | Closest call — lowest confidence |
| DQ | 1.0 | Treated as a normal win/loss |
| Draw | 0.5 | Partial credit |
| No contest | 0.0 | No rating change |

The multiplier scales the K-factor:

\[
K_{adjusted} = K_{base} \times \text{result multiplier}
\]

A knockout therefore moves ratings roughly 30% more than a unanimous decision at the same base K. The underlying logic: finishes reduce judge noise. When a fighter stops someone outright, the rating system should reflect higher confidence in the outcome than when three scorecards barely agree.

> **Future plot:** Distribution of Elo swings by finish type across the full UFC dataset.

---

### 3. The 1.5× loss penalty

Standard Elo is zero-sum: what the winner gains, the loser loses. This system deliberately breaks that symmetry.

**Rule:** Losses cost **1.5×** what an equivalent win would have gained.

\[
\Delta_{winner} = K \times (1 - E_{winner})
\]
\[
\Delta_{loser} = -K \times 1.5 \times E_{loser}
\]

**Why?** The goal is not simply to reward win streaks or undefeated records. It is to separate two kinds of long careers:

| Career shape | What happens |
|--------------|--------------|
| **Many wins, many losses** | Wins and losses pile up, but each loss costs 1.5× more than a comparable win returns. Over 20+ fights, that deficit compounds — a .750 fighter with a dozen losses bleeds rating even while beating mid-tier opposition. |
| **Many wins, few losses** | The same volume of fights without the tax. Sustained excellence over a long window is preserved and rewarded. |

A fighter on a hot streak benefits — every win adds points and they avoid the expensive penalty. But the real target is the **volume grinder** with a respectable record on paper that hides a pattern of losses against top competition. Standard Elo treats a 22–8 career and a 22–2 career too similarly if the wins came against comparable opponents. The 1.5× multiplier makes that gap visible.

This is why **Jon Jones** and **Georges St-Pierre** sit where they do: long careers, elite opposition, and only a handful of losses between them. The system does not need a manual “legend bonus” — longevity plus selectivity does the work.

The trade-off: ratings are no longer strictly zero-sum. Total rating mass drifts slightly over time. That is intentional — ranking *shape* matters more than conservation of points.

> **Future plot:** Cumulative Elo gained vs lost over a career — comparing a high-volume .700 fighter against a long-tenure .900 fighter.

---

### 4. Inactive fighters keep their rating

If a fighter stops competing, their Elo does not decay. Ratings are carried forward monthly through the present.

Jon Jones not fighting for two years does not erase the fact that he beat the best competition available when he was active. He remains on the board at his last rating until someone overtakes him — or until he returns.

An inactivity decay mechanism exists in the parameter set but is currently **disabled**. The reasoning: absence of competition is not the same as decline. Penalizing inactivity would conflate “not fighting” with “getting worse,” which punishes retirees and injured fighters unfairly.

> **Future plot:** Animated P4P bar-chart race (2020–present) showing how the top ten shifts while inactive legends hold their ground.

---

## Case Studies

### Khabib Nurmagomedov — undefeated, but not automatic #1

Many fans call Khabib the GOAT. He retired **29–0**, never tasted defeat. In his own words: *"Nobody is invincible. If you fight enough, you are gonna get beaten."*

The model respects the undefeated record — Khabib sits **4th all-time P4P** (~1208 Elo) — but does not hand him #1 on that alone.

**Why not higher?**

- **Volume:** 13 UFC fights. Jones, GSP, and others accumulated far more high-stakes data points against elite opposition over longer windows.
- **Strength of schedule over time:** Khabib beat excellent fighters, but the loss penalty structurally rewards those who kept winning against the very best across multiple generations of contenders. Islam Makhachev, his successor, continued climbing after him.
- **The undefeated tailwind has limits:** Never losing protects your rating from the 1.5× penalty, but it does not manufacture wins you never had. Perfection without volume cannot outrun longevity with near-perfection.

Khabib’s score is **high because he never lost**. It is **not #1 because he did not fight enough times against enough top-ranked opponents** to separate from Jones, GSP, and active elites on volume and strength-of-schedule alone.

> **Future plot:** Khabib vs Jones P4P timeline overlay.

---

### Jon Jones — one loss, sustained elite competition

Jones is **#1 P4P** (~1285 Elo) in the current snapshot.

**Why he ranks above Khabib despite one loss:**

- **Strength of schedule:** Jones fought consistently at the top of light heavyweight and heavyweight for over a decade — Cormier (twice), Gustafsson, Miocic, and others at or near their peaks.
- **The loss was early and recovered:** His disqualification loss to Matt Hamill came in 2009, before his prime. The expensive-loss rule hurt him once; he then went on one of the longest elite runs in the sport’s history.
- **Volume + quality:** Enough fights, enough wins against highly-rated opponents, for the model to keep rewarding him — even while inactive, his rating holds until surpassed.

One loss did not define his ceiling. A long career with few losses against the best opposition did.

> **Future plot:** Jones career P4P with opponent rating at time of fight annotated on each inflection point.

---

## Open Problems

Several factors are tracked in the data but not yet weighted in the model:

| Factor | Status |
|--------|--------|
| Interim vs undisputed championships | Recorded, not yet weighted |
| Short-notice fights | No preparation-time adjustment |
| Catchweight / weight-missed bouts | Tracked, not penalized differently |
| Pre-UFC regional records | Outside the dataset |
| Women's divisions | Same model, thinner early history |
| Inactivity decay | Parameterized but disabled |

These are candidates for future iterations as the model matures.

---

## System Parameters

The model is fully defined by a small set of constants:

| Parameter | Value | Role |
|-----------|-------|------|
| Starting Elo | 1000 | Baseline for new fighters and division debuts |
| Base K-factor | 32 | Controls how much each fight moves ratings |
| Loss multiplier | 1.5 | Asymmetric penalty on defeats |
| Debut carry-over | 90% | Cross-division reputation transfer (floor at 1000) |
| Result multipliers | 0.7–1.3 | Finish-quality scaling on K |

Changing any parameter triggers a full historical recalculation. The entire rating history is a pure function of the fight record and these assumptions — nothing is hand-tuned per fighter.

---

## Closing Thought

Any rating system encodes values. This one values **decisive finishes**, **punishes losses heavily enough to sink high-volume careers with mixed records**, **respects division changes**, and **rewards long careers with few losses** — the Jon Jones and GSP archetype — over grinding out wins while absorbing defeats.

Khabib and Jones are both legends. The model puts Jones on top today not because it dismisses perfection — but because it asks a harder question: *what did you do, against whom, for how long — and how much did losing cost you along the way?*

More visualizations, more edge cases, and more tuning ahead.
