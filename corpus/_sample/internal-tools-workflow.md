# Case: Internal tools workflow exploration (fictional)

**Note:** This is a fabricated case story used as sample content for the uxr-agent-template. It is not based on a real organization or project.

## Situation

A logistics company's operations team was complaining loudly about their dispatch tool. Engineering had a redesign queued, but the team couldn't agree on what was wrong with the current version. Multiple stakeholders had multiple theories. There was no prior research; the tool had been built internally five years earlier and never user-tested.

## Task

Figure out what the actual problem was before any redesign. The PM had three weeks of calendar before next-quarter planning and no stimulus material — just the live tool and access to the operations team.

## Action

Routed to an Explore / Direction cascade. Recommended a time-boxed spike: three days of ethnographic observation across two dispatch shifts, two locations, paired with open-ended interviews scheduled for each operator's natural break.

Observation protocol: shadow each operator for one full shift, capture screen interactions and verbal commentary, log every workaround we noticed (anything where the operator did something outside the tool to get a job done — sticky notes on the monitor, second-screen spreadsheets, calls to colleagues). Interviews focused on "what do you actually do during a shift" rather than "what's wrong with the tool" so we got behavior rather than complaints.

## Result

Six operators observed, ~28 hours of shift time. The dispatch tool itself wasn't the primary friction — the friction was the tool's *boundary* with three other systems (CRM for customer details, a separate carrier-availability lookup, and the company's CRM-of-record for SLA terms). Operators kept four browser windows open simultaneously and had a consistent workaround: a personal Excel sheet with copy-pasted data from all four systems, refreshed manually every shift start.

The PM's redesign proposal had been scoped to the dispatch tool itself. The actual problem was integration. We re-scoped the redesign to focus on a unified shift-start view that pulled from the three adjacent systems on dispatch tool launch.

The spike took 14 days end-to-end (3 days of observation, 4 days of analysis, 7 days of synthesis + readout) and reframed a quarter of engineering work. Without it, the team would have shipped a polished version of the wrong tool.

## Methodological notes

- Spike was the right routing: capabilities were "nothing yet — just the idea" of a redesign, but Q5 was clear (alignment on direction needed for next-quarter planning), so deny didn't fire. The cascade routed correctly to a time-boxed exploratory study.
- Ethnographic observation produced findings no interview-only protocol would have surfaced. The Excel workaround in particular came from watching operators, not asking them — they didn't think of it as a workaround anymore, just "what they do."
- The PM's reframe was the highest-leverage outcome of the study. Confirming a redesign hypothesis would have produced incremental improvement; reframing it pre-spec produced a substantively different deliverable.
