# Demo Day Checklist

## Night before
- [ ] Laptop charged to 100%; pack the charger.
- [ ] Run `python run.py`, ask one question, open the Continuity report. Everything works.
- [ ] GitHub repo is **public** before the **10:00 AM, October 10** deadline.
- [ ] Want a clean slate? Stop the app and delete the `vault` folder (it re-syncs on start).

## 10 minutes before you present
- [ ] Plug in the charger and turn off battery saver.
- [ ] Close heavy apps: extra browser tabs, Docker, video calls, OneDrive/Dropbox syncing.
- [ ] Double-click **start-demo** on the Desktop (or `python run.py`).
- [ ] Wait for the terminal line *"Model llama3.2:3b warmed up … Ready for questions."*
- [ ] Warm-up question: **"Which clients owe us money?"**
- [ ] On **Connections**, make sure every demo switch is on **Up**. Refresh the page so the stage starts clean.
- [ ] Zoom the browser to 110–125% so the room can read it.
- [ ] Know where your Wi-Fi toggle is (taskbar / menu bar).

## On stage (5 minutes)
1. Connections: 6 platforms, about 200 records saved locally.
2. Ask: "Why hasn't Thames Fintech paid?" Click a citation to show the original Zoho data.
3. Zoho CRM → **Shut down**, Zoho Projects → **Outage**. The banner switches to Continuity mode.
4. Wi-Fi **OFF**. Ask "Which clients owe us money?"
5. Continuity report → *What needs attention now?*
6. Vault → search "property listings" → **Mark done**. Then open INV-2042 → *Draft a payment reminder* → queue it.
7. Wi-Fi **ON**, Zoho Projects → **Up**. Pending changes show **Pushed**.
8. AI import → *Try a sample Pipedrive export* → Import. Then **Export everything**.

## Backups
- **Venue Wi-Fi is flaky, or the Wi-Fi toggle is hard to reach:** use **Simulate Wi-Fi off** in the top bar. It behaves exactly the same.
- **Ollama isn't responding** (red banner "The local AI (Ollama) isn't running"):
  1. Open the Ollama app (Windows: Start menu → Ollama; macOS: Applications → Ollama), or run `ollama serve`.
  2. http://localhost:11434 should say "Ollama is running".
  3. `ollama list` should show `llama3.2:3b` and `nomic-embed-text`. If not: `ollama pull llama3.2:3b`.
  4. Ask again; no need to restart the app. The vault, Connections, report facts and export all keep working without the AI.
- **Answers are slow:** close other apps and wait for the warm-up. Last resort: set `{"llm_model": "llama3.2:1b"}` in `config.local.json` and restart.
- **Browser can't connect:** the app isn't running, so double-click start-demo again. If port 8000 is busy, the terminal prints the new address.
- **Anything else:** open http://localhost:8000/health.
