# _sample/

These are fictional case stories, written specifically to give a freshly-forked deployment something to answer questions about before the practitioner has ingested their real content. They are not based on real organizations, people, or events.

**Replace these before you go live.** The agent will work fine ingesting them, but recruiters asking about your portfolio expect to see your work, not these.

Each case is tuned to exercise a specific feature path in the agent so that fresh deploys can validate the pipeline end-to-end:

| File | Intent fork | What it demonstrates |
|---|---|---|
| `healthcare-scheduling-redesign.md` | validate / certainty | Unmoderated task-based testing scenario. Wizard asks "Should we redesign the booking flow?" → routing=next_sprint. |
| `fintech-onboarding-flow.md` | define / direction | Co-creation workshop scenario. Mid-cascade preview shows productive divergence between PM/Designer/Engineer. |
| `b2b-saas-dashboard-usability.md` | measure / certainty | Analytics funnel + benchmarking. Triggers the take_and_run routing path. |
| `internal-tools-workflow.md` | explore / direction | Ethnographic observation. Triggers the spike routing path. |
| `mobile-app-retention-measurement.md` | mixed (explore + measure) | Phased Discovery → Validation. Exercises the mixed-intent recommendation. |

To delete them after ingesting your real content:

```bash
rm -rf corpus/_sample/
git add corpus/
git commit -m "Replace sample corpus with my own case stories"
git push
# Then trigger re-ingest from /admin
```
