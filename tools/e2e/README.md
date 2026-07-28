# End-to-end harness — drive the deployed product in a real browser

Unit tests prove the parts; these prove the shipped thing. Every defect in the 2026-07-28
round was found here and none of them by the suite: the deployed page said "Done — your
dashboard is ready" over an empty table, and 761 green tests had nothing to say about it.

```bash
export SV_EMAIL=you@example.org

# 1. a real Chrome window, all five wizard steps, screenshots at each
"/c/Program Files/Google/Chrome/Application/chrome.exe" \
  --remote-debugging-port=9222 --user-data-dir=/tmp/cprof --new-window \
  --window-size=1500,950 https://supervisorly.web.app/ &
node tools/e2e/drive_wizard.js "structural engineering" ./shots

# 2. open a finished dashboard and click a professor; reads the modal back as JSON
node tools/e2e/open_professor.js <jobId> engineering ./shots

# 3. many subjects at once, API-only — the coverage check
node tools/e2e/sweep_subjects.js sweep.json
```

## Things these scripts learned the hard way

**Scripted `.click()` is not a trusted gesture.** An earlier round reported the working
"Open dashboard" button as broken because of it. Every meaningful click here goes through
`Input.dispatchMouseEvent` at the element's centre.

**The page deliberately remembers an unfinished job**, so a second run does not start at
step 1 — it restores the last one. `drive_wizard.js` clears storage and reloads first, then
prints the entry step, because a fresh-visitor test has to actually be a fresh visitor. The
first version of it failed with "timeout waiting for step 2" for exactly this reason.

**`country` is on step 1, not step 4.** Filling it late is how the blank-country defect was
found — the scan was accepted, a worker ran, and the student was told their dashboard was
ready over nothing.

**Do not map the raw field.** `sweep_subjects.js` expands first, then maps each phrasing and
merges (what the page does, D-070). Mapping the raw field alone sends an EMPTY topic filter,
and the run still looks healthy: the first sweep returned the same 1081 professors for both
"sport" and "medicine" and I nearly reported it as five passing subjects. It also hides that
"cardiology" maps to nothing on its own — OpenAlex has no topic by that name, which is the
case the expand step exists to rescue.

**Check the names, not just the counts.** Two subjects returning identical top names is the
tell that a filter is empty. Counts alone looked fine.

## Cost

`sweep_subjects.js` starts one scan per subject and the §5.2 cap is 5 scans/hour per IP. A
five-subject sweep uses the whole hour's budget. Lifting the cap for a test pass means
editing `firebase/_core.py` and deploying — if you do, revert it the same day; commit
`a6fd713` and its revert `2e80d7d` are the worked example.
