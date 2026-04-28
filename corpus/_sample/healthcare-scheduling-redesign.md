# Case: Healthcare scheduling flow redesign (fictional)

**Note:** This is a fabricated case story used as sample content for the uxr-agent-template. It is not based on a real organization or project.

## Situation

A regional health system was seeing a 22 percent abandonment rate on its online appointment scheduling flow. Mobile users abandoned at higher rates than desktop. Stakeholders had two competing hypotheses: the form was too long, or the specialty selector was too confusing. Engineering had a redesign queued but no one was confident the redesign solved either hypothesis.

## Task

Validate the proposed redesign before sprint allocation. The PM needed a go/no-go decision in three weeks. The design team had a Figma prototype covering the four most-used flows (primary care, cardiology, dermatology, behavioral health). Prior research existed in the form of two quantitative surveys (n=480 and n=312) and three rounds of moderated usability testing on the prior version.

## Action

Recommended unmoderated task-based testing with statistical rigor over moderated sessions, given:
- Decision posture was certainty, not direction (clear hypothesis, design ready)
- Prior moderated rounds had already surfaced qualitative themes
- The PM needed comparable conversion and time-on-task metrics across user segments

Designed a 90-participant unmoderated study via UserTesting.com. Three task scenarios per participant (initial booking, reschedule, cancel), randomized order to control for fatigue effects. Measured task completion rate, time-on-task, error count, and SUS score. Recruited from a panel matched on age, insurance type, and primary care vs. specialty visit history.

## Result

Completion rate on the redesign: 78 percent vs. 56 percent on the prior version. Time-on-task: 2 minutes 14 seconds vs. 3 minutes 48 seconds. SUS score: 72 vs. 51.

Specialty selector errors dropped from 31 percent to 6 percent — confirming the "specialty selector is confusing" hypothesis as the dominant friction. Form length reduction had a smaller effect (8 percent fewer abandons attributable to it). The PM shipped the redesign on the spec we tested, with two prioritized follow-ups for cardiology specifically (where errors remained at 11 percent).

The study took 17 days end-to-end including recruit, fielding, and analysis. The team applied the same protocol six months later to validate the cardiology fix.

## Methodological notes

- Unmoderated worked here because we had a tight hypothesis and needed comparable metrics. Moderated would have given richer "why" data but slower delivery and noisier conversion estimates.
- The 90-participant sample size came from a power calculation targeting a 12-point completion-rate difference at alpha=0.05.
- Prior research saved 1-2 weeks of discovery; the cascade for this study would have routed differently if we'd been starting cold.
