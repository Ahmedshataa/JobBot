# -*- coding: utf-8 -*-
"""Telegram job alert bot: Mostaql + Khamsat (+ Nafezly if reachable).
Needs only Python 3.8+. No pip installs.
Run:  set BOT_TOKEN=xxxx   (Windows)   then   python jobbot.py
"""
import os, re, json, time, html, ssl, sys
import urllib.request, urllib.parse, urllib.error

# ---------- settings you can edit ----------
KEYWORDS = [
    "بوت", "تليجرام", "تيليجرام", "telegram", "bot", "n8n", "اتمتة", "أتمتة", "automation",
    "ذكاء اصطناعي", "ذكاء", "ai", "gpt", "chatgpt", "agent", "python", "بايثون",
    "موقع", "مواقع", "ويب", "web", "landing", "صفحة هبوط", "scraping", "سكرابينج", "api",
    "wordpress", "ووردبريس",
]
# Put words here to skip jobs that contain them
BLOCK = []                   # e.g. ["مغني", "سائق", "تعليق صوتي"]
KEYWORDS_ENABLED = False     # False = send EVERY new job (default). True = only jobs matching KEYWORDS
MAX_PER_CYCLE = 20           # max alerts per check; extra jobs are counted in one summary line
POLL_SECONDS = 300           # check every 5 minutes (don't go below 120)
# --------------------------------------------

ONCE = "--once" in sys.argv   # one check then exit (for GitHub Actions)
TOKEN = os.environ.get("BOT_TOKEN", "").strip()
CHAT_ID = os.environ.get("CHAT_ID", "").strip()
STATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "state.json")
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36"

def http(url, data=None, timeout=25):
    url = urllib.parse.quote(url, safe=":/?&=%#")
    req = urllib.request.Request(url, data=data, headers={"User-Agent": UA, "Accept-Language": "ar,en;q=0.8"})
    with urllib.request.urlopen(req, timeout=timeout, context=ssl.create_default_context()) as r:
        return r.read().decode("utf-8", "replace")

def clean(s):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s))).strip()

def fetch_mostaql():
    page = http("https://mostaql.com/projects")
    out = []
    for row in page.split('class="project-row"')[1:]:
        m = re.search(r'<h2[^>]*>\s*<a href="(https://mostaql\.com/project/(\d+)[^"]*)"[^>]*>(.*?)</a>', row, re.S)
        if not m:
            continue
        b = re.search(r'project__brief[^>]*>(.*?)</p>', row, re.S)
        t = re.search(r'<time[^>]*>(.*?)</time>', row, re.S)
        out.append({"site": "mostaql", "id": m.group(2), "title": clean(m.group(3)),
                    "url": urllib.parse.unquote(m.group(1)),
                    "desc": clean(b.group(1)) if b else "", "when": clean(t.group(1)) if t else "",
                    "poster": clean(re.search(r"<bdi>(.*?)</bdi>", row, re.S).group(1)) if "<bdi>" in row else ""})
    return out

def mostaql_details(job):
    """Budget and duration from the project page (best effort)."""
    try:
        t = clean(re.sub(r"<script.*?</script>|<style.*?</style>", "", http(job["url"]), flags=re.S))
        m = re.search(r"الميزانية\s*([^\s].*?)\s*مدة التنفيذ\s*(.*?)\s*المهارات", t)
        if m:
            job["budget"], job["duration"] = m.group(1)[:40], m.group(2)[:30]
    except Exception:
        pass

def fetch_khamsat():
    page = http("https://khamsat.com/community/requests")
    out = []
    for row in page.split('class="forum_post"')[1:]:
        m = re.search(r'<h3 class="details-head"><a[^>]*href="(/community/requests/(\d+)[^"]*)"[^>]*>(.*?)</a>', row, re.S)
        if not m:
            continue
        t = re.search(r'<span dir="ltr" title="[^"]*">(.*?)</span>', row, re.S)for d in json.loads(http("https://jobicy.com/api/v2/remote-jobs?count=50")).get("jobs", []):
        out.append({"site": "jobicy", "id": str(d["id"]), "title": d.get("jobTitle", ""), "poster": d.get("companyName", ""),
                    "url": d.get("url", ""), "budget": "", "desc": strip(d.get("jobExcerpt")),
                    "when": (d.get("pubDate") or "")[:10], "tags": str(d.get("jobIndustry", "")),
                    "duration": str(d.get("jobGeo", "")), "global": True})
    return out

def fetch_wwr():
    import xml.etree.ElementTree as ET
    out = []
    root = ET.fromstring(http("https://weworkremotely.com/remote-jobs.rss").encode("utf-8"))
    for it in root.iter("item"):
        g = lambda k: (it.findtext(k) or "")
        link = g("link")
        out.append({"site": "weworkremotely", "id": link.rsplit("/", 1)[-1] or link, "title": g("title"), "poster": "",
                    "url": link, "budget": g("type"), "desc": strip(g("description")), "when": "",
                    "tags": g("skills") + " " + g("category"), "duration": g("region"), "global": True})
    return out

def global_match(job):
    t = (job["title"] + " " + job.get("tags", "")).lower()
    return any(re.search(r"(?<![a-z0-9])" + re.escape(k) + r"(?![a-z0-9])", t) for k in GLOBAL_KEYWORDS)

def render(job):
    e = lambda x: html.escape(x, quote=False)
    c = COLOR[job["site"]]
    lines = ["%s <b>%s | %s</b>" % (c, LABEL[job["site"]], HEADER[job["site"]]), "",
             "<b>%s</b>" % e(job["title"])]
    if job.get("poster"):
        lines.append("👤 %s" % e(job["poster"]))
    lines.append("")
    if job.get("budget"):
        lines.append("💚 %s: <b>%s</b>" % ("الراتب/النوع" if job.get("global") else "الميزانية", e(job["budget"])))
    if job.get("duration"):
        lines.append(("🌍 المكان: %s" if job.get("global") else "⏳ المدة: %s") % e(job["duration"]))
    if job.get("when"):
        lines.append("🕒 %s" % e(job["when"]))
    if job.get("desc"):
        d = job["desc"]
        lines += ["", "<blockquote expandable>%s</blockquote>" % e(d[:600] + ("…" if len(d) > 600 else ""))]
    return "\n".join(lines)

def send_job(chat, job):
    import json as _j
    tg("sendMessage", chat_id=chat, text=render(job), parse_mode="HTML", disable_web_page_preview="true",
       reply_markup=_j.dumps({"inline_keyboard": [[{"text": "🌐 عرض الطلب في " + LABEL[job["site"]], "url": job["url"]}]]}))

SOURCES = {"mostaql": fetch_mostaql, "khamsat": fetch_khamsat, "nafezly": fetch_nafezly,
           "remoteok": fetch_remoteok, "remotive": fetch_remotive, "jobicy": fetch_jobicy, "weworkremotely": fetch_wwr}

def tg(method, **params):
    return json.loads(http("https://api.telegram.org/bot%s/%s" % (TOKEN, method),
                           data=urllib.parse.urlencode(params).encode()))

def load():
    try:
        return json.load(open(STATE, encoding="utf-8"))
    except Exception:
        return {"seen": {}, "chat_id": ""}

def save(st):
    json.dump(st, open(STATE, "w", encoding="utf-8"), ensure_ascii=False)

def match(title):
    t = title.lower()
    if any(b.lower() in t for b in BLOCK):
        return False
    if not KEYWORDS_ENABLED:
        return True
    for k in KEYWORDS:
        k = k.lower()
        if k.isascii():
            if re.search(r"(?<![a-z0-9])" + re.escape(k) + r"(?![a-z0-9])", t):
                return True
        elif k in t:
            return True
    return False

def find_chat(st):
    if CHAT_ID:
        return CHAT_IDfor d in json.loads(http("https://jobicy.com/api/v2/remote-jobs?count=50")).get("jobs", []):
        out.append({"site": "jobicy", "id": str(d["id"]), "title": d.get("jobTitle", ""), "poster": d.get("companyName", ""),
                    "url": d.get("url", ""), "budget": "", "desc": strip(d.get("jobExcerpt")),
                    "when": (d.get("pubDate") or "")[:10], "tags": str(d.get("jobIndustry", "")),
                    "duration": str(d.get("jobGeo", "")), "global": True})
    return out

def fetch_wwr():
    import xml.etree.ElementTree as ET
    out = []
    root = ET.fromstring(http("https://weworkremotely.com/remote-jobs.rss").encode("utf-8"))
    for it in root.iter("item"):
        g = lambda k: (it.findtext(k) or "")
        link = g("link")
        out.append({"site": "weworkremotely", "id": link.rsplit("/", 1)[-1] or link, "title": g("title"), "poster": "",
                    "url": link, "budget": g("type"), "desc": strip(g("description")), "when": "",
                    "tags": g("skills") + " " + g("category"), "duration": g("region"), "global": True})
    return out

def global_match(job):
    t = (job["title"] + " " + job.get("tags", "")).lower()
    return any(re.search(r"(?<![a-z0-9])" + re.escape(k) + r"(?![a-z0-9])", t) for k in GLOBAL_KEYWORDS)

def render(job):
    e = lambda x: html.escape(x, quote=False)
    c = COLOR[job["site"]]
    lines = ["%s <b>%s | %s</b>" % (c, LABEL[job["site"]], HEADER[job["site"]]), "",
             "<b>%s</b>" % e(job["title"])]
    if job.get("poster"):
        lines.append("👤 %s" % e(job["poster"]))
    lines.append("")
    if job.get("budget"):
        lines.append("💚 %s: <b>%s</b>" % ("الراتب/النوع" if job.get("global") else "الميزانية", e(job["budget"])))
    if job.get("duration"):
        lines.append(("🌍 المكان: %s" if job.get("global") else "⏳ المدة: %s") % e(job["duration"]))
    if job.get("when"):
        lines.append("🕒 %s" % e(job["when"]))
    if job.get("desc"):
        d = job["desc"]
        lines += ["", "<blockquote expandable>%s</blockquote>" % e(d[:600] + ("…" if len(d) > 600 else ""))]
    return "\n".join(lines)

def send_job(chat, job):
    import json as _j
    tg("sendMessage", chat_id=chat, text=render(job), parse_mode="HTML", disable_web_page_preview="true",
       reply_markup=_j.dumps({"inline_keyboard": [[{"text": "🌐 عرض الطلب في " + LABEL[job["site"]], "url": job["url"]}]]}))

SOURCES = {"mostaql": fetch_mostaql, "khamsat": fetch_khamsat, "nafezly": fetch_nafezly,
           "remoteok": fetch_remoteok, "remotive": fetch_remotive, "jobicy": fetch_jobicy, "weworkremotely": fetch_wwr}

def tg(method, **params):
    return json.loads(http("https://api.telegram.org/bot%s/%s" % (TOKEN, method),
                           data=urllib.parse.urlencode(params).encode()))

def load():
    try:
        return json.load(open(STATE, encoding="utf-8"))
    except Exception:
        return {"seen": {}, "chat_id": ""}

def save(st):
    json.dump(st, open(STATE, "w", encoding="utf-8"), ensure_ascii=False)

def match(title):
    t = title.lower()
    if any(b.lower() in t for b in BLOCK):
        return False
    if not KEYWORDS_ENABLED:
        return True
    for k in KEYWORDS:
        k = k.lower()
        if k.isascii():
            if re.search(r"(?<![a-z0-9])" + re.escape(k) + r"(?![a-z0-9])", t):
                return True
        elif k in t:
            return True
    return False

def find_chat(st):
    if CHAT_ID:
        return CHAT_IDfor d in json.loads(http("https://jobicy.com/api/v2/remote-jobs?count=50")).get("jobs", []):
        out.append({"site": "jobicy", "id": str(d["id"]), "title": d.get("jobTitle", ""), "poster": d.get("companyName", ""),
                    "url": d.get("url", ""), "budget": "", "desc": strip(d.get("jobExcerpt")),
                    "when": (d.get("pubDate") or "")[:10], "tags": str(d.get("jobIndustry", "")),
                    "duration": str(d.get("jobGeo", "")), "global": True})
    return out

def fetch_wwr():
    import xml.etree.ElementTree as ET
    out = []
    root = ET.fromstring(http("https://weworkremotely.com/remote-jobs.rss").encode("utf-8"))
    for it in root.iter("item"):
        g = lambda k: (it.findtext(k) or "")
        link = g("link")
        out.append({"site": "weworkremotely", "id": link.rsplit("/", 1)[-1] or link, "title": g("title"), "poster": "",
                    "url": link, "budget": g("type"), "desc": strip(g("description")), "when": "",
                    "tags": g("skills") + " " + g("category"), "duration": g("region"), "global": True})
    return out

def global_match(job):
    t = (job["title"] + " " + job.get("tags", "")).lower()
    return any(re.search(r"(?<![a-z0-9])" + re.escape(k) + r"(?![a-z0-9])", t) for k in GLOBAL_KEYWORDS)

def render(job):
    e = lambda x: html.escape(x, quote=False)
    c = COLOR[job["site"]]
    lines = ["%s <b>%s | %s</b>" % (c, LABEL[job["site"]], HEADER[job["site"]]), "",
             "<b>%s</b>" % e(job["title"])]
    if job.get("poster"):
        lines.append("👤 %s" % e(job["poster"]))
    lines.append("")
    if job.get("budget"):
        lines.append("💚 %s: <b>%s</b>" % ("الراتب/النوع" if job.get("global") else "الميزانية", e(job["budget"])))
    if job.get("duration"):
        lines.append(("🌍 المكان: %s" if job.get("global") else "⏳ المدة: %s") % e(job["duration"]))
    if job.get("when"):
        lines.append("🕒 %s" % e(job["when"]))
    if job.get("desc"):
        d = job["desc"]
        lines += ["", "<blockquote expandable>%s</blockquote>" % e(d[:600] + ("…" if len(d) > 600 else ""))]
    return "\n".join(lines)

def send_job(chat, job):
    import json as _j
    tg("sendMessage", chat_id=chat, text=render(job), parse_mode="HTML", disable_web_page_preview="true",
       reply_markup=_j.dumps({"inline_keyboard": [[{"text": "🌐 عرض الطلب في " + LABEL[job["site"]], "url": job["url"]}]]}))

SOURCES = {"mostaql": fetch_mostaql, "khamsat": fetch_khamsat, "nafezly": fetch_nafezly,
           "remoteok": fetch_remoteok, "remotive": fetch_remotive, "jobicy": fetch_jobicy, "weworkremotely": fetch_wwr}

def tg(method, **params):
    return json.loads(http("https://api.telegram.org/bot%s/%s" % (TOKEN, method),
                           data=urllib.parse.urlencode(params).encode()))

def load():
    try:
        return json.load(open(STATE, encoding="utf-8"))
    except Exception:
        return {"seen": {}, "chat_id": ""}

def save(st):
    json.dump(st, open(STATE, "w", encoding="utf-8"), ensure_ascii=False)

def match(title):
    t = title.lower()
    if any(b.lower() in t for b in BLOCK):
        return False
    if not KEYWORDS_ENABLED:
        return True
    for k in KEYWORDS:
        k = k.lower()
        if k.isascii():
            if re.search(r"(?<![a-z0-9])" + re.escape(k) + r"(?![a-z0-9])", t):
                return True
        elif k in t:
            return True
    return False

def find_chat(st):
    if CHAT_ID:
        return CHAT_IDout.append({"site": "khamsat", "id": m.group(2), "title": clean(m.group(3)),
                    "url": "https://khamsat.com" + urllib.parse.unquote(m.group(1)),
                    "desc": "", "when": clean(t.group(1)) if t else "",
                    "poster": clean(re.search(r'<a class="user"[^>]*>(.*?)</a>', row, re.S).group(1)) if 'class="user"' in row else ""})
    return out

def fetch_nafezly():
    page = http("https://nafezly.com/projects")
    out, seen = [], set()
    for m in re.finditer(r'<a[^>]*href="(https://nafezly\.com/project/([^"/?#]+)[^"]*)"[^>]*>(.*?)</a>', page, re.S):
        t = clean(m.group(3))
        if len(t) > 6 and m.group(2) not in seen:
            seen.add(m.group(2))
            out.append({"site": "nafezly", "id": m.group(2), "title": t,
                        "url": urllib.parse.unquote(m.group(1)), "desc": "", "when": ""})
    return out

HEADER = {"mostaql": "مشاريع جديدة", "khamsat": "طلبات الخدمات", "nafezly": "مشاريع جديدة", "remoteok": "وظائف ريموت", "remotive": "وظائف ريموت", "jobicy": "وظائف ريموت", "weworkremotely": "وظائف ريموت"}

COLOR = {"mostaql": "🟦", "khamsat": "🟨", "nafezly": "🟩", "remoteok": "🟥", "remotive": "🟧", "jobicy": "🟪", "weworkremotely": "🟫"}   # edit to change platform colors
LABEL = {"mostaql": "مستقل", "khamsat": "خمسات", "nafezly": "نفذلي", "remoteok": "RemoteOK", "remotive": "Remotive", "jobicy": "Jobicy", "weworkremotely": "WeWorkRemotely"}


# ---------- global remote-job sources (AI-related filter below) ----------
GLOBAL_KEYWORDS = ["ai", "llm", "gpt", "chatgpt", "openai", "claude", "prompt", "machine learning", "ml",
                   "automation", "automate", "n8n", "zapier", "make.com", "no-code", "nocode", "low-code",
                   "bot", "chatbot", "agent", "agents", "rag", "langchain", "python", "scraping", "scraper",
                   "data annotation", "annotator", "ai trainer", "telegram", "web developer", "wordpress", "api"]
ENABLED_SOURCES = {"mostaql": True, "khamsat": True, "nafezly": True,
                   "remoteok": True, "remotive": True, "jobicy": True, "weworkremotely": True}

def strip(x, n=300):
    return clean(html.unescape(re.sub(r"<[^>]+>", " ", html.unescape(x or ""))))[:n]

def fetch_remoteok():
    out = []
    for d in json.loads(http("https://remoteok.com/api"))[1:]:
        sal = ""
        if d.get("salary_min"):
            sal = "$%s-%s/yr" % (d["salary_min"], d.get("salary_max") or d["salary_min"])
        out.append({"site": "remoteok", "id": str(d["id"]), "title": d.get("position", ""), "poster": d.get("company", ""),
                    "url": d.get("url", ""), "budget": sal, "desc": strip(d.get("description")),
                    "when": (d.get("date") or "")[:10], "tags": " ".join(d.get("tags") or []), "global": True})
    return out

def fetch_remotive():
    out = []
    for d in json.loads(http("https://remotive.com/api/remote-jobs?limit=100")).get("jobs", []):
        out.append({"site": "remotive", "id": str(d["id"]), "title": d.get("title", ""), "poster": d.get("company_name", ""),
                    "url": d.get("url", ""), "budget": d.get("salary", ""), "desc": strip(d.get("description")),
                    "when": (d.get("publication_date") or "")[:10], "tags": " ".join(d.get("tags") or []),
                    "duration": d.get("candidate_required_location", ""), "global": True})
    return out

def fetch_jobicy():
    out = []if st.get("chat_id"):
        return st["chat_id"]
    print("افتح البوت في تيليجرام واضغط Start وانا هلاقيك...")
    while True:
        for u in tg("getUpdates").get("result", []):
            msg = u.get("message") or {}
            if msg.get("chat", {}).get("id"):
                st["chat_id"] = str(msg["chat"]["id"]); save(st)
                tg("sendMessage", chat_id=st["chat_id"], text="تمام ✅ هبعتلك الشغل الجديد من مستقل وخمسات هنا.")
                return st["chat_id"]
        time.sleep(5)

def main():
    if not TOKEN:
        sys.exit("BOT_TOKEN مش متحدد. شوف README.")
    st = load()
    if ONCE and not CHAT_ID and not st.get("chat_id"):
        sys.exit("CHAT_ID مطلوب مع --once")
    chat = find_chat(st)
    while True:
        for name, fn in SOURCES.items():
            if not ENABLED_SOURCES.get(name, True):
                continue
            try:
                jobs = fn()
            except Exception as e:
                print(name, "skipped:", e)   # e.g. Nafezly 403: just skip
                continue
            first = name not in st["seen"]
            seen = set(st["seen"].get(name, []))
            sent = skipped = 0
            for job in reversed(jobs):
                site, jid, title = job["site"], job["id"], job["title"]
                if jid in seen:
                    continue
                seen.add(jid)
                if first:
                    continue          # first run: remember only, don't spam
                key = re.sub(r"\W+", "", title.lower())
                if key in st.setdefault("titles", []):
                    continue          # same title already sent (reposts/dupes)
                if (global_match(job) if job.get("global") else match(title)):
                    if sent >= MAX_PER_CYCLE:
                        skipped += 1
                        continue
                    sent += 1
                    st["titles"] = (st["titles"] + [key])[-500:]
                    try:
                        if site == "mostaql":
                            mostaql_details(job)
                        send_job(chat, job)
                    except Exception as e:
                        print("send failed:", e)
            if skipped:
                try:
                    tg("sendMessage", chat_id=chat, text="+%d مشروع جديد كمان على %s (افتح الموقع)" % (skipped, LABEL[name]))
                except Exception as e:
                    print("send failed:", e)
            st["seen"][name] = list(seen)[-300:]
            save(st)
        if ONCE:
            return
        time.sleep(POLL_SECONDS)

if __name__ == "__main__":
    main()
