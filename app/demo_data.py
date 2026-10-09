"""Demo business: Web Innovation Experts, a digital marketing agency (clients and people below are fictional sample data).
Generates each platform's data in that platform's own API format (Zoho CRM, Zoho Projects, Zoho Books,
HubSpot, ClickUp, BambooHR). Dates are relative to today so there is always work due today and overdue.
All companies, people, emails and phone numbers are fictional."""
import random
from datetime import date, datetime, time, timedelta, timezone

EMPLOYEES = [  # name, title, department, location
    ("Ana Reyes", "Account Director", "Client Services", "Manila, PH"),
    ("Paolo Santos", "Project Manager", "Delivery", "Manila, PH"),
    ("Jessa Lim", "Senior Designer", "Creative", "Cebu, PH"),
    ("Migs Cruz", "Web Developer", "Engineering", "Cebu, PH"),
    ("Carlo Mendoza", "Paid Media Specialist", "Performance", "Manila, PH"),
    ("Liam Carter", "Head of Growth", "Leadership", "Sydney, AU"),
    ("Priya Nair", "SEO Lead", "Performance", "Melbourne, AU"),
    ("Grace Tan", "Content Writer", "Creative", "Singapore, SG"),
    ("Ben Walsh", "Finance Manager", "Finance", "Sydney, AU"),
    ("Sofia Garcia", "HR & Operations Manager", "Operations", "Manila, PH"),
    ("Kenji Watanabe", "Full-stack Developer", "Engineering", "Remote, JP"),
    ("Rhea Bautista", "Social Media Manager", "Creative", "Davao, PH"),
]

ACCOUNTS = [  # name, industry, city, country, owner, description
    ("Harbourline Realty", "Real Estate", "Sydney", "Australia", "Ana Reyes",
     "Property group with 12 offices. Website rebuild plus SEO retainer. Wants a weekly report every Monday."),
    ("Koala Coast Tours", "Travel", "Gold Coast", "Australia", "Liam Carter",
     "Tour operator. Paid social for peak season. Very price sensitive."),
    ("Brightwell Dental Group", "Healthcare", "Austin", "United States", "Ana Reyes",
     "Dental chain, 8 clinics. Local SEO and Google Ads. Compliance review needed for all ad copy."),
    ("Maple & Rye Bakery", "Food & Beverage", "Toronto", "Canada", "Paolo Santos",
     "Bakery brand with online orders. Shopify site and social content."),
    ("Thames Fintech", "Financial Services", "London", "United Kingdom", "Liam Carter",
     "Payments startup. Brand refresh and product launch campaign. Finance team requires a PO number on every invoice."),
    ("Lumen Solar Co.", "Energy", "Phoenix", "United States", "Ana Reyes",
     "Residential solar installer. Lead generation campaigns; pays on time."),
    ("Kampong Kitchen", "Hospitality", "Singapore", "Singapore", "Grace Tan",
     "Restaurant group. Content and influencer campaigns."),
    ("Manila Bay Logistics", "Logistics", "Manila", "Philippines", "Paolo Santos",
     "Freight forwarder. Corporate website and LinkedIn. Approvals go through the CEO."),
    ("Aurora Skincare", "Beauty", "Melbourne", "Australia", "Rhea Bautista",
     "DTC skincare brand. Social, paid ads, email flows. Fast-growing, high expectations."),
    ("Redgum Constructions", "Construction", "Brisbane", "Australia", "Liam Carter",
     "Builder. Website and project gallery. Cash-flow issues this quarter."),
    ("Pacific Pet Supplies", "Retail", "Auckland", "New Zealand", "Carlo Mendoza",
     "Pet store chain. Google Shopping and Meta ads."),
    ("Golden Gate Legal", "Legal", "San Francisco", "United States", "Ana Reyes",
     "Law firm. Website maintenance retainer; formal communication only."),
    ("Bayside Fitness Studios", "Fitness", "Perth", "Australia", "Rhea Bautista",
     "Gym franchise. Member acquisition campaigns and social content."),
    ("Nordic Home Interiors", "Retail", "Manchester", "United Kingdom", "Paolo Santos",
     "Furniture e-commerce. Site speed and conversion work."),
    ("Cebu Coffee Roasters", "Food & Beverage", "Cebu City", "Philippines", "Jessa Lim",
     "Specialty coffee. Packaging design and Instagram."),
    ("Summit Insurance Brokers", "Insurance", "Adelaide", "Australia", "Liam Carter",
     "Insurance brokerage. New prospect; proposal for SEO + content sent."),
]

FIRST = ["Olivia", "James", "Mia", "Noah", "Chloe", "Ethan", "Hannah", "Lucas", "Isla", "Jack", "Zara", "Ryan",
         "Emily", "Daniel", "Sophie", "Marcus", "Aisha", "Tom", "Leah", "Oscar", "Nina", "Sam", "Ivy", "Raj"]
LAST = ["Mitchell", "Nguyen", "Brooks", "Patel", "Hughes", "Kim", "Fraser", "Lopez", "Wright", "Chen", "Doyle",
        "Murphy", "Singh", "Turner", "Ward", "Ramos", "Fischer", "Okafor", "Bennett", "Hayes"]
TITLES = ["Marketing Manager", "CEO", "Founder", "Operations Director", "Head of Marketing", "Finance Officer"]

DEALS = [  # account index, name, amount AUD, stage, close offset
    (0, "SEO Retainer 2027", 48000, "Negotiation/Review", 6), (1, "Summer Paid Social", 18000, "Proposal/Price Quote", 12),
    (2, "Google Ads Expansion", 36000, "Qualification", 30), (4, "Product Launch Campaign", 95000, "Negotiation/Review", 3),
    (5, "Lead Gen Q1", 27000, "Closed Won", -10), (6, "Influencer Program", 15000, "Proposal/Price Quote", 20),
    (8, "Email Flows Rebuild", 22000, "Closed Won", -4), (9, "Gallery Phase 2", 14000, "Closed Lost", -15),
    (10, "Shopping Feed Optimisation", 12500, "Qualification", 25), (12, "Franchise Launch Ads", 40000, "Negotiation/Review", 9),
    (13, "Conversion Rate Sprint", 19000, "Proposal/Price Quote", 14), (15, "SEO + Content Proposal", 52000, "Proposal/Price Quote", 5),
    (3, "Holiday Campaign", 9800, "Qualification", 35), (14, "Packaging Range 2", 11000, "Closed Won", -20),
]

NOTES = [  # account index, title, content, days ago
    (4, "Invoice blocked", "Thames Fintech's finance team rejected INV-2042 because it had no PO number. Their PO is PO-88213. Re-issue the invoice with the PO number and they pay within 7 days."),
    (0, "Weekly reporting", "Harbourline wants the SEO and traffic report every Monday before 10 AM Sydney time. CEO reads it. Keep it to one page."),
    (9, "Payment plan agreed", "Redgum Constructions is short on cash this quarter. Agreed to split the overdue invoice into two payments, the second one at month end."),
    (2, "Ad compliance", "All Brightwell Dental ad copy must be reviewed by their compliance officer before launch. Allow 3 business days."),
    (8, "Escalation", "Aurora Skincare complained that the last email campaign went out with a broken discount code. Fixed within an hour; offered a free A/B test as goodwill."),
    (7, "Approval process", "Manila Bay Logistics: every design must be approved by the CEO, Mr. Ramos. He is travelling until next week, so homepage approval will be late."),
    (15, "Proposal call", "Summit Insurance liked the SEO proposal but asked for case studies from other insurance or finance clients. Send the Thames Fintech case study."),
    (12, "Franchise rollout", "Bayside Fitness is opening 4 new studios. They want launch ads live 2 weeks before each opening."),
    (11, "Contract terms", "Golden Gate Legal retainer: 20 hours per month, unused hours do not roll over. Invoices net 15."),
    (1, "Budget concern", "Koala Coast Tours asked to cut the paid social budget by 20% if bookings don't improve by the end of the month."),
    (5, "Happy client", "Lumen Solar renewed lead gen; cost per lead down 31% vs last quarter. Good case study candidate."),
    (13, "Site speed", "Nordic Home Interiors mobile load time is 6.2s. Target under 2.5s before Black Friday."),
]

PROJECTS = [  # account index, name, owner, end offset, status, template
    (0, "Harbourline Realty Website Rebuild", "Paolo Santos", 4, "active", "web"),
    (0, "Harbourline SEO Retainer", "Priya Nair", 21, "active", "seo"),
    (4, "Thames Fintech Brand Refresh", "Jessa Lim", 10, "active", "brand"),
    (8, "Aurora Skincare Always-On Social", "Rhea Bautista", 30, "active", "social"),
    (7, "Manila Bay Logistics Corporate Site", "Migs Cruz", 6, "active", "web"),
    (2, "Brightwell Dental Local SEO", "Priya Nair", 14, "active", "seo"),
    (12, "Bayside Fitness Launch Ads", "Carlo Mendoza", 7, "active", "ads"),
    (9, "Redgum Constructions Project Gallery", "Kenji Watanabe", 2, "on hold", "web"),
    (13, "Nordic Home Speed & CRO Sprint", "Kenji Watanabe", 12, "active", "web"),
    (14, "Cebu Coffee Packaging Range", "Jessa Lim", -12, "completed", "brand"),
]
TASK_TEMPLATES = {
    "web": [("Discovery workshop", "Delivery"), ("Sitemap and wireframes", "Creative"), ("UI design: homepage", "Creative"),
            ("Build CMS templates", "Engineering"), ("QA and launch checklist", "Engineering")],
    "seo": [("Technical SEO audit", "Performance"), ("Keyword research", "Performance"), ("On-page fixes batch", "Engineering"),
            ("Monthly SEO report", "Performance")],
    "brand": [("Brand workshop", "Creative"), ("Logo concepts", "Creative"), ("Brand guidelines document", "Creative"),
              ("Launch assets", "Creative")],
    "social": [("Content calendar", "Creative"), ("Photo shoot", "Creative"), ("Community management", "Creative"),
               ("Monthly social report", "Creative")],
    "ads": [("Campaign structure", "Performance"), ("Ad creative set", "Creative"), ("Tracking and pixels", "Engineering"),
            ("Launch and optimise", "Performance")],
}
DEPT_PEOPLE = {"Delivery": ["Paolo Santos"], "Creative": ["Jessa Lim", "Grace Tan", "Rhea Bautista"],
               "Engineering": ["Migs Cruz", "Kenji Watanabe"], "Performance": ["Priya Nair", "Carlo Mendoza"]}

LEADS = [  # first, last, company, stage, message
    ("Harper", "Quinn", "Seaside Dental Care", "salesqualifiedlead", "Looking for an agency to run Google Ads for 3 clinics in Brisbane. Budget AUD 6k/month."),
    ("Diego", "Alvarez", "Verde Coffee Bar", "lead", "Downloaded the 'Local SEO checklist' ebook."),
    ("Mei", "Watanabe", "Kumo Architecture", "marketingqualifiedlead", "Wants a portfolio website with a project gallery before their awards entry."),
    ("Callum", "Reid", "Highland Outdoor Gear", "opportunity", "Requested a proposal for Shopify migration plus paid social. Decision in 2 weeks."),
    ("Fatima", "Rahman", "Crescent Accounting", "lead", "Attended our webinar on LinkedIn ads for professional services."),
    ("Jonah", "Price", "Prime Auto Detailing", "marketingqualifiedlead", "Asked about pricing for a monthly social media package."),
    ("Lara", "Costa", "Bella Bridal Studio", "salesqualifiedlead", "Needs Instagram and TikTok content before wedding season; wants a call this week."),
    ("Nathan", "Ellis", "Ellis Family Law", "lead", "Filled in the contact form: website is outdated and not mobile friendly."),
    ("Yuki", "Sato", "Sakura Language School", "opportunity", "Proposal sent for student enrolment campaign in PH and VN. Follow up overdue."),
    ("Owen", "Grant", "GreenLeaf Landscaping", "lead", "Clicked pricing page three times this week."),
    ("Bianca", "Ferreira", "Studio B Pilates", "marketingqualifiedlead", "Interested in the same launch-ads package as Bayside Fitness."),
    ("Ahmed", "Khan", "Swift Courier Co.", "lead", "Asked whether we work with logistics companies; referred by Manila Bay Logistics."),
]

CLICKUP_TASKS = [  # name, assignee, status, due offset, tags, list
    ("Update agency case studies page", "Grace Tan", "in progress", 2, ["website"], "Sprint 42"),
    ("Renew SSL certificates for client sites", "Migs Cruz", "to do", 0, ["ops", "urgent"], "Sprint 42"),
    ("Migrate 6 client sites to new hosting", "Kenji Watanabe", "in progress", 5, ["ops"], "Sprint 42"),
    ("Prepare Q4 board report", "Ben Walsh", "to do", 3, ["finance"], "Sprint 42"),
    ("Chase overdue invoices (top 5)", "Ben Walsh", "in progress", 0, ["finance", "urgent"], "Sprint 42"),
    ("Onboard new designer", "Sofia Garcia", "to do", 4, ["hr"], "Sprint 42"),
    ("Quarterly performance reviews", "Sofia Garcia", "to do", 12, ["hr"], "Backlog"),
    ("Pitch deck for Summit Insurance", "Liam Carter", "review", 1, ["sales"], "Sprint 42"),
    ("Record agency showreel", "Rhea Bautista", "to do", 9, ["marketing"], "Backlog"),
    ("Audit ad accounts access (offboarding)", "Carlo Mendoza", "to do", -2, ["security"], "Sprint 41"),
    ("Write 'Local SEO' blog series", "Priya Nair", "in progress", 6, ["content"], "Sprint 42"),
    ("Fix broken links on agency site", "Migs Cruz", "complete", -3, ["website"], "Sprint 41"),
    ("Update proposal templates", "Ana Reyes", "review", 1, ["sales"], "Sprint 42"),
    ("Backup client brand assets to NAS", "Kenji Watanabe", "to do", -1, ["ops"], "Sprint 41"),
    ("Plan team offsite in Bohol", "Sofia Garcia", "in progress", 20, ["hr"], "Backlog"),
    ("Review contractor invoices", "Ben Walsh", "to do", 2, ["finance"], "Sprint 42"),
]


def zid(n: int) -> str:
    return f"48768760000{n:08d}"


def generate(today: date | None = None) -> dict:
    """Returns {platform: {resource: [native records]}}."""
    t = today or date.today()
    d = lambda off: (t + timedelta(days=off)).isoformat()
    ts = lambda off: datetime.combine(t + timedelta(days=off), time(9, 0), tzinfo=timezone.utc).isoformat()
    rng = random.Random(42)
    emp_ids = {e[0]: 40100 + i for i, e in enumerate(EMPLOYEES)}

    accounts = []
    for i, (name, ind, city, country, owner, desc) in enumerate(ACCOUNTS):
        slug = "".join(ch for ch in name.lower() if ch.isalnum())[:18]
        accounts.append({"id": zid(1000 + i), "Account_Name": name, "Industry": ind, "Billing_City": city,
                         "Billing_Country": country, "Website": f"https://www.{slug}.example",
                         "Phone": f"+{rng.randint(1, 99)} {rng.randint(200, 999)} {rng.randint(100, 999)} {rng.randint(1000, 9999)}",
                         "Owner": {"name": owner, "id": str(emp_ids[owner])}, "Description": desc,
                         "Modified_Time": ts(-rng.randint(0, 20))})
    contacts = []
    for i, a in enumerate(accounts):
        for j in range(2):
            fn, ln = FIRST[(i * 2 + j) % len(FIRST)], LAST[(i * 3 + j * 7) % len(LAST)]
            dom = a["Website"].split("www.")[1]
            contacts.append({"id": zid(2000 + i * 2 + j), "First_Name": fn, "Last_Name": ln,
                             "Email": f"{fn.lower()}.{ln.lower()}@{dom}", "Title": TITLES[(i + j) % len(TITLES)],
                             "Phone": f"+{rng.randint(1, 99)} 4{rng.randint(10, 99)} {rng.randint(100, 999)} {rng.randint(100, 999)}",
                             "Account_Name": {"name": a["Account_Name"], "id": a["id"]},
                             "Modified_Time": ts(-rng.randint(0, 30))})
    deals = []
    for i, (ai, name, amt, stage, off) in enumerate(DEALS):
        a = accounts[ai]
        deals.append({"id": zid(3000 + i), "Deal_Name": f"{a['Account_Name']}: {name}", "Amount": amt, "Stage": stage,
                      "Closing_Date": d(off), "Account_Name": {"name": a["Account_Name"], "id": a["id"]},
                      "Owner": a["Owner"], "Modified_Time": ts(-rng.randint(0, 10))})
    notes = [{"id": zid(4000 + i), "Note_Title": title, "Note_Content": content,
              "Parent_Id": {"name": accounts[ai]["Account_Name"], "id": accounts[ai]["id"]}, "se_module": "Accounts",
              "Created_Time": ts(-ago)} for i, (ai, title, content, ago) in enumerate(
        [(n[0], n[1], n[2], (k * 3) % 14) for k, n in enumerate(NOTES)])]

    projects, tasks = [], {}
    for i, (ai, name, owner, end, status, tpl) in enumerate(PROJECTS):
        pid = f"17{i:02d}000000{i:04d}"
        projects.append({"id": pid, "name": name, "owner_name": owner, "status": status, "end_date": d(end),
                         "start_date": d(end - 45), "description": f"Client: {accounts[ai]['Account_Name']}",
                         "client": accounts[ai]["Account_Name"], "last_updated_time": ts(-rng.randint(0, 6))})
        steps = TASK_TEMPLATES[tpl]
        tlist = []
        for k, (tname, dept) in enumerate(steps):
            # spread deadlines across the project; earlier steps closed for active projects
            due = end - (len(steps) - 1 - k) * 6
            closed = status == "completed" or due < 0
            st = "Closed" if closed else ("In Progress" if due <= 3 else "Open")
            who = owner if dept == "Delivery" else DEPT_PEOPLE[dept][(i + k) % len(DEPT_PEOPLE[dept])]
            tlist.append({"id": f"{pid}{k:02d}", "name": tname, "status": {"name": st},
                          "details": {"owners": [{"name": who}]}, "end_date": d(due),
                          "priority": "High" if 0 <= due <= 2 else ("Medium" if due < 10 else "Low"),
                          "description": f"{tname} for {name}.", "last_updated_time": ts(-rng.randint(0, 5))})
        tasks[pid] = tlist
    # pin a few demo-critical tasks
    tasks[projects[0]["id"]][3].update(name="Build CMS templates (property listings)", end_date=d(0), status={"name": "In Progress"})
    tasks[projects[4]["id"]][2].update(name="UI design: homepage (waiting on CEO approval)", end_date=d(-3), status={"name": "In Progress"})

    invoices = []
    plan = [  # account index, amount, issue offset, due offset, paid
        (0, 18500, -45, -15, True), (0, 9200, -14, 0, False), (1, 6400, -40, -10, False), (2, 12800, -60, -30, True),
        (2, 12800, -30, 0, False), (3, 4200, -20, 10, False), (4, 38000, -35, -12, False), (4, 21000, -70, -40, True),
        (5, 9000, -40, -10, True), (5, 9000, -10, 20, False), (6, 7500, -25, -5, False), (7, 15600, -50, -20, False),
        (8, 11000, -15, 15, False), (8, 11000, -45, -15, True), (9, 22400, -50, -21, False), (10, 5300, -12, 18, False),
        (11, 6000, -20, -5, False), (11, 6000, -50, -35, True), (12, 14200, -8, 22, False), (13, 8900, -33, -3, False),
        (14, 3600, -70, -40, True), (14, 2800, -5, 25, False), (0, 4800, -3, 27, False), (6, 7500, -55, -35, True),
        (9, 6000, -90, -60, True), (12, 14200, -38, -8, True), (13, 8900, -63, -33, True), (3, 4200, -50, -20, True),
        (10, 5300, -42, -12, True), (1, 6400, -70, -40, True),
    ]
    for i, (ai, amt, iss, due, paid) in enumerate(plan):
        a = accounts[ai]
        status = "paid" if paid else ("overdue" if due < 0 else "sent")
        invoices.append({"invoice_id": f"9300000{i:05d}", "invoice_number": f"INV-{2031 + i}", "customer_name": a["Account_Name"],
                         "customer_id": a["id"], "date": d(iss), "due_date": d(due), "total": amt,
                         "balance": 0 if paid else amt, "currency_code": "AUD", "status": status,
                         "reference_number": "", "last_modified_time": ts(min(0, iss + 2))})
    # INV-2042 is the Thames Fintech invoice blocked by the missing PO (see note)
    for inv in invoices:
        if inv["customer_name"] == "Thames Fintech" and inv["status"] == "overdue":
            inv["invoice_number"], invoices[11]["invoice_number"] = "INV-2042", inv["invoice_number"]
            break

    hubspot = [{"id": str(70001 + i), "properties": {
        "firstname": fn, "lastname": ln, "email": f"{fn.lower()}@{''.join(c for c in comp.lower() if c.isalnum())}.example",
        "company": comp, "lifecyclestage": stage, "message": msg,
        "hs_lead_status": "IN_PROGRESS" if stage in ("salesqualifiedlead", "opportunity") else "NEW",
        "createdate": ts(-rng.randint(1, 25)), "lastmodifieddate": ts(-rng.randint(0, 5)),
        "hubspot_owner": ["Liam Carter", "Ana Reyes"][i % 2]}} for i, (fn, ln, comp, stage, msg) in enumerate(LEADS)]

    clickup = []
    for i, (name, who, status, due, tags, lst) in enumerate(CLICKUP_TASKS):
        due_ms = int(datetime.combine(t + timedelta(days=due), time(17, 0), tzinfo=timezone.utc).timestamp() * 1000)
        clickup.append({"id": f"86c{i:05x}", "name": name, "status": {"status": status},
                        "assignees": [{"username": who}], "due_date": str(due_ms),
                        "tags": [{"name": tg} for tg in tags], "list": {"name": lst},
                        "date_updated": str(due_ms - 86400000 * 3)})

    bamboo = [{"id": str(emp_ids[n]), "displayName": n, "jobTitle": title, "department": dept, "location": loc,
               "workEmail": f"{n.split()[0].lower()}@webinnovationexperts.example",
               "mobilePhone": f"+63 9{rng.randint(10, 99)} {rng.randint(100, 999)} {rng.randint(1000, 9999)}",
               "hireDate": d(-rng.randint(200, 2400))} for n, title, dept, loc in EMPLOYEES]

    return {
        "zoho_crm": {"Accounts": accounts, "Contacts": contacts, "Deals": deals, "Notes": notes},
        "zoho_projects": {"projects": projects, "tasks": tasks},
        "zoho_books": {"invoices": invoices},
        "hubspot": {"contacts": hubspot},
        "clickup": {"tasks": clickup},
        "bamboohr": {"employees": bamboo},
    }
