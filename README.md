# All Is Well AI
**Your business brain, on your own computer.**

Built by Web Innovation Experts. A local AI agent that connects to the cloud platforms a business runs on (Zoho CRM, Zoho Projects, Zoho Books, HubSpot, ClickUp, BambooHR), keeps a complete, versioned copy of everything in a **vault on the company's own computer**, and lets the team keep working, with AI, when those platforms go down, lock them out, or shut down for good.

## The problem
Almost every company now runs on third-party SaaS: the CRM holds the clients, the project tool holds the sprints, the accounting tool holds the invoices, the HR tool holds the people. Remote teams depend on them completely. But:
- **Platforms go down.** Regional cloud outages take whole teams offline for hours.
- **Platforms disappear or lock you out.** Vendors get acquired, discontinue products, change pricing, or suspend accounts. "If Zoho shut down tomorrow, where are our clients, projects and invoices?" Most businesses have no answer.
- **Data is scattered.** Answering "which clients owe us money and who do I call?" means logging in to three tools.

## The solution
1. **Connect**: the agent pulls every record from each platform over its API, every minute.
2. **Keep**: everything lands in one local vault (SQLite on the company's computer), with each platform's original JSON and a version history of every change.
3. **Ask**: a local LLM answers questions across all platforms with clickable citations, using local embeddings for search. No data is sent to a cloud AI.
4. **Keep working**: when a platform is down (or the internet is), the team still marks tasks done, adds notes and drafts emails. Changes apply in the vault immediately and **push back automatically** when the platform returns.
5. **Leave anytime**: one click exports everything as CSV + original JSON, so a vendor shutdown is never a data loss.
6. **Bring in anything**: for tools without a connector, drop in their export file; the **local AI maps the unknown columns** onto the vault.

## Why it has to be local AI
| | Cloud-only AI | All Is Well AI |
|---|---|---|
| Platform or internet outage | AI and data both gone | Vault + AI keep working on the laptop |
| Vendor shuts down / locks account | Data at the vendor's mercy | Full copy already on your computer |
| Privacy | Client, invoice and HR data sent to a third-party AI | Never leaves the device |
| Cost | Pay per query, per seat | No per-query cost |
| Speed | Network round-trips | Answers from local disk + local model |

---

## Run it yourself

### Requirements
- Windows 10/11, macOS 12+, or 64-bit Linux
- 8 GB RAM minimum (16 GB recommended)
- About 4 GB free disk (llama3.2:3b ≈ 2.0 GB, nomic-embed-text ≈ 0.3 GB, plus Python packages)
- Python 3.11 or newer, Git, Ollama
- Internet only for the one-time install

### 1. Install the prerequisites
**Windows** (PowerShell):
```powershell
winget install -e --id Ollama.Ollama; winget install -e --id Git.Git; winget install -e --id Python.Python.3.12
```
Then close and reopen PowerShell.

**macOS**: install Ollama from https://ollama.com/download (open it once) and Python 3.12 from https://www.python.org/downloads/. Git comes with the Xcode tools (`git --version` prompts to install).

**Linux**:
```bash
sudo apt install -y python3 python3-venv git
curl -fsSL https://ollama.com/install.sh | sh
```

### 2. Get the code and set up (one command)
```bash
git clone https://github.com/Jeanwel/all-is-well-ai.git
cd all-is-well-ai
python scripts/setup.py          # macOS/Linux: python3 scripts/setup.py   Windows: py scripts\setup.py
```
Setup creates `.venv`, installs pinned dependencies, checks your RAM and picks the model, starts Ollama, downloads and tests both models, runs a first sync of all six platforms into the vault, builds the AI index, and puts a **start-demo** launcher on your Desktop.

### 3. Run (one command)
```bash
python run.py                    # macOS/Linux: python3 run.py   Windows: py run.py
```
Open **http://localhost:8000** (it opens automatically). Or double-click **start-demo** on the Desktop.

### Test it offline
1. Wait for the terminal to print *"Model … warmed up"*.
2. **Turn Wi-Fi off.** Within about 5 seconds the top bar says *No internet* and the banner explains you're running from the vault.
3. Ask the questions below, open **Continuity report → What needs attention now?**, mark a task done, and draft an email. Everything works.
4. Turn Wi-Fi back on. The queued email and changes move to **Pushed** on their own.

To test a single platform failing instead, use **Connections → Demo switch → Outage / Shut down**.

### Sample questions
| Question | Expected kind of answer |
|---|---|
| Which clients owe us money? | Overdue invoices with amounts and the total (AUD 104,800), cited |
| Why hasn't Thames Fintech paid? | INV-2042 was rejected for a missing PO number (PO-88213), from the Zoho CRM note |
| What is Migs working on this week? | Migs Cruz's open tasks from Zoho Projects and ClickUp, with due dates |
| What's the status of the Harbourline Realty website? | Project status, today's CMS task, the Monday-report note, open invoices |
| Who is our SEO lead and how do I reach her? | Priya Nair, from BambooHR, with email and mobile |
| What's our office Wi-Fi password? | "I couldn't find that in your vault." (no made-up answers) |

### Run the tests
```bash
.venv/bin/python -m pytest -q         # Windows: .venv\Scripts\python -m pytest -q
```

### Troubleshooting
| Problem | Fix |
|---|---|
| "The local AI (Ollama) isn't running" | Open the Ollama app, or run `ollama serve`. http://localhost:11434 should say "Ollama is running". |
| "AI model not downloaded" | `ollama pull llama3.2:3b` and `ollama pull nomic-embed-text`, or rerun setup. |
| Port 8000 in use | `run.py` picks the next free port and prints it. Or set `AIW_PORT=8080`. |
| First answer is slow | The model loads into memory on first use; `run.py` warms it up, so wait for "warmed up". Close heavy apps. On older laptops set `{"llm_model": "llama3.2:1b"}` in `config.local.json`. |
| `python` not found (Windows) | Use `py` instead of `python`. |
| Start over with fresh data | Stop the app, delete the `vault` folder, start again. |
| Check everything | http://localhost:8000/health |

---

## Demo script (5 minutes)
1. **Connections (online):** six platforms connected, about 200 records in the vault. "This is our agency's Zoho, HubSpot, ClickUp and BambooHR, copied onto this laptop every minute."
2. **Ask:** "Why hasn't Thames Fintech paid?" A cited answer combines the Zoho Books invoice with the Zoho CRM note. Click a chip to show the original Zoho data.
3. **Zoho shuts down:** Connections → Zoho CRM → *Shut down*; Zoho Projects → *Outage*. The banner switches to Continuity mode, and **nothing is lost**.
4. **Turn Wi-Fi OFF live** (backup: *Simulate Wi-Fi off*). Ask "Which clients owe us money?" It is still answered, with no internet and no cloud AI.
5. **Continuity report:** *What needs attention now?* gives today's tasks, overdue money, who to call.
6. **Keep working:** mark "Build CMS templates (property listings)" done; draft a payment reminder for INV-2042. Both are queued in **Pending changes**.
7. **Wi-Fi ON + Zoho Projects Up:** the queued changes push back automatically.
8. **Leave anytime:** AI import of the Pipedrive sample (the local AI maps the columns), then *Export everything*.
