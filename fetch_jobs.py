"""
Remote jobs collector v2.
Sources: Remotive, RemoteOK, WeWorkRemotely, Jobicy, Himalayas, Working Nomads.
Writes index.html with search, role filter, region filter (Nigeria/Africa/Worldwide)
and a how-to-apply guide on every job.
Run:  python fetch_jobs.py     (standard library only, no keys needed)
"""
import json
import re
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from html import escape

UA = {"User-Agent": "Mozilla/5.0 (RemoteJobsBot; personal job board)"}


def get(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def as_text(v):
    if isinstance(v, list):
        return ", ".join(str(x) for x in v)
    return str(v or "")


# ---------- classification ----------
ROLES = [
    ("Admin & Assistant", ["assistant", "administrat", "secretar", "office", "data entry", "coordinator", "operations"]),
    ("Customer Support", ["support", "customer", "success", "helpdesk", "service rep", "chat"]),
    ("Writing & Content", ["writer", "writing", "content", "copy", "editor", "blog", "journalist", "translat", "transcri"]),
    ("Design & Creative", ["design", "creative", "illustrat", "video", "animator", "ux", "ui "]),
    ("Marketing & Sales", ["marketing", "seo", "social media", "sales", "growth", "recruit", "account exec", "business develop"]),
    ("Tech & Dev", ["developer", "engineer", "software", "devops", "data scien", "data analy", "qa ", "python", "react", "security", "programmer"]),
]


def classify_role(title, category):
    text = (title + " " + category).lower() + " "
    for name, words in ROLES:
        if any(w in text for w in words):
            return name
    return "Other"


def classify_region(location):
    t = (location or "").lower()
    if "nigeria" in t:
        return "Nigeria"
    if "africa" in t or "emea" in t:
        return "Africa"
    if not t.strip() or any(w in t for w in ("worldwide", "anywhere", "global", "world wide", "remote")) and not any(
        c in t for c in ("usa", "us only", "united states", "canada", "uk", "europe", "eu ", "india", "australia", "latam", "asia")
    ):
        return "Worldwide"
    return "Other"


def job(title, company, location, category, date, url, source):
    return {
        "title": (title or "").strip(),
        "company": (company or "").strip(),
        "location": (location or "Anywhere").strip(),
        "category": category or "",
        "role": classify_role(title or "", category or ""),
        "region": classify_region(location),
        "date": (date or "")[:10],
        "url": url or "",
        "source": source,
    }


# ---------- sources ----------
def from_remotive():
    data = json.loads(get("https://remotive.com/api/remote-jobs"))
    return [
        job(j.get("title"), j.get("company_name"), j.get("candidate_required_location"),
            j.get("category"), j.get("publication_date"), j.get("url"), "Remotive")
        for j in data.get("jobs", [])
    ]


def from_remoteok():
    data = json.loads(get("https://remoteok.com/api"))
    out = []
    for j in data:
        if isinstance(j, dict) and "position" in j:
            out.append(job(j.get("position"), j.get("company"), j.get("location"),
                           as_text((j.get("tags") or [])[:3]), j.get("date"),
                           j.get("apply_url") or j.get("url"), "RemoteOK"))
    return out


def from_wwr():
    root = ET.fromstring(get("https://weworkremotely.com/remote-jobs.rss"))
    out = []
    for item in root.iter("item"):
        raw = item.findtext("title", "")
        company, _, title = raw.partition(":")
        if not title:
            company, title = "", raw
        out.append(job(title, company, item.findtext("region", "Anywhere"),
                       item.findtext("category", ""), "", item.findtext("link"), "WeWorkRemotely"))
    return out


def from_jobicy():
    data = json.loads(get("https://jobicy.com/api/v2/remote-jobs?count=50"))
    return [
        job(j.get("jobTitle"), j.get("companyName"), j.get("jobGeo"),
            as_text(j.get("jobIndustry")), j.get("pubDate"), j.get("url"), "Jobicy")
        for j in data.get("jobs", [])
    ]


def from_himalayas():
    data = json.loads(get("https://himalayas.app/jobs/api?limit=100"))
    out = []
    for j in data.get("jobs", []):
        loc = as_text(j.get("locationRestrictions")) or "Worldwide"
        pub = j.get("pubDate")
        date = ""
        if isinstance(pub, (int, float)):
            date = datetime.fromtimestamp(pub, timezone.utc).strftime("%Y-%m-%d")
        out.append(job(j.get("title"), j.get("companyName"), loc,
                       as_text(j.get("categories")), date,
                       j.get("applicationLink") or j.get("guid"), "Himalayas"))
    return out


def from_workingnomads():
    data = json.loads(get("https://www.workingnomads.com/api/exposed_jobs/"))
    return [
        job(j.get("title"), j.get("company_name"), j.get("location"),
            j.get("category_name"), j.get("pub_date"), j.get("url"), "WorkingNomads")
        for j in data
    ]


SOURCES = [from_remotive, from_remoteok, from_wwr, from_jobicy, from_himalayas, from_workingnomads]


def main():
    jobs = []
    for fn in SOURCES:
        try:
            got = fn()
            print(f"{fn.__name__}: {len(got)} jobs")
            jobs += got
        except Exception as e:  # one broken source must not stop the rest
            print(f"{fn.__name__} failed: {e}")

    seen, unique = set(), []
    for j in jobs:
        key = re.sub(r"\W+", "", (j["title"] + j["company"]).lower())
        if key and key not in seen and j["url"].startswith("http"):
            seen.add(key)
            unique.append(j)
    unique.sort(key=lambda j: j["date"], reverse=True)

    updated = datetime.now(timezone.utc).strftime("%d %b %Y, %H:%M UTC")
    page = TEMPLATE.replace("__JOBS__", json.dumps(unique).replace("</", "<\\/"))
    page = page.replace("__UPDATED__", escape(updated))
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(page)
    print(f"Wrote index.html with {len(unique)} jobs")


TEMPLATE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Daily Remote Jobs</title>
<style>
:root{--bg:#fff;--fg:#1a1a1a;--mut:#666;--card:#f5f5f4;--acc:#0b6b4f}
@media(prefers-color-scheme:dark){:root{--bg:#161616;--fg:#eee;--mut:#9a9a9a;--card:#222;--acc:#4fd1a5}}
body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.5 system-ui,sans-serif}
main{max-width:820px;margin:auto;padding:20px}
input,select{padding:10px;border-radius:8px;border:1px solid var(--mut);background:var(--bg);color:var(--fg);font-size:16px}
#q{width:100%;box-sizing:border-box;margin-bottom:8px}
.filters{display:flex;gap:8px;flex-wrap:wrap}
.filters select{flex:1;min-width:140px}
.job{background:var(--card);border-radius:10px;padding:14px;margin:10px 0}
.job h3{margin:0 0 4px;font-size:17px}
.meta{color:var(--mut);font-size:14px}
a.apply{display:inline-block;margin-top:8px;color:var(--acc);font-weight:600}
details{margin-top:8px;font-size:14px}
summary{cursor:pointer;color:var(--acc);font-weight:600}
.tag{display:inline-block;background:var(--bg);border:1px solid var(--mut);border-radius:20px;padding:1px 10px;margin:2px 4px 2px 0;font-size:13px}
.note{background:var(--bg);border-left:3px solid var(--acc);padding:8px 12px;margin:6px 0;white-space:pre-wrap}
</style></head><body><main>
<h1>Remote Jobs</h1>
<p class="meta">Updated __UPDATED__ &middot; <span id="count"></span></p>
<input id="q" placeholder="Search title, company, skill...">
<div class="filters">
<select id="role"><option value="">All roles</option></select>
<select id="region"><option value="">All regions</option>
<option value="open">Open to me (Nigeria + Africa + Worldwide)</option>
<option value="Nigeria">Nigeria only</option><option value="Africa">Africa</option>
<option value="Worldwide">Worldwide</option><option value="Other">Other regions</option></select>
<select id="src"><option value="">All sources</option></select>
</div>
<div id="list"></div>
</main>
<script>
const JOBS=__JOBS__;
const $=id=>document.getElementById(id);
const q=$('q'),role=$('role'),region=$('region'),src=$('src'),list=$('list'),count=$('count');
[...new Set(JOBS.map(j=>j.role))].sort().forEach(s=>role.add(new Option(s,s)));
[...new Set(JOBS.map(j=>j.source))].sort().forEach(s=>src.add(new Option(s,s)));
function esc(s){return String(s||'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]))}
const GUIDE={
 'Admin & Assistant':{kw:['calendar management','email management','data entry','Google Workspace','scheduling','record keeping'],
  note:'Hello [Name], I am applying for the [Job Title] role. I keep inboxes, calendars and records organised, and I am comfortable with Google Workspace and remote tools. I would love to help your team stay on schedule.'},
 'Customer Support':{kw:['customer satisfaction','ticketing tools','live chat','problem solving','clear written English','empathy'],
  note:'Hello [Name], I am applying for the [Job Title] role. I enjoy solving customers\\' problems calmly and in clear written English, and I learn new support tools quickly.'},
 'Writing & Content':{kw:['SEO writing','research','editing and proofreading','content calendar','tone of voice','deadlines'],
  note:'Hello [Name], I am applying for the [Job Title] role. I write clear, well-researched content to deadline. I have attached samples of my work and would be glad to match your tone of voice.'},
 'Design & Creative':{kw:['portfolio','Figma','Canva','Adobe tools','brand consistency','feedback and revisions'],
  note:'Hello [Name], I am applying for the [Job Title] role. My portfolio is linked below. I design with the brand in mind and take feedback well.'},
 'Marketing & Sales':{kw:['social media','campaign results','lead generation','SEO','analytics','CRM'],
  note:'Hello [Name], I am applying for the [Job Title] role. I focus on measurable results and can start contributing quickly. Examples of my work are in my CV.'},
 'Tech & Dev':{kw:['GitHub link','projects you built','tech stack from the ad','problem solving','testing','documentation'],
  note:'Hello [Name], I am applying for the [Job Title] role. Here is a link to a project that matches your stack. I write clean, documented code and communicate clearly in remote teams.'},
 'Other':{kw:['keywords from the job ad','relevant experience','remote work skills','clear communication'],
  note:'Hello [Name], I am applying for the [Job Title] role. My experience fits what you describe, and I work well independently and remotely.'}
};
function guide(j){
  const g=GUIDE[j.role]||GUIDE['Other'];
  const note=g.note.replace('[Job Title]',j.title);
  return `<details><summary>How to apply</summary>
  <p><b>1.</b> Tap Apply and read the full posting. <b>2.</b> Check the location rule${j.region==='Other'?' (this one may limit applicants by country, check before applying)':''}.
  <b>3.</b> Tailor your CV with these keywords (only the ones that are true for you):</p>
  <div>${g.kw.map(k=>'<span class="tag">'+esc(k)+'</span>').join('')}</div>
  <p><b>4.</b> Cover note starter:</p><div class="note">${esc(note)}</div>
  <p><b>5.</b> Send it within 48 hours of posting and follow the employer's instructions exactly.</p></details>`;
}
function render(){
  const t=q.value.toLowerCase(),rg=region.value;
  const r=JOBS.filter(j=>
    (!role.value||j.role===role.value)&&(!src.value||j.source===src.value)&&
    (!rg||(rg==='open'?['Nigeria','Africa','Worldwide'].includes(j.region):j.region===rg))&&
    (!t||(j.title+j.company+j.category+j.location).toLowerCase().includes(t)));
  count.textContent=r.length+' jobs';
  list.innerHTML=r.slice(0,150).map(j=>`<div class="job"><h3>${esc(j.title)}</h3>
  <div class="meta">${esc(j.company)} &middot; ${esc(j.location)} &middot; ${esc(j.role)} &middot; ${esc(j.date)} &middot; ${esc(j.source)}</div>
  <a class="apply" href="${esc(j.url)}" target="_blank" rel="noopener">Apply &rarr;</a>${guide(j)}</div>`).join('');
}
[q,role,region,src].forEach(e=>e.addEventListener('input',render));render();
</script></body></html>"""

if __name__ == "__main__":
    main()
