"""
Fetches remote jobs from free public feeds and writes index.html.
Run:  python fetch_jobs.py
No API keys needed. Uses only the Python standard library.
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


def from_remotive():
    data = json.loads(get("https://remotive.com/api/remote-jobs"))
    return [
        {
            "title": j.get("title", ""),
            "company": j.get("company_name", ""),
            "location": j.get("candidate_required_location", "Anywhere"),
            "category": j.get("category", ""),
            "date": (j.get("publication_date") or "")[:10],
            "url": j.get("url", ""),
            "source": "Remotive",
        }
        for j in data.get("jobs", [])
    ]


def from_remoteok():
    data = json.loads(get("https://remoteok.com/api"))
    jobs = []
    for j in data:
        if not isinstance(j, dict) or "position" not in j:
            continue  # first item is a legal notice
        jobs.append(
            {
                "title": j.get("position", ""),
                "company": j.get("company", ""),
                "location": j.get("location") or "Anywhere",
                "category": ", ".join((j.get("tags") or [])[:3]),
                "date": (j.get("date") or "")[:10],
                "url": j.get("apply_url") or j.get("url", ""),
                "source": "RemoteOK",
            }
        )
    return jobs


def from_wwr():
    root = ET.fromstring(get("https://weworkremotely.com/remote-jobs.rss"))
    jobs = []
    for item in root.iter("item"):
        raw = item.findtext("title", "")
        company, _, title = raw.partition(":")
        if not title:
            company, title = "", raw
        jobs.append(
            {
                "title": title.strip(),
                "company": company.strip(),
                "location": item.findtext("region", "Anywhere"),
                "category": item.findtext("category", ""),
                "date": "",
                "url": item.findtext("link", ""),
                "source": "WeWorkRemotely",
            }
        )
    return jobs


def main():
    jobs = []
    for fn in (from_remotive, from_remoteok, from_wwr):
        try:
            got = fn()
            print(f"{fn.__name__}: {len(got)} jobs")
            jobs += got
        except Exception as e:  # one broken source should not stop the rest
            print(f"{fn.__name__} failed: {e}")

    # de-duplicate on title+company
    seen, unique = set(), []
    for j in jobs:
        key = re.sub(r"\W+", "", (j["title"] + j["company"]).lower())
        if key and key not in seen and j["url"]:
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
.job{background:var(--card);border-radius:10px;padding:14px;margin:10px 0}
.job h3{margin:0 0 4px;font-size:17px}
.meta{color:var(--mut);font-size:14px}
a.apply{display:inline-block;margin-top:8px;color:var(--acc);font-weight:600}
.tips{background:var(--card);border-radius:10px;padding:12px 16px;font-size:14px}
</style></head><body><main>
<h1>Remote Jobs</h1>
<p class="meta">Updated __UPDATED__ &middot; <span id="count"></span></p>
<div class="tips"><b>How to apply:</b> click Apply, read the posting, then follow the
instructions on the employer's page. Tailor your CV to the job title, send a short
cover note (3-4 lines), and apply within 48 hours of posting.</div>
<br>
<input id="q" placeholder="Search title, company, skill...">
<select id="src"><option value="">All sources</option></select>
<div id="list"></div>
</main>
<script>
const JOBS=__JOBS__;
const q=document.getElementById('q'),src=document.getElementById('src'),
list=document.getElementById('list'),count=document.getElementById('count');
[...new Set(JOBS.map(j=>j.source))].forEach(s=>{const o=document.createElement('option');o.value=o.textContent=s;src.appendChild(o)});
function esc(s){return String(s||'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]))}
function safe(u){return /^https?:\\/\\//.test(u)?u:'#'}
function render(){
  const t=q.value.toLowerCase(),s=src.value;
  const r=JOBS.filter(j=>(!s||j.source===s)&&(!t||(j.title+j.company+j.category+j.location).toLowerCase().includes(t)));
  count.textContent=r.length+' jobs';
  list.innerHTML=r.slice(0,200).map(j=>`<div class="job"><h3>${esc(j.title)}</h3>
  <div class="meta">${esc(j.company)} &middot; ${esc(j.location)} &middot; ${esc(j.category)} &middot; ${esc(j.date)} &middot; ${esc(j.source)}</div>
  <a class="apply" href="${safe(j.url)}" target="_blank" rel="noopener">Apply &rarr;</a></div>`).join('');
}
q.oninput=render;src.onchange=render;render();
</script></body></html>"""

if __name__ == "__main__":
    main()
