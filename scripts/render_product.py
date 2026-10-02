#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import html
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
PUBLIC=ROOT/"public"
REGISTRY=PUBLIC/"registry.json"
REPORT=ROOT/"data"/"verification-report.json"
CHANGE_FEED=ROOT/"data"/"change-feed.json"

def esc(v):
    return html.escape(str(v if v is not None else ""),quote=True)

def slug(v):
    return re.sub(r"[^a-z0-9]+","-",str(v).lower()).strip("-")

def date(v):
    return str(v)[:10] if v else "Not declared"

def epoch(v):
    if not v:return 0
    try:
        return int(dt.datetime.fromisoformat(str(v).replace("Z","+00:00")).timestamp())
    except Exception:
        return 0

def fmt_compact(v):
    try:n=int(v or 0)
    except Exception:return "0"
    if n>=1_000_000_000:return f"{n/1_000_000_000:.1f}B"
    if n>=1_000_000:return f"{n/1_000_000:.1f}M"
    if n>=1_000:return f"{n/1_000:.1f}K"
    return f"{n:,}"

def head(title,desc,canonical,extra=""):
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="theme-color" content="#f7f7f4"><title>{esc(title)}</title><meta name="description" content="{esc(desc)}"><link rel="canonical" href="{esc(canonical)}"><meta name="robots" content="index,follow,max-snippet:-1"><meta property="og:site_name" content="Open Model Weights"><meta property="og:title" content="{esc(title)}"><meta property="og:description" content="{esc(desc)}"><meta property="og:url" content="{esc(canonical)}"><link rel="stylesheet" href="/styles.css">{extra}</head>'''

def header(active=""):
    links=[("models","/models/","Models"),("explore","/explore/","Explore"),("developers","/developers/","Developers"),("changes","/changes/","Changes"),("verification","/verification/","Verification")]
    out=[]
    for key,url,label in links:
        cur=' aria-current="page"' if active==key else ""
        out.append(f'<a class="nav-link" href="{url}"{cur}>{label}</a>')
    cur=' aria-current="page"' if active=="compare" else ""
    out.append(f'<a class="nav-link nav-compare" href="/compare/"{cur}>Compare <span aria-hidden="true">→</span></a>')
    return '<header class="site-header"><a class="brand" href="/" aria-label="Open Model Weights home">Open Model Weights</a><nav aria-label="Primary navigation">'+''.join(out)+'</nav></header>'

def footer():
    return '''<footer class="site-footer"><div class="footer-brand"><strong>Open Model Weights</strong><p>Field-verified intelligence for open-weight AI.</p></div><div class="footer-links"><a href="/models/">Models</a><a href="/compare/">Compare</a><a href="/sources/">Sources</a><a href="/verification/">Verification</a><a href="/methodology/">Methodology</a><a href="/api/">API / JSON</a><a href="/registry.json">Registry JSON</a><a href="https://github.com/openmodelweights/openmodelweights" rel="noopener">GitHub ↗</a><a href="https://huggingface.co/openmodelweights" rel="noopener">Hugging Face ↗</a></div></footer>'''

def trust_strip(checked,full=None,mode=None):
    full=full or checked
    mode_text="Repository revision checked" if mode=="repository-revision-unchanged" else "Field evidence checked"
    return f'''<div class="trust-strip"><div><span class="trust-dot">●</span><strong>Source-first verification</strong></div><div><span>{esc(mode_text)}</span><strong>{esc(checked)}</strong></div><div><span>Full field verification</span><strong>{esc(full)}</strong></div><a href="/sources/">Source policy →</a><a href="/methodology/">Methodology →</a></div>'''

def context_value(m):
    c=(m.get("model") or {}).get("context")
    return c.get("value") if isinstance(c,dict) else None

def context_display(m):
    c=(m.get("model") or {}).get("context")
    return c.get("display") if isinstance(c,dict) else (c or "Not declared")

def model_discovery_page(models,generated):
    orgs=sorted({m.get("developer","Unknown") for m in models})
    licenses=sorted({(m.get("license") or {}).get("name","Not declared") for m in models})
    commercial=sorted({((m.get("license") or {}).get("commercial_use") or {}).get("status","unknown") for m in models})
    formats=sorted({x for m in models for x in (m.get("weights") or {}).get("formats",[]) if x and not x.startswith("No recognized")})
    rows=[]
    for m in models:
        lic=m.get("license") or {}; com=lic.get("commercial_use") or {}; hub=m.get("hub") or {}; ver=m.get("verification") or {}
        hw=(m.get("hardware") or {}).get("weight_only_gb") or {}
        p=(m.get("model") or {}).get("total_parameters_billions")
        fmt=(m.get("weights") or {}).get("formats",[])
        search=" ".join([m.get("name",""),m.get("developer",""),m.get("family",""),lic.get("name","")," ".join(fmt),(m.get("model") or {}).get("modality","")]).lower()
        rows.append(f'''<a class="registry-row discovery-row" href="/models/{esc(m["id"])}/" data-title="{esc(m.get("name",""))}" data-search="{esc(search)}" data-org="{esc(m.get("developer","").lower())}" data-license="{esc(lic.get("name","").lower())}" data-commercial="{esc(com.get("status","unknown").lower())}" data-formats="{esc("|".join(fmt))}" data-params="{esc(p if p is not None else "")}" data-context="{esc(context_value(m) if context_value(m) is not None else "")}" data-memory="{esc(hw.get("int4") if hw.get("int4") is not None else "")}" data-created="{epoch(hub.get("created_at"))}" data-updated="{epoch(hub.get("last_modified"))}" data-downloads="{esc(hub.get("downloads") or 0)}" data-likes="{esc(hub.get("likes") or 0)}"><div><div class="row-title">{esc(m.get("name"))}</div><div class="row-sub">{esc(m.get("developer"))} · {esc((m.get("model") or {}).get("modality",""))} · {esc((m.get("model") or {}).get("parameters",""))}</div></div><div><strong>{esc(context_display(m))}</strong><span>context</span></div><div><span class="pill">{esc(lic.get("name","Not declared"))}</span><small>{esc(com.get("status","unknown").replace("-"," "))}</small></div><div><strong>{f'~{hw.get("int4"):,.1f} GB' if isinstance(hw.get("int4"),(int,float)) else "—"}</strong><span>INT4 weights</span></div><div><strong>{fmt_compact(hub.get("downloads"))}</strong><span>{fmt_compact(hub.get("likes"))} likes</span></div><div><span class="pill verified">Checked {esc(date(ver.get("checked_at")))}</span><small>full: {esc(date(ver.get("full_verified_at") or ver.get("checked_at")))}</small></div></a>''')
    opt_org="".join(f'<option value="{esc(x.lower())}">{esc(x)}</option>' for x in orgs)
    opt_lic="".join(f'<option value="{esc(x.lower())}">{esc(x)}</option>' for x in licenses)
    opt_com="".join(f'<option value="{esc(x.lower())}">{esc(x.replace("-"," ").title())}</option>' for x in commercial)
    opt_fmt="".join(f'<option value="{esc(x)}">{esc(x)}</option>' for x in formats)
    checked=date(generated)
    return f'''{head(f"{len(models)} field-verified open-weight AI models — Open Model Weights",f"Discover and sort {len(models)} verified open-weight AI model records by developer, license, context, parameters, hardware, repository date and popularity.","https://openmodelweights.com/models/",'<script src="/discovery.js?v=1" defer></script>')}<body>{header("models")}<main><section class="page-hero discovery-hero"><div class="breadcrumbs"><a href="/">Home</a> / Models</div><p class="eyebrow">FIELD-VERIFIED REGISTRY · {len(models)} RECORDS</p><h1>Discover open-weight models.</h1><p class="lead">Filter and sort source repositories by technical, legal, hardware and freshness signals. Missing values stay missing rather than being inferred.</p></section>{trust_strip(checked,checked)}<section class="section registry-section"><div class="discovery-controls"><div class="discovery-search"><input id="model-search" type="search" placeholder="Search model, developer, family, license or format…"><button id="reset-filters" type="button">Reset</button></div><div class="discovery-filters"><select id="org-filter"><option value="">All developers</option>{opt_org}</select><select id="license-filter"><option value="">All licenses</option>{opt_lic}</select><select id="commercial-filter"><option value="">All commercial-use classes</option>{opt_com}</select><select id="format-filter"><option value="">All formats</option>{opt_fmt}</select></div><div class="discovery-sort"><label>Sort <select id="sort-filter"><option value="popular">Popularity · downloads</option><option value="likes">Popularity · likes</option><option value="params-desc">Parameters · largest</option><option value="params-asc">Parameters · smallest</option><option value="context-desc">Context · largest</option><option value="memory-asc">INT4 memory · lowest</option><option value="created-desc">Repository created · newest</option><option value="updated-desc">Publisher updated · newest</option><option value="name">Name · A–Z</option></select></label><label>Per page <select id="page-size"><option>25</option><option selected>50</option><option>100</option></select></label></div><p class="note discovery-note">“Repository created” is used as a release-date proxy when the publisher does not expose a separate structured release date.</p></div><div class="registry-list-head"><span>Model</span><span>Context</span><span>License</span><span>INT4</span><span>Popularity</span><span>Freshness</span></div><p id="registry-result-count" class="registry-result-count" aria-live="polite"></p><div class="registry-list">{''.join(rows)}</div><p id="no-results" class="note" hidden>No matching models.</p><div class="registry-pagination"><button id="page-prev" type="button">← Previous</button><span id="page-info"></span><button id="page-next" type="button">Next →</button></div></section></main>{footer()}</body></html>'''

def compare_page(model_count,generated):
    return f'''{head("Compare open-weight AI models — Compare 2.0 | Open Model Weights","Compare two to four verified open-weight models with neutral visual highlighting for technical, legal, hardware, lineage, training, freshness and popularity differences.","https://openmodelweights.com/compare/",'<script src="/compare.js?v=4" defer></script>')}<body class="compare-page">{header("compare")}<main><section class="page-hero"><div class="breadcrumbs"><a href="/">Home</a> / Compare</div><p class="eyebrow">COMPARE 2.0 · {model_count} VERIFIED RECORDS</p><h1>Differences, without a winner.</h1><p class="lead">Put two to four verified records side by side. Different values are highlighted neutrally; Open Model Weights does not turn them into a composite score.</p></section>{trust_strip(date(generated),date(generated))}<section class="section compare-section"><div class="compare-picker"><div class="compare-select-grid"><label>Model 1<select id="compare-1" class="compare-select"></select></label><label>Model 2<select id="compare-2" class="compare-select"></select></label><label>Model 3 <span>optional</span><select id="compare-3" class="compare-select"></select></label><label>Model 4 <span>optional</span><select id="compare-4" class="compare-select"></select></label></div><div class="compare-actions"><label class="compare-toggle"><input id="differences-only" type="checkbox"> Show differences only</label><button id="share-comparison" class="button" type="button">Copy comparison link</button></div><p id="compare-summary" class="compare-summary"></p><div id="compare-message" class="compare-message" hidden></div></div><div id="compare-output" class="compare-output" aria-live="polite"><p class="note">Loading verified registry…</p></div></section></main>{footer()}</body></html>'''

def changes_page(feed,models,generated):
    events=feed.get("events",[])[:1000]
    devs=sorted({e.get("developer","") for e in events if e.get("developer")})
    types=sorted({e.get("type","") for e in events if e.get("type")})
    dopt="".join(f'<option value="{esc(x.lower())}">{esc(x)}</option>' for x in devs)
    topt="".join(f'<option value="{esc(x)}">{esc(x.title())}</option>' for x in types)
    items=[]
    for e in events:
        search=" ".join([e.get("model",""),e.get("developer",""),e.get("summary",""),e.get("detail","")]).lower()
        items.append(f'''<article class="change-item" data-at="{esc(e.get("at",""))}" data-type="{esc(e.get("type",""))}" data-developer="{esc(e.get("developer","").lower())}" data-search="{esc(search)}"><time>{esc(e.get("at",""))}</time><div><span class="change-type">{esc(e.get("type",""))}</span><h3><a href="{esc(e.get("url","/changes/"))}">{esc(e.get("model","Registry"))}</a></h3><strong>{esc(e.get("summary",""))}</strong><p>{esc(e.get("detail",""))}</p></div></article>''')
    upstream=[]
    for e in feed.get("publisher_activity",[])[:120]:
        upstream.append(f'''<a class="upstream-row" href="{esc(e.get("url",""))}"><time>{esc(e.get("at",""))}</time><div><strong>{esc(e.get("model",""))}</strong><span>{esc(e.get("developer",""))}</span></div><code>{esc((e.get("sha") or "")[:10])}</code></a>''')
    return f'''{head("What changed? — release and verification history | Open Model Weights","Long-horizon change history for verified open-weight model repositories, metadata and registry verification runs.","https://openmodelweights.com/changes/",'<script src="/changes-v2.js?v=1" defer></script>')}<body>{header("changes")}<main><section class="page-hero"><div class="breadcrumbs"><a href="/">Home</a> / Changes</div><p class="eyebrow">RELEASE / VERIFICATION HISTORY</p><h1>What changed?</h1><p class="lead">Repository revisions, field-level metadata changes and verification runs retained as a rolling history instead of a one-day snapshot.</p></section>{trust_strip(date(generated),date(generated))}<section class="metric-strip freshness-metrics"><div><span>Events retained</span><strong>{len(feed.get("events",[])):,}</strong></div><div><span>Publisher activity records</span><strong>{len(feed.get("publisher_activity",[])):,}</strong></div><div><span>Models tracked</span><strong>{len(models):,}</strong></div><div><span>History policy</span><strong>up to 5,000 events</strong></div></section><section class="section explorer-section"><div class="explorer-controls change-controls"><input id="changes-search" type="search" placeholder="Search model, developer or change…"><select id="changes-type"><option value="">All change types</option>{topt}</select><select id="changes-developer"><option value="">All developers</option>{dopt}</select><select id="changes-range"><option value="7">Last 7 days</option><option value="30" selected>Last 30 days</option><option value="365">Last 365 days</option><option value="">All retained history</option></select></div><p id="changes-count" class="explorer-result-count"></p><div class="changes-layout"><div><h2 class="explorer-title">Registry changes</h2><div class="change-feed">{''.join(items)}</div></div><aside><h2 class="explorer-title">Publisher repository activity</h2><div class="upstream-feed">{''.join(upstream)}</div><p class="note">Publisher activity is Hugging Face repository metadata. A changed repository timestamp is not automatically treated as a semantic model release.</p></aside></div></section></main>{footer()}</body></html>'''

def sources_page(generated,count):
    return f'''{head("Source policy & verification trust — Open Model Weights","How Open Model Weights distinguishes repository evidence, publisher claims, inferred values, missing metadata and verification freshness.","https://openmodelweights.com/sources/")}<body>{header()}<main><section class="page-hero"><div class="breadcrumbs"><a href="/">Home</a> / Sources</div><p class="eyebrow">SOURCE POLICY</p><h1>Evidence before inference.</h1><p class="lead">The registry records what a source repository and its publisher-facing metadata actually expose. Unknown values remain explicit.</p></section>{trust_strip(date(generated),date(generated))}<section class="section content trust-content"><h2>Evidence hierarchy</h2><p><strong>Primary repository evidence</strong> includes the Hugging Face model API, exact repository file listing, model card, config files and repository license files. These sources are used for weights, formats, context signals, lineage metadata and declared license information.</p><p><strong>Publisher documentation</strong> is used where a repository points to separate terms, model documentation or organization information.</p><p><strong>Derived values</strong> are labeled as estimates. Hardware figures are weight-only memory estimates from parameter counts; they are not deployment guarantees.</p><h2>What field-verified means</h2><p>Each published record has passed the field verifier for its listed source repository. “Not disclosed” means the checked standard sources did not expose that value. It does not mean the information cannot exist elsewhere.</p><h2>Repository identity</h2><p>With a large registry, some records are publisher repositories and some can be community-maintained model repositories. Open Model Weights therefore calls the indexed URL the <strong>source repository</strong> unless publisher ownership is independently established.</p><h2>Freshness</h2><p>Daily checks compare the current source-repository revision with the last verified revision. If the repository SHA is unchanged, prior field evidence is retained and the revision check is recorded separately from the date of the last full field verification.</p><h2>Current scope</h2><p>{count:,} model records are currently published. The discovery pipeline may keep reserve candidates so that failed or unavailable repositories do not reduce the public target count.</p></section></main>{footer()}</body></html>'''

def api_docs(count,generated):
    endpoints=[
      ("/api/v1/meta.json","Registry metadata, count, schema and freshness."),
      ("/api/v1/models.json","Compact machine-readable model index."),
      ("/api/v1/models/{id}.json","Full field-verified record for one model."),
      ("/api/v1/developers.json","Developer aggregation."),
      ("/api/v1/licenses.json","License and commercial-use aggregation."),
      ("/api/v1/changes.json","Rolling release / verification change history."),
      ("/openapi.json","OpenAPI 3.1 description of the static JSON layer."),
      ("/registry.json","Canonical full registry JSON.")
    ]
    rows="".join(f'<div class="api-endpoint"><code>{esc(p)}</code><p>{esc(d)}</p></div>' for p,d in endpoints)
    return f'''{head("Open Model Weights API & JSON documentation","Machine-readable JSON endpoints and schema documentation for the Open Model Weights field-verified registry.","https://openmodelweights.com/api/")}<body>{header()}<main><section class="page-hero"><div class="breadcrumbs"><a href="/">Home</a> / API</div><p class="eyebrow">MACHINE-READABLE LAYER · v1</p><h1>Use the registry as data.</h1><p class="lead">Static, cacheable JSON for {count:,} verified model records, developer/license aggregates and change history. Designed so an MCP or live query API can be added later without changing the core record shape.</p></section>{trust_strip(date(generated),date(generated))}<section class="section api-docs"><div class="api-grid">{rows}</div><div class="content"><h2>Stability</h2><p><code>/api/v1/</code> is the first versioned machine-readable surface. Additive fields may appear without a version bump; breaking shape changes will use a new API version.</p><h2>CORS & caching</h2><p>JSON API paths are configured for cross-origin read access and short public caching. The canonical registry remains available at <code>/registry.json</code>.</p><h2>Evidence semantics</h2><p>Machine-readable values preserve verification status, sources, explicit unknowns and the distinction between repository revision checks and full field verification.</p></div></section></main>{footer()}</body></html>'''

def compact_model(m):
    return {
      "id":m.get("id"),"name":m.get("name"),"developer":m.get("developer"),"family":m.get("family"),"variant":m.get("variant"),
      "model":m.get("model"),"license":m.get("license"),"hardware":m.get("hardware"),
      "formats":(m.get("weights") or {}).get("formats",[]),"repository":(m.get("weights") or {}).get("repository"),
      "lineage":m.get("lineage"),"runtime_support":m.get("runtime_support"),"hub":m.get("hub"),"verification":m.get("verification"),
      "url":f'https://openmodelweights.com/models/{m.get("id")}/'
    }

def write_api(reg,report,feed):
    models=reg["models"]; api=PUBLIC/"api"/"v1"; (api/"models").mkdir(parents=True,exist_ok=True)
    compact=[compact_model(m) for m in models]
    (api/"models.json").write_text(json.dumps({"generated_at":reg.get("generated_at"),"count":len(compact),"models":compact},indent=2,ensure_ascii=False)+"\n")
    for m in models:
        (api/"models"/f'{m["id"]}.json').write_text(json.dumps(m,indent=2,ensure_ascii=False)+"\n")
    devs=defaultdict(list)
    for m in models:devs[m.get("developer","Unknown")].append(m)
    developer_payload=[]
    for d,items in sorted(devs.items()):
        developer_payload.append({"name":d,"slug":slug(d),"model_count":len(items),"families":sorted({x.get("family") for x in items if x.get("family")}),"url":f"https://openmodelweights.com/developers/{slug(d)}/"})
    (api/"developers.json").write_text(json.dumps({"generated_at":reg.get("generated_at"),"developers":developer_payload},indent=2,ensure_ascii=False)+"\n")
    lic=defaultdict(lambda:{"count":0,"commercial_use":Counter()})
    for m in models:
        name=(m.get("license") or {}).get("name","Not declared");status=((m.get("license") or {}).get("commercial_use") or {}).get("status","unknown")
        lic[name]["count"]+=1;lic[name]["commercial_use"][status]+=1
    license_payload=[{"name":k,"model_count":v["count"],"commercial_use":dict(v["commercial_use"])} for k,v in sorted(lic.items())]
    (api/"licenses.json").write_text(json.dumps({"generated_at":reg.get("generated_at"),"licenses":license_payload},indent=2,ensure_ascii=False)+"\n")
    (api/"changes.json").write_text(json.dumps(feed,indent=2,ensure_ascii=False)+"\n")
    meta={"api_version":"v1","registry_schema":reg.get("schema_version"),"generated_at":reg.get("generated_at"),"model_count":len(models),"verification":report.get("stats",{}),"links":{"models":"https://openmodelweights.com/api/v1/models.json","changes":"https://openmodelweights.com/api/v1/changes.json","openapi":"https://openmodelweights.com/openapi.json","registry":"https://openmodelweights.com/registry.json"}}
    (api/"meta.json").write_text(json.dumps(meta,indent=2,ensure_ascii=False)+"\n")
    schema={"$schema":"https://json-schema.org/draft/2020-12/schema","$id":"https://openmodelweights.com/api/v1/model.schema.json","title":"Open Model Weights model record","type":"object","required":["id","name","developer","model","weights","license","verification","sources"],"properties":{"id":{"type":"string"},"name":{"type":"string"},"developer":{"type":"string"},"family":{"type":["string","null"]},"model":{"type":"object"},"weights":{"type":"object"},"license":{"type":"object"},"hardware":{"type":"object"},"lineage":{"type":"object"},"training_assets":{"type":"object"},"runtime_support":{"type":"object"},"hub":{"type":"object"},"verification":{"type":"object"},"sources":{"type":"array"}}}
    (api/"model.schema.json").write_text(json.dumps(schema,indent=2)+"\n")
    openapi={"openapi":"3.1.0","info":{"title":"Open Model Weights JSON API","version":"1.0.0","description":"Static, versioned JSON surface for the field-verified Open Model Weights registry."},"servers":[{"url":"https://openmodelweights.com"}],"paths":{"/api/v1/meta.json":{"get":{"summary":"Registry metadata","responses":{"200":{"description":"Registry metadata"}}}},"/api/v1/models.json":{"get":{"summary":"Compact model index","responses":{"200":{"description":"Model index"}}}},"/api/v1/models/{id}.json":{"get":{"summary":"Full verified model record","parameters":[{"name":"id","in":"path","required":True,"schema":{"type":"string"}}],"responses":{"200":{"description":"Full model record"}}}},"/api/v1/developers.json":{"get":{"summary":"Developer aggregation","responses":{"200":{"description":"Developer aggregation"}}}},"/api/v1/licenses.json":{"get":{"summary":"License aggregation","responses":{"200":{"description":"License aggregation"}}}},"/api/v1/changes.json":{"get":{"summary":"Rolling change history","responses":{"200":{"description":"Change history"}}}}}}
    (PUBLIC/"openapi.json").write_text(json.dumps(openapi,indent=2)+"\n")
    (PUBLIC/"_headers").write_text("""/api/*
  Access-Control-Allow-Origin: *
  Cache-Control: public, max-age=300

/registry.json
  Access-Control-Allow-Origin: *
  Cache-Control: public, max-age=300

/openapi.json
  Access-Control-Allow-Origin: *
  Cache-Control: public, max-age=3600
""")

def patch_model_page(path,m,generated):
    text=path.read_text()
    text=text.replace("official Hugging Face repository","listed Hugging Face source repository").replace("Official repository ↗","Source repository ↗")
    if 'class="trust-strip"' not in text:
        marker=re.search(r'(<section class="page-hero model-head">.*?</section>)',text,re.S)
        if marker:
            ver=m.get("verification") or {}
            strip=trust_strip(date(ver.get("checked_at") or generated),date(ver.get("full_verified_at") or ver.get("checked_at") or generated),ver.get("mode"))
            text=text[:marker.end()]+strip+text[marker.end():]
    if 'Machine-readable JSON' not in text:
        text=text.replace('</div></div>\n<div class="facts">',f'<a class="button" href="/api/v1/models/{esc(m["id"])}.json">Machine-readable JSON ↗</a></div></div>\n<div class="facts">',1)
    if 'class="source-assurance"' not in text:
        source_count=len(m.get("sources") or [])
        sha=((m.get("hub") or {}).get("sha") or "")[:12]
        box=f'<div class="source-assurance"><div><span>Primary / declared sources</span><strong>{source_count}</strong></div><div><span>Repository revision</span><strong><code>{esc(sha or "not exposed")}</code></strong></div><div><span>Source policy</span><strong><a href="/sources/">How evidence is classified →</a></strong></div></div>'
        text=text.replace('<h2>Field evidence</h2>','<h2>Field evidence</h2>'+box,1)
    text=re.sub(r'<footer(?: class="[^"]*")?>.*?</footer>',footer(),text,count=1,flags=re.S)
    path.write_text(text)

def patch_general_pages(generated):
    generic=trust_strip(date(generated),date(generated))
    for p in PUBLIC.rglob("index.html"):
        route="/"+str(p.relative_to(PUBLIC).parent).strip(".").strip("/").replace("\\","/")+"/"
        if route in ("/models/","/compare/","/changes/","/sources/","/api/"):continue
        text=p.read_text()
        if 'class="page-hero' in text and 'class="trust-strip"' not in text:
            m=re.search(r'(<section class="page-hero[^"]*">.*?</section>)',text,re.S)
            if m:text=text[:m.end()]+generic+text[m.end():]
        if route=="//" or p==PUBLIC/"index.html":
            if 'class="home-trust"' not in text:
                m=re.search(r'(<section class="hero[^"]*">.*?</section>)',text,re.S)
                if m:
                    home=f'<div class="home-trust"><span class="trust-dot">●</span><strong>Field-verified registry</strong><span>Last checked {esc(date(generated))}</span><a href="/sources/">Source policy →</a><a href="/api/">API / JSON →</a></div>'
                    text=text[:m.end()]+home+text[m.end():]
        text=re.sub(r'<footer(?: class="[^"]*")?>.*?</footer>',footer(),text,count=1,flags=re.S)
        p.write_text(text)

def patch_sitemap(generated):
    p=PUBLIC/"sitemap.xml"
    if not p.exists():return
    text=p.read_text()
    for u in ("/sources/","/api/"):
        full=f"https://openmodelweights.com{u}"
        if full not in text:
            text=text.replace("</urlset>",f'<url><loc>{full}</loc><lastmod>{date(generated)}</lastmod></url>\n</urlset>')
    p.write_text(text)

def patch_llms(count,generated):
    p=PUBLIC/"llms.txt";text=p.read_text() if p.exists() else "# Open Model Weights\n"
    block=f"""
## Machine-readable
- https://openmodelweights.com/api/ — API documentation
- https://openmodelweights.com/api/v1/meta.json — registry metadata
- https://openmodelweights.com/api/v1/models.json — compact {count}-model index
- https://openmodelweights.com/api/v1/changes.json — change history
- https://openmodelweights.com/openapi.json — OpenAPI 3.1 document
- https://openmodelweights.com/sources/ — source and evidence policy
"""
    if "## Machine-readable" not in text:text+="\n"+block
    p.write_text(text)

def main():
    reg=json.loads(REGISTRY.read_text());models=reg.get("models",[])
    report=json.loads(REPORT.read_text()) if REPORT.exists() else {}
    feed=json.loads(CHANGE_FEED.read_text()) if CHANGE_FEED.exists() else {"events":[],"publisher_activity":[]}
    generated=reg.get("generated_at") or dt.datetime.now(dt.timezone.utc).isoformat()
    reg["schema_version"]="0.7.0"
    reg["model_count"]=len(models)
    reg["freshness"]={"last_registry_run":generated,"policy":"daily repository revision check; full field verification on changed/new repositories"}
    reg["api"]={"version":"v1","documentation":"https://openmodelweights.com/api/","models":"https://openmodelweights.com/api/v1/models.json","changes":"https://openmodelweights.com/api/v1/changes.json","openapi":"https://openmodelweights.com/openapi.json"}
    REGISTRY.write_text(json.dumps(reg,indent=2,ensure_ascii=False)+"\n")

    (PUBLIC/"models"/"index.html").write_text(model_discovery_page(models,generated))
    d=PUBLIC/"compare";d.mkdir(parents=True,exist_ok=True);(d/"index.html").write_text(compare_page(len(models),generated))
    d=PUBLIC/"changes";d.mkdir(parents=True,exist_ok=True);(d/"index.html").write_text(changes_page(feed,models,generated))
    d=PUBLIC/"sources";d.mkdir(parents=True,exist_ok=True);(d/"index.html").write_text(sources_page(generated,len(models)))
    d=PUBLIC/"api";d.mkdir(parents=True,exist_ok=True);(d/"index.html").write_text(api_docs(len(models),generated))
    write_api(reg,report,feed)

    by_id={m["id"]:m for m in models}
    for mid,m in by_id.items():
        p=PUBLIC/"models"/mid/"index.html"
        if p.exists():patch_model_page(p,m,generated)
    patch_general_pages(generated)
    patch_sitemap(generated)
    patch_llms(len(models),generated)
    print(json.dumps({"models":len(models),"api":"v1","compare":"2.0","change_events":len(feed.get("events",[]))},indent=2))

if __name__=="__main__":
    main()
