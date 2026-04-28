# Case: Mobile app retention — phased exploration to validation (fictional)

**Note:** This is a fabricated case story used as sample content for the uxr-agent-template. It is not based on a real organization or project.

## Situation

A consumer wellness app had a 60-day retention cliff: 71 percent of new installs were active at day 7, 19 percent at day 60. The product team had several theories (notification fatigue, content depth, social hook missing) but none had been tested. The CEO wanted to know which lever to pull next quarter and the team couldn't agree.

## Task

Identify which retention drop-off was driving the cliff and validate a counter-hypothesis under test. The team had the live app, prior research (one persona round n=15 from launch, no follow-up), analytics for 14 months, and a willingness to ship a low-fidelity prototype change behind a feature flag if research recommended it.

## Action

Routed to a Mixed (Explore + Validate) cascade. Recommended a phased study aligned to the Discovery → Concept → Validation → Strategy Review framework:

**Phase 1 (Discovery, weeks 1-2):** Diary studies with 12 lapsed users (last active days 30-60) and 8 still-active users (active >90 days). Goal: surface what changed between week 2 and week 6 for the lapsed cohort. Captured daily check-ins on app use, life context, and what the app was or wasn't delivering against expectations.

**Phase 2 (Concept, week 3):** Co-creation with 6 of the diary participants on three candidate intervention concepts — push notification redesign, social-thread feature, and content-depth expansion. Sessions surfaced which concepts felt natural vs. forced.

**Phase 3 (Validation, weeks 4-5):** Low-fidelity prototype usability testing on the top concept (notification redesign — narrower scope, more frequent on-app moments). 10 moderated sessions with new-install simulation, plus 80-participant unmoderated A/B against the existing notification cadence.

## Result

Phase 1 surfaced the actual mechanism: the app was treating new users like long-term users by week 3, sending the same daily-frequency notifications regardless of where the user was in their behavior change cycle. Lapsed users described the notifications as "constant pressure"; active users described the same notifications as "helpful nudges" — the difference was whether the user had already built a habit.

Phase 2 narrowed three candidates to one (notification frequency that adapted to user-stated habit strength). Phase 3 validated: A/B test showed 14-point retention lift at day 30 for the adaptive cohort vs. control. The CEO greenlit the redesign.

Total study time: 39 days end-to-end. The phased structure prevented a common failure mode: jumping directly to validation on a pre-formed hypothesis. The hypothesis we ended up validating was different from any of the three the team started with.

## Methodological notes

- Mixed intent here meant the cascade routed to a phased plan rather than a single method. The Discovery → Concept → Validation pacing matched the standard convergence framework: divergent exploration constrained to agreed problem-audience spaces, then to feasible concepts, then to 1-3 solutions.
- Diary studies were essential for Phase 1 — interviews alone would have missed the temporal pattern (week 3 was when notifications started feeling like pressure).
- Phase 2 co-creation with diary participants added a continuity bonus: participants had already shared their context, so concept reactions came with built-in user-specific framing.
- Phase 3 mixed moderated and unmoderated deliberately — moderated for "why," unmoderated for the comparable retention numbers the CEO needed to make the call.
