# Case: B2B SaaS dashboard quantitative measurement (fictional)

**Note:** This is a fabricated case story used as sample content for the uxr-agent-template. It is not based on a real organization or project.

## Situation

A B2B sales-enablement SaaS had launched a new analytics dashboard six weeks earlier. Customer success was reporting "people seem to like it" anecdotally, but the VP of Product wanted hard numbers before greenlighting the next phase of dashboard work. Specifically: which segments were getting value, which were not, and what predicted retention through the 90-day mark.

## Task

Quantify dashboard adoption and its correlation with retention across customer segments. The team had a live product, a year of analytics data, prior research from the discovery phase (n=24 interviews, three usability rounds, a quant survey n=156), and SUS scores from launch. The decision posture was clear: certainty, not direction.

## Action

Routed to a Measure / Certainty cascade. Recommended analytics funnel analysis combined with longitudinal SUS/NPS tracking, plus a focused benchmark against three competitor dashboards we'd profiled in the prior research.

Analysis structure: pulled 8 weeks of post-launch usage data (n=2,840 active customers), segmented by company size (SMB / mid-market / enterprise) and primary use case (forecasting / pipeline review / coaching). Computed funnel completion at four key dashboard interactions (filter, drill-down, export, share). Joined to retention curve at 30, 60, 90 days. Re-ran SUS quarterly with a panel of 200 active users.

## Result

Pipeline-review users showed 72 percent completion through the four-interaction funnel; coaching users showed 31 percent. Coaching users had a 90-day retention of 58 percent vs. 84 percent for pipeline-review. The benchmark against competitors put us at parity on filter and drill-down, behind on export, ahead on share.

The actionable finding: coaching users were dropping out at the drill-down step specifically, and the drill-down design assumed a forecasting mental model that coaches didn't share. We hadn't caught this in the discovery phase because coaching users were under-represented in the original recruit (3 of 24 interviews).

Recommended: a focused redesign of the drill-down pattern for coaching workflows, plus a recruit balance fix for the next discovery round. The team shipped the drill-down redesign in the next sprint cycle. Coaching retention at 90 days moved to 71 percent over the following quarter.

## Methodological notes

- Take-and-run was the right routing here: prior research existed, metrics were the decision-maker's currency, and the team had a year of analytics already. A new generative round would have been redundant; a survey would have measured the wrong thing.
- The benchmarking work was lighter than a full competitive audit — we already had the competitor profiles from prior research; this was just an explicit re-comparison against current performance.
- The biggest methodological lesson was about recruit balance. Three coaching users out of 24 was statistically reasonable but practically wrong for a product with 30+ percent coaching customers.
