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

def short_date(v):
    if not v:return "Not declared"
    try:
        d=dt.datetime.fromisoformat(str(v).replace("Z","+00:00"))
        return f"{d.day} {d.strftime('%b %Y')}"
    except Exception:
        return str(v)[:10]

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

SITE="https://openmodelweights.com"
UMAMI_ANALYTICS='<script defer src="https://cloud.umami.is/script.js" data-website-id="76f4745e-2915-44e5-aaaa-8dda6cfee383"></script>'
ORG_ID=SITE+"/#organization"
WEBSITE_ID=SITE+"/#website"

def _plain(v):
    return html.unescape(re.sub(r"<[^>]+>"," ",str(v or ""))).strip()

def _meta(text,name):
    m=re.search(rf'<meta[^>]+name="{re.escape(name)}"[^>]+content="([^"]*)"',text,re.I)
    if not m:
        m=re.search(rf'<meta[^>]+content="([^"]*)"[^>]+name="{re.escape(name)}"',text,re.I)
    return html.unescape(m.group(1)) if m else ""

def _title(text):
    m=re.search(r"<title>(.*?)</title>",text,re.I|re.S)
    return _plain(m.group(1)) if m else ""

def _h1(text):
    m=re.search(r"<h1[^>]*>(.*?)</h1>",text,re.I|re.S)
    return _plain(m.group(1)) if m else ""

def organization_node():
    return {
      "@type":"Organization","@id":ORG_ID,"name":"Open Model Weights","url":SITE+"/",
      "description":"Field-verified intelligence and machine-readable evidence for open-weight AI models.",
      "logo":{"@type":"ImageObject","url":SITE+"/logo.png","width":512,"height":512},
      "sameAs":["https://github.com/openmodelweights/openmodelweights","https://huggingface.co/openmodelweights"]
    }

def website_node():
    return {
      "@type":"WebSite","@id":WEBSITE_ID,"url":SITE+"/","name":"Open Model Weights",
      "publisher":{"@id":ORG_ID},"inLanguage":"en"
    }

def breadcrumb_node(canonical,items):
    return {
      "@type":"BreadcrumbList","@id":canonical+"#breadcrumb",
      "itemListElement":[
        {"@type":"ListItem","position":i+1,"name":name,"item":url}
        for i,(name,url) in enumerate(items)
      ]
    }

def page_node(canonical,title,desc,page_type="WebPage",breadcrumb=None,main_entity=None):
    node={
      "@type":page_type,"@id":canonical+"#webpage","url":canonical,
      "name":title,"description":desc,"isPartOf":{"@id":WEBSITE_ID},"inLanguage":"en"
    }
    if breadcrumb: node["breadcrumb"]={"@id":breadcrumb["@id"]}
    if main_entity: node["mainEntity"]={"@id":main_entity}
    return node

def tech_article_node(canonical,title,desc,generated):
    return {
      "@type":"TechArticle","@id":canonical+"#article","headline":title,"description":desc,
      "url":canonical,"dateModified":date(generated),"author":{"@id":ORG_ID},
      "publisher":{"@id":ORG_ID},"inLanguage":"en"
    }

def dataset_distribution(url,name="Machine-readable JSON"):
    return {"@type":"DataDownload","name":name,"encodingFormat":"application/json","contentUrl":url}

def registry_catalog_node(model_count=None):
    node={
      "@type":"DataCatalog","@id":SITE+"/models/#catalog","name":"Open Model Weights Registry",
      "description":"Field-verified registry of open-weight AI model records with source-linked technical, legal, hardware, lineage, runtime and freshness fields.",
      "url":SITE+"/models/","provider":{"@id":ORG_ID}
    }
    if model_count is not None:
        node["numberOfItems"]=model_count
    node["dataset"]={
      "@type":"Dataset","@id":SITE+"/registry.json#dataset","name":"Open Model Weights registry data",
      "description":"Canonical machine-readable Open Model Weights registry.",
      "url":SITE+"/registry.json","provider":{"@id":ORG_ID},
      "distribution":[
        dataset_distribution(SITE+"/registry.json","Full registry JSON"),
        dataset_distribution(SITE+"/api/v1/models.json","Compact model index JSON")
      ]
    }
    return node

def model_dataset_node(m,generated):
    canonical=SITE+f'/models/{m["id"]}/'
    lic=m.get("license") or {}
    ver=m.get("verification") or {}
    hub=m.get("hub") or {}
    weights=m.get("weights") or {}
    model=m.get("model") or {}
    desc=f'Field-verified record for {m.get("name")} with source-linked weight artifacts, license, context, formats, lineage, runtime and hardware evidence.'
    node={
      "@type":"Dataset","@id":canonical+"#dataset","name":f'{m.get("name")} verified model record',
      "description":desc,"url":canonical,"identifier":m.get("id"),
      "provider":{"@id":ORG_ID},"includedInDataCatalog":{"@id":SITE+"/models/#catalog"},
      "isAccessibleForFree":True,"dateModified":date(ver.get("checked_at") or generated),
      "measurementTechnique":"Field-by-field source verification against the listed source repository",
      "variableMeasured":["Parameters","Context window","License","Weight artifacts","Formats","Precision availability","Lineage","Runtime support","Weight-only memory estimate"],
      "distribution":[dataset_distribution(SITE+f'/api/v1/models/{m["id"]}.json',"Verified model record JSON")]
    }
    repo=weights.get("repository")
    if repo: node["isBasedOn"]=repo
    sha=hub.get("sha")
    if sha: node["version"]=sha
    lname=lic.get("name")
    lurl=lic.get("url")
    if lurl and str(lurl).startswith(("http://","https://")): node["license"]=lurl
    elif lname and lname!="Not declared": node["license"]=lname
    keywords=[m.get("developer"),m.get("family"),model.get("modality")]+list(weights.get("formats") or [])
    node["keywords"]=[x for x in dict.fromkeys(str(x) for x in keywords if x)]
    return node

def _route_for_path(path):
    rel=path.relative_to(PUBLIC)
    if rel==Path("index.html"): return "/"
    return "/"+str(rel.parent).replace("\\","/").strip("/")+"/"

def _breadcrumbs_for(route,title,model=None):
    home=("Home",SITE+"/")
    if route=="/": return []
    if model and route==f'/models/{model["id"]}/':
        return [home,("Models",SITE+"/models/"),(model.get("name") or title,SITE+route)]
    if model and route==f'/models/{model["id"]}/history/':
        return [home,("Models",SITE+"/models/"),(model.get("name") or model["id"],SITE+f'/models/{model["id"]}/'),("History",SITE+route)]
    if route.startswith("/diff/") and model:
        return [home,("Models",SITE+"/models/"),(model.get("name") or model["id"],SITE+f'/models/{model["id"]}/'),("Diff",SITE+route)]
    if route.startswith("/developers/") and route!="/developers/":
        return [home,("Developers",SITE+"/developers/"),(title,SITE+route)]
    if route in {"/licenses/","/hardware/","/formats/","/lineage/"}:
        return [home,("Explore",SITE+"/explore/"),(title,SITE+route)]
    label={
      "/models/":"Models","/developers/":"Developers","/explore/":"Explore","/compare/":"Compare",
      "/changes/":"Changes","/sources/":"Sources","/verification/":"Verification",
      "/methodology/":"Methodology","/about/":"About","/api/":"API","/history/":"History",
      "/compatibility/":"Compatibility","/benchmarks/":"Benchmarks","/mcp/":"MCP"
    }.get(route,title)
    return [home,(label,SITE+route)]

def schema_nodes_for_route(route,text,by_id,generated):
    canonical=SITE+route
    title=_title(text) or _h1(text) or "Open Model Weights"
    desc=_meta(text,"description") or "Field-verified intelligence for open-weight AI."
    model=None
    parts=[x for x in route.strip("/").split("/") if x]
    if len(parts)>=2 and parts[0]=="models":
        model=by_id.get(parts[1])
    elif len(parts)>=2 and parts[0]=="diff":
        model=by_id.get(parts[1])
    crumbs=_breadcrumbs_for(route,_h1(text) or title,model)
    breadcrumb=breadcrumb_node(canonical,crumbs) if crumbs else None
    nodes=[]

    if route=="/":
        page=page_node(canonical,title,desc,"WebPage")
        nodes=[organization_node(),website_node(),page]
        return nodes

    if route=="/about/":
        page=page_node(canonical,title,desc,"AboutPage",breadcrumb,ORG_ID)
        nodes=[page,breadcrumb,organization_node()]
        return [x for x in nodes if x]

    if model and route==f'/models/{model["id"]}/':
        dataset=model_dataset_node(model,generated)
        page=page_node(canonical,title,desc,"WebPage",breadcrumb,dataset["@id"])
        return [page,breadcrumb,dataset]

    if model and route==f'/models/{model["id"]}/history/':
        evidence={
          "@type":"Dataset","@id":canonical+"#dataset","name":f'{model.get("name")} observed evidence history',
          "description":desc,"url":canonical,"identifier":model["id"]+"-evidence-history",
          "provider":{"@id":ORG_ID},"dateModified":date(generated),
          "distribution":[dataset_distribution(SITE+f'/api/v1/evidence/{model["id"]}.json',"Evidence ledger JSON")]
        }
        page=page_node(canonical,title,desc,"CollectionPage",breadcrumb,evidence["@id"])
        return [page,breadcrumb,evidence]

    if route=="/models/":
        catalog=registry_catalog_node(len(by_id))
        page=page_node(canonical,title,desc,"CollectionPage",breadcrumb,catalog["@id"])
        return [page,breadcrumb,catalog]

    if route in {"/changes/","/history/","/compatibility/"}:
        data_urls={
          "/changes/":("/api/v1/changes.json","Registry change history"),
          "/history/":("/api/v1/history.json","Evidence-ledger index"),
          "/compatibility/":("/api/v1/compatibility.json","Compatibility graph")
        }
        data_url,data_name=data_urls[route]
        dataset={
          "@type":"Dataset","@id":canonical+"#dataset","name":data_name,"description":desc,
          "url":canonical,"provider":{"@id":ORG_ID},"dateModified":date(generated),
          "distribution":[dataset_distribution(SITE+data_url,data_name+" JSON")]
        }
        page=page_node(canonical,title,desc,"CollectionPage",breadcrumb,dataset["@id"])
        return [page,breadcrumb,dataset]

    if route in {"/sources/","/verification/","/methodology/","/api/","/mcp/","/benchmarks/"}:
        article=tech_article_node(canonical,title,desc,generated)
        page=page_node(canonical,title,desc,"WebPage",breadcrumb,article["@id"])
        return [page,breadcrumb,article]

    collection_routes={"/developers/","/explore/","/licenses/","/hardware/","/formats/","/lineage/"}
    if route in collection_routes or (route.startswith("/developers/") and route!="/developers/"):
        page=page_node(canonical,title,desc,"CollectionPage",breadcrumb)
        return [page,breadcrumb]

    page=page_node(canonical,title,desc,"WebPage",breadcrumb)
    return [page,breadcrumb] if breadcrumb else [page]

def _schema_script(nodes):
    payload={"@context":"https://schema.org","@graph":[x for x in nodes if x]}
    raw=json.dumps(payload,ensure_ascii=False,separators=(",",":")).replace("</","<\\/")
    return f'<script type="application/ld+json">{raw}</script>'

def _ensure_meta(text,canonical,title,desc):
    additions=[]
    text=re.sub(r'<script[^>]+src="https://cloud\.umami\.is/script\.js"[^>]*>\s*</script>','',text,flags=re.I)
    additions.append(UMAMI_ANALYTICS)
    # Normalize site identity so generated pages cannot retain the legacy bar mark.
    text=re.sub(r'<span class="brand-mark brand-mark-small" aria-hidden="true"><i></i><i></i><i></i></span>',
                '<img class="brand-logo brand-logo-small" src="/favicon.svg" width="24" height="24" alt="">',text)
    text=re.sub(r'<span class="brand-mark" aria-hidden="true"><i></i><i></i><i></i></span>',
                '<img class="brand-logo" src="/favicon.svg" width="30" height="30" alt="">',text)

    # Normalize the site identity assets so old/generated pages cannot retain legacy favicon markup.
    text=re.sub(r'<link[^>]+rel=["\'](?:shortcut )?icon["\'][^>]*>','',text,flags=re.I)
    text=re.sub(r'<link[^>]+rel=["\']apple-touch-icon["\'][^>]*>','',text,flags=re.I)
    text=re.sub(r'<link[^>]+rel=["\']manifest["\'][^>]*>','',text,flags=re.I)
    additions.append('<link rel="icon" href="/favicon.svg" type="image/svg+xml">')
    additions.append('<link rel="icon" href="/favicon-48x48.png" sizes="48x48" type="image/png">')
    additions.append('<link rel="shortcut icon" href="/favicon.ico">')
    additions.append('<link rel="manifest" href="/site.webmanifest">')
    if 'name="theme-color"' not in text:
        additions.append('<meta name="theme-color" content="#f7f7f4">')
    if 'rel="canonical"' not in text:
        additions.append(f'<link rel="canonical" href="{esc(canonical)}">')
    if 'name="robots"' not in text:
        additions.append('<meta name="robots" content="index,follow,max-snippet:-1,max-image-preview:large">')
    if 'property="og:type"' not in text:
        additions.append('<meta property="og:type" content="website">')
    if 'property="og:site_name"' not in text:
        additions.append('<meta property="og:site_name" content="Open Model Weights">')
    if 'property="og:title"' not in text:
        additions.append(f'<meta property="og:title" content="{esc(title)}">')
    if 'property="og:description"' not in text:
        additions.append(f'<meta property="og:description" content="{esc(desc)}">')
    if 'property="og:url"' not in text:
        additions.append(f'<meta property="og:url" content="{esc(canonical)}">')
    if 'property="og:image"' not in text:
        additions.append('<meta property="og:image" content="https://openmodelweights.com/social-card.png">')
        additions.append('<meta property="og:image:width" content="1200">')
        additions.append('<meta property="og:image:height" content="630">')
        additions.append('<meta property="og:image:alt" content="Open Model Weights — The evidence layer for open-weight AI">')
    text=re.sub(r'<meta\s+name="twitter:card"\s+content="summary"\s*/?>',
                '<meta name="twitter:card" content="summary_large_image">',text,flags=re.I)
    if 'name="twitter:card"' not in text:
        additions.append('<meta name="twitter:card" content="summary_large_image">')
    if 'name="twitter:title"' not in text:
        additions.append(f'<meta name="twitter:title" content="{esc(title)}">')
    if 'name="twitter:description"' not in text:
        additions.append(f'<meta name="twitter:description" content="{esc(desc)}">')
    if 'name="twitter:image"' not in text:
        additions.append('<meta name="twitter:image" content="https://openmodelweights.com/social-card.png">')
        additions.append('<meta name="twitter:image:alt" content="Open Model Weights — The evidence layer for open-weight AI">')
    if additions and "</head>" in text:
        text=text.replace("</head>","".join(additions)+"</head>",1)
    return text

def apply_structured_data_file(path,by_id,generated):
    if not path.exists(): return
    route=_route_for_path(path)
    text=path.read_text()
    canonical=SITE+route
    title=_title(text) or _h1(text) or "Open Model Weights"
    desc=_meta(text,"description") or "Field-verified intelligence for open-weight AI."
    text=_ensure_meta(text,canonical,title,desc)
    text=re.sub(r'<script\s+type="application/ld\+json">.*?</script>','',text,flags=re.I|re.S)
    script=_schema_script(schema_nodes_for_route(route,text,by_id,generated))
    if "</head>" in text:
        text=text.replace("</head>",script+"</head>",1)
    path.write_text(text)

def apply_structured_data_tree(models,generated):
    by_id={m["id"]:m for m in models}
    for path in PUBLIC.rglob("index.html"):
        apply_structured_data_file(path,by_id,generated)

def head(title,desc,canonical,extra=""):
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="theme-color" content="#f7f7f4"><title>{esc(title)}</title><meta name="description" content="{esc(desc)}"><link rel="canonical" href="{esc(canonical)}"><meta name="robots" content="index,follow,max-snippet:-1"><meta property="og:site_name" content="Open Model Weights"><meta property="og:title" content="{esc(title)}"><meta property="og:description" content="{esc(desc)}"><meta property="og:url" content="{esc(canonical)}">{UMAMI_ANALYTICS}<link rel="stylesheet" href="/styles.css">{extra}</head>'''

def header(active=""):
    links=[("models","/models/","Models"),("explore","/explore/","Explore"),("news","/news/","News"),("developers","/developers/","Developers"),("changes","/changes/","Changes"),("sources","/sources/","Sources")]
    out=[]
    for key,url,label in links:
        cur=' aria-current="page"' if active==key else ""
        out.append(f'<a class="nav-link" href="{url}"{cur}>{label}</a>')
    cur=' aria-current="page"' if active=="compare" else ""
    out.append(f'<a class="nav-link nav-compare" href="/compare/"{cur}>Compare <span aria-hidden="true">→</span></a>')
    mark='<img class="brand-logo" src="/favicon.svg" width="30" height="30" alt="">'
    return '<a class="skip-link" href="#main-content">Skip to content</a><header class="site-header"><a class="brand" href="/" aria-label="Open Model Weights home">'+mark+'<span class="brand-wordmark">Open Model Weights</span></a><nav aria-label="Primary navigation">'+''.join(out)+'</nav></header>'

def footer():
    return '''<footer class="site-footer site-footer-v2"><div class="footer-brand"><div class="footer-brand-line"><img class="brand-logo brand-logo-small" src="/favicon.svg" width="24" height="24" alt=""><strong>Open Model Weights</strong></div><p>Field-verified intelligence for open-weight AI.</p></div><div class="footer-nav"><div class="footer-group"><span>Registry</span><a href="/models/">Models</a><a href="/news/">News</a><a href="/compare/">Compare</a><a href="/changes/">Changes</a><a href="/sources/">Sources</a></div><div class="footer-group"><span>Evidence</span><a href="/verification/">Verification</a><a href="/methodology/">Methodology</a><a href="/history/">History</a><a href="/compatibility/">Compatibility</a></div><div class="footer-group"><span>Machine</span><a href="/api/">API / JSON</a><a href="/mcp/">MCP</a><a href="/registry.json">Registry JSON</a><a href="/benchmarks/">Benchmarks</a></div><div class="footer-group"><span>Project</span><a href="https://github.com/openmodelweights/openmodelweights" rel="noopener">GitHub ↗</a><a href="https://huggingface.co/openmodelweights" rel="noopener">Hugging Face ↗</a></div></div></footer>'''

def trust_strip(checked,full=None,mode=None):
    full=full or checked
    mode_text="Repository revision checked" if mode=="repository-revision-unchanged" else "Field evidence checked"
    return f'''<div class="trust-strip" role="status" aria-label="Verification status"><div class="trust-primary"><span class="trust-signal" aria-hidden="true"><i></i></span><span><small>Evidence status</small><strong>Source-first verified</strong></span></div><div class="trust-item"><small>{esc(mode_text)}</small><strong>{esc(checked)}</strong></div><div class="trust-item"><small>Full field verification</small><strong>{esc(full)}</strong></div><div class="trust-links"><a href="/sources/">Source policy →</a><a href="/methodology/">Methodology →</a></div></div>'''

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
        rows.append(f'''<a class="registry-row discovery-row" href="/models/{esc(m["id"])}/" data-title="{esc(m.get("name",""))}" data-search="{esc(search)}" data-org="{esc(m.get("developer","").lower())}" data-license="{esc(lic.get("name","").lower())}" data-commercial="{esc(com.get("status","unknown").lower())}" data-formats="{esc("|".join(fmt))}" data-params="{esc(p if p is not None else "")}" data-context="{esc(context_value(m) if context_value(m) is not None else "")}" data-memory="{esc(hw.get("int4") if hw.get("int4") is not None else "")}" data-created="{epoch(hub.get("created_at"))}" data-updated="{epoch(hub.get("last_modified"))}" data-downloads="{esc(hub.get("downloads") or 0)}" data-likes="{esc(hub.get("likes") or 0)}"><div><div class="row-title">{esc(m.get("name"))}</div><div class="row-sub">{esc(m.get("developer"))} · {esc((m.get("model") or {}).get("modality",""))} · {esc((m.get("model") or {}).get("parameters",""))}</div><div class="mobile-model-facts"><span>{esc(lic.get("name","Not declared"))}</span><span>{f'INT4 ~{hw.get("int4"):,.1f} GB' if isinstance(hw.get("int4"),(int,float)) else "INT4 —"}</span><span>✓ {esc(date(ver.get("checked_at")))}</span></div></div><div><strong>{esc(context_display(m))}</strong><span>context</span></div><div><span class="pill">{esc(lic.get("name","Not declared"))}</span><small>{esc(com.get("status","unknown").replace("-"," "))}</small></div><div><strong>{f'~{hw.get("int4"):,.1f} GB' if isinstance(hw.get("int4"),(int,float)) else "—"}</strong><span>INT4 weights</span></div><div><strong>{fmt_compact(hub.get("downloads"))}</strong><span>{fmt_compact(hub.get("likes"))} likes</span></div><div><span class="pill verified">Checked {esc(date(ver.get("checked_at")))}</span><small>full: {esc(date(ver.get("full_verified_at") or ver.get("checked_at")))}</small></div></a>''')
    opt_org="".join(f'<option value="{esc(x.lower())}">{esc(x)}</option>' for x in orgs)
    opt_lic="".join(f'<option value="{esc(x.lower())}">{esc(x)}</option>' for x in licenses)
    opt_com="".join(f'<option value="{esc(x.lower())}">{esc(x.replace("-"," ").title())}</option>' for x in commercial)
    opt_fmt="".join(f'<option value="{esc(x)}">{esc(x)}</option>' for x in formats)
    checked=date(generated)
    return f'''{head(f"{len(models)} field-verified open-weight AI models — Open Model Weights",f"Discover and sort {len(models)} verified open-weight AI model records by developer, license, context, parameters, hardware, repository date and popularity.","https://openmodelweights.com/models/",'<script src="/discovery.js?v=1" defer></script>')}<body class="models-page">{header("models")}<main id="main-content"><section class="page-hero discovery-hero discovery-hero-v3"><div class="breadcrumbs"><a href="/">Home</a> / Models</div><p class="eyebrow">OPEN MODEL WEIGHTS · VERIFIED REGISTRY</p><h1>Search the evidence.</h1><p class="lead">{len(models)} field-verified records with source-linked technical, legal, hardware and freshness fields. Unknown values stay explicit rather than being inferred.</p><div class="page-hero-chips"><span>{len(models)} published records</span><span>Daily revision checks</span><span>No composite ranking</span></div></section>{trust_strip(checked,checked)}<section class="section registry-section"><div class="discovery-controls discovery-controls-v3"><div class="discovery-search"><input id="model-search" type="search" placeholder="Search model, developer, family, license or format…"><button id="reset-filters" type="button">Reset filters</button></div><div class="discovery-filters"><select id="org-filter"><option value="">All developers</option>{opt_org}</select><select id="license-filter"><option value="">All licenses</option>{opt_lic}</select><select id="commercial-filter"><option value="">All commercial-use classes</option>{opt_com}</select><select id="format-filter"><option value="">All formats</option>{opt_fmt}</select></div><div class="discovery-sort"><label>Sort <select id="sort-filter"><option value="popular">Popularity · downloads</option><option value="likes">Popularity · likes</option><option value="params-desc">Parameters · largest</option><option value="params-asc">Parameters · smallest</option><option value="context-desc">Context · largest</option><option value="memory-asc">INT4 memory · lowest</option><option value="created-desc">Repository created · newest</option><option value="updated-desc">Publisher updated · newest</option><option value="name">Name · A–Z</option></select></label><label>Per page <select id="page-size"><option>25</option><option selected>50</option><option>100</option></select></label></div><p class="note discovery-note">Repository-created date is only a release-date proxy when no separate structured release date is available.</p></div><div class="registry-list-head"><span>Model</span><span>Context</span><span>License</span><span>INT4</span><span>Popularity</span><span>Freshness</span></div><p id="registry-result-count" class="registry-result-count" aria-live="polite"></p><div class="registry-list">{''.join(rows)}</div><p id="no-results" class="note" hidden>No matching models.</p><div class="registry-pagination"><button id="page-prev" type="button">← Previous</button><span id="page-info"></span><button id="page-next" type="button">Next →</button></div></section></main>{footer()}</body></html>'''

def compare_page(model_count,generated):
    return f'''{head("Compare open-weight AI models — Compare 2.0 | Open Model Weights","Compare two to four verified open-weight models with neutral visual highlighting for technical, legal, hardware, lineage, training, freshness and popularity differences.","https://openmodelweights.com/compare/",'<script src="/compare.js?v=4" defer></script>')}<body class="compare-page">{header("compare")}<main id="main-content"><section class="page-hero compare-hero-v3"><div class="breadcrumbs"><a href="/">Home</a> / Compare</div><p class="eyebrow">OPEN MODEL WEIGHTS · COMPARE</p><h1>Compare the evidence.</h1><p class="lead">Put two to four verified records side by side. Different values are highlighted neutrally — never converted into an overall score or declared winner.</p><div class="page-hero-chips"><span>{model_count} verified records</span><span>2–4 models</span><span>Differences, not rankings</span></div></section>{trust_strip(date(generated),date(generated))}<section class="section compare-section"><div class="compare-picker compare-picker-v3"><div class="compare-picker-head"><div><span>BUILD A COMPARISON</span><strong>Select 2–4 verified records</strong></div><p>Start with two models. Add a third or fourth only when you need a wider field comparison.</p></div><div class="compare-select-grid"><label>Model 1<select id="compare-1" class="compare-select"></select></label><label>Model 2<select id="compare-2" class="compare-select"></select></label><label>Model 3 <span>optional</span><select id="compare-3" class="compare-select"></select></label><label>Model 4 <span>optional</span><select id="compare-4" class="compare-select"></select></label></div><div class="compare-actions"><label class="compare-toggle"><input id="differences-only" type="checkbox"> Show differences only</label><button id="share-comparison" class="button" type="button">Copy comparison link</button></div><p id="compare-summary" class="compare-summary"></p><div id="compare-message" class="compare-message" hidden></div></div><div id="compare-output" class="compare-output" aria-live="polite"><p class="note">Loading verified registry…</p></div></section></main>{footer()}</body></html>'''

def changes_page(feed,models,generated):
    events=feed.get("events",[])[:1000]
    devs=sorted({e.get("developer","") for e in events if e.get("developer")})
    types=sorted({e.get("type","") for e in events if e.get("type")})
    dopt="".join(f'<option value="{esc(x.lower())}">{esc(x)}</option>' for x in devs)
    topt="".join(f'<option value="{esc(x)}">{esc(x.title())}</option>' for x in types)
    items=[]
    for e in events:
        search=" ".join([e.get("model",""),e.get("developer",""),e.get("summary",""),e.get("detail","")]).lower()
        items.append(f'''<article class="change-item" data-at="{esc(e.get("at",""))}" data-type="{esc(e.get("type",""))}" data-developer="{esc(e.get("developer","").lower())}" data-search="{esc(search)}"><time datetime="{esc(e.get("at",""))}" title="{esc(e.get("at",""))}">{esc(short_date(e.get("at")))}</time><div><span class="change-type">{esc(e.get("type",""))}</span><h3><a href="{esc(e.get("url","/changes/"))}">{esc(e.get("model","Registry"))}</a></h3><strong>{esc(e.get("summary",""))}</strong><p>{esc(e.get("detail",""))}</p></div></article>''')
    upstream=[]
    for e in feed.get("publisher_activity",[])[:120]:
        upstream.append(f'''<a class="upstream-row" href="{esc(e.get("url",""))}"><time datetime="{esc(e.get("at",""))}" title="{esc(e.get("at",""))}">{esc(short_date(e.get("at")))}</time><div><strong>{esc(e.get("model",""))}</strong><span>{esc(e.get("developer",""))}</span></div><code>{esc((e.get("sha") or "")[:10])}</code></a>''')
    return f'''{head("What changed? — release and verification history | Open Model Weights","Long-horizon change history for verified open-weight model repositories, metadata and registry verification runs.","https://openmodelweights.com/changes/",'<script src="/changes-v2.js?v=2" defer></script>')}<body class="changes-page">{header("changes")}<main id="main-content"><section class="page-hero changes-hero-v3"><div class="breadcrumbs"><a href="/">Home</a> / Changes</div><p class="eyebrow">OPEN MODEL WEIGHTS · CHANGE HISTORY</p><h1>Track what changed.</h1><p class="lead">Repository revisions, field-level metadata changes and verification runs are retained as evidence over time — not reduced to a one-day snapshot.</p><div class="page-hero-chips"><span>Rolling verification history</span><span>Publisher activity separated</span><span>Short dates · exact timestamps retained</span></div></section>{trust_strip(date(generated),date(generated))}<section class="metric-strip freshness-metrics"><div><span>Events retained</span><strong>{len(feed.get("events",[])):,}</strong></div><div><span>Publisher activity records</span><strong>{len(feed.get("publisher_activity",[])):,}</strong></div><div><span>Models tracked</span><strong>{len(models):,}</strong></div><div><span>History policy</span><strong>up to 5,000 events</strong></div></section><section class="section explorer-section"><div class="explorer-controls change-controls"><input id="changes-search" type="search" placeholder="Search model, developer or change…"><select id="changes-type"><option value="">All change types</option>{topt}</select><select id="changes-developer"><option value="">All developers</option>{dopt}</select><select id="changes-range"><option value="7">Last 7 days</option><option value="30" selected>Last 30 days</option><option value="365">Last 365 days</option><option value="">All retained history</option></select></div><p id="changes-count" class="explorer-result-count"></p><div class="changes-layout"><div><h2 class="explorer-title">Registry changes</h2><div class="change-feed">{''.join(items)}</div></div><aside><h2 class="explorer-title">Publisher repository activity</h2><div class="upstream-feed">{''.join(upstream)}</div><p class="note">Publisher activity is Hugging Face repository metadata. A changed repository timestamp is not automatically treated as a semantic model release.</p></aside></div></section></main>{footer()}</body></html>'''

def sources_page(generated,count):
    tiers=[
      ("01","Repository evidence","Highest priority","Hugging Face model API, exact repository file listing, model card, config files and repository license files. These are the default sources for factual model fields."),
      ("02","Publisher documentation","Primary when repository metadata points outward","Official model documentation, legal terms and organization pages are used when a field is defined outside the source repository."),
      ("03","Derived values","Explicitly labeled","Calculations made from verified inputs, such as weight-only memory estimates from parameter counts. Derived values are never presented as publisher claims."),
    ]
    tier_html="".join(f'<article class="source-tier"><div class="source-tier-number">{n}</div><div><span>{esc(strength)}</span><h2>{esc(title)}</h2><p>{esc(desc)}</p></div></article>' for n,title,strength,desc in tiers)
    fields=[
      ("Weight availability","Hugging Face API + exact repository file list","Recognized weight artifacts must be present; repository existence alone is not enough."),
      ("Weight files","Exact repository file list","Exact filenames are stored rather than inferred from a model name."),
      ("Formats / precision","Repository artifacts + API/config dtype evidence","Observed artifacts and dtype signals only; third-party conversions are not silently attributed to the source repository."),
      ("License","Model-card license metadata + repository LICENSE/licence file","The declared terms are recorded with their evidence URL when available."),
      ("Commercial use","Checked license terms","A structured classification of the checked terms; not legal advice."),
      ("Context window","config.json + explicit model-card statement","Structured config is preferred; explicit publisher text is used when config does not expose the value."),
      ("Parameters","Hugging Face metadata/config + existing publisher declaration","Used for display and derived memory calculations when sufficiently supported."),
      ("Base model / lineage","Declared model-card metadata","No parent model is invented from naming similarity."),
      ("Training recipe","Publisher model card + repository files","Presence/disclosure signal, not an independent reconstruction of training."),
      ("Training data","Publisher/model-card disclosure","“Not disclosed” means not found in the checked standard evidence, not that no disclosure exists anywhere."),
      ("Runtime support","Publisher tags, model card and repository artifacts","Source-derived compatibility signals; Open Model Weights does not imply that every runtime was independently executed."),
      ("Downloads / likes","Hugging Face model API","Popularity metadata; useful for discovery, not a quality score."),
      ("Repository created / updated","Hugging Face model API","Repository creation is labeled as a release-date proxy where no separate structured release date exists."),
      ("Hardware memory","Derived from verified parameter count","Weight-only estimate. KV cache, activations, runtime overhead and sharding are excluded."),
    ]
    field_rows="".join(f'<tr><th scope="row">{esc(field)}</th><td><strong>{esc(source)}</strong></td><td>{esc(rule)}</td></tr>' for field,source,rule in fields)
    limitations=[
      ("No guessing","Unknown or missing values remain explicit instead of being filled from naming conventions or assumptions."),
      ("No silent source substitution","A community conversion is not treated as the publisher’s own weight release unless the record explicitly identifies that repository as its source."),
      ("No deployment guarantee","Hardware estimates are weight-only calculations, not claims that a model will run within that amount of VRAM/RAM."),
      ("No untested runtime claim","Runtime support is source-derived unless Open Model Weights explicitly labels a runtime as independently tested."),
      ("No legal advice","License and commercial-use labels summarize checked terms for comparison; users remain responsible for legal review."),
      ("No quality ranking from popularity","Downloads and likes are discovery signals only. They do not become a model-quality or safety score."),
    ]
    limitation_html="".join(f'<div class="source-limit"><strong>{esc(title)}</strong><p>{esc(body)}</p></div>' for title,body in limitations)
    checked=date(generated)
    return f'''{head("Source policy & verification trust — Open Model Weights","Exact evidence rules behind Open Model Weights: source tiers, field-to-source mapping, freshness, limitations, corrections and reproducibility.","https://openmodelweights.com/sources/")}<body class="sources-page">{header("sources")}<main id="main-content"><section class="page-hero sources-hero sources-hero-v3"><div class="breadcrumbs"><a href="/">Home</a> / Sources</div><p class="eyebrow">SOURCE POLICY · EVIDENCE STANDARD</p><h1>Evidence before inference.</h1><p class="lead">Every published field should be traceable to a source, an explicit classification rule, or a clearly labeled derivation. Unknown values stay unknown.</p><div class="page-hero-chips"><span>Repository evidence first</span><span>Unknown stays unknown</span><span>Derived values labeled</span></div><div class="hero-actions"><a class="button primary" href="/verification/">Open verification report</a><a class="button" href="/api/v1/models.json">Inspect model JSON ↗</a></div></section>{trust_strip(checked,checked)}<section class="section sources-section"><div class="section-head"><div><p class="eyebrow">EVIDENCE HIERARCHY</p><h2>Not all evidence is treated equally.</h2></div><p class="section-kicker">The registry prefers direct repository evidence, then publisher documentation, then transparent derivation.</p></div><div class="source-tier-grid">{tier_html}</div></section><section class="section sources-section"><div class="section-head"><div><p class="eyebrow">FIELD → SOURCE</p><h2>How each claim is established.</h2></div><p class="section-kicker">This mapping is the practical contract behind “field-verified”.</p></div><div class="source-table-wrap"><table class="source-table"><thead><tr><th>Registry field</th><th>Primary evidence</th><th>Rule / limitation</th></tr></thead><tbody>{field_rows}</tbody></table></div></section><section class="section sources-section"><div class="sources-split"><div><p class="eyebrow">VERIFICATION SEMANTICS</p><h2>What “field-verified” means.</h2><p>A published record has passed the verifier for its listed source repository. Verification is field-specific: one field can be verified while another remains “not disclosed”. The label does not mean every fact about a model has been independently reproduced.</p><p><strong>Not disclosed</strong> means the checked standard repository/API/config/model-card evidence did not expose the value. It does not assert that the information exists nowhere else.</p></div><div class="sources-definition"><div><span>Checked</span><strong>{checked}</strong><p>Latest registry verification run represented on this page.</p></div><div><span>Public scope</span><strong>{count:,} records</strong><p>Only candidates that pass the publication verifier count toward the public target.</p></div></div></div></section><section class="section sources-section"><div class="section-head"><div><p class="eyebrow">FRESHNESS</p><h2>Revision checks and full verification are different.</h2></div></div><div class="freshness-flow"><div><span>01</span><strong>Check repository revision</strong><p>The daily pipeline reads the current source-repository revision/SHA and fresh API metadata.</p></div><div><span>02A</span><strong>If unchanged</strong><p>Prior field evidence is retained. The new revision check is recorded separately from the last full field verification.</p></div><div><span>02B</span><strong>If new or changed</strong><p>The pipeline re-fetches the repository evidence needed for a full field-by-field verification.</p></div><div><span>03</span><strong>Record changes</strong><p>Meaningful repository or field changes are added to the rolling change history.</p></div></div><div class="source-callout"><strong>Why this matters</strong><p>At registry scale, repeatedly downloading unchanged model cards, configs and license files adds latency and rate-limit pressure without adding evidence. Revision-aware verification preserves freshness while keeping full verification meaningful.</p><a href="/changes/">Open change history →</a></div></section><section class="section sources-section"><div class="section-head"><div><p class="eyebrow">BOUNDARIES</p><h2>What Open Model Weights does not claim.</h2></div></div><div class="source-limit-grid">{limitation_html}</div></section><section class="section sources-section"><div class="sources-split sources-repro"><div><p class="eyebrow">REPRODUCIBILITY</p><h2>Inspect the same data we publish.</h2><p>The public registry, versioned JSON layer, model schema, OpenAPI description and verification methodology are exposed so researchers and developers can inspect the record structure directly.</p><div class="source-link-grid"><a href="/registry.json"><strong>Registry JSON</strong><span>Canonical full registry →</span></a><a href="/api/"><strong>API / JSON docs</strong><span>Versioned machine-readable layer →</span></a><a href="/api/v1/model.schema.json"><strong>Model schema</strong><span>Record shape →</span></a><a href="/openapi.json"><strong>OpenAPI 3.1</strong><span>Endpoint description →</span></a><a href="/methodology/"><strong>Methodology</strong><span>Verification method →</span></a><a href="/changes/"><strong>Change history</strong><span>Freshness and revisions →</span></a></div></div><aside class="correction-card"><span class="correction-label">FOUND AN ERROR?</span><h2>Corrections should be inspectable too.</h2><p>Report a questionable field, missing source or classification issue in the public repository. Include the model URL, the field in question and the strongest source you have.</p><a class="button primary" href="https://github.com/openmodelweights/openmodelweights/issues/new" rel="noopener">Report a correction ↗</a><a class="text-link" href="https://github.com/openmodelweights/openmodelweights" rel="noopener">Inspect the repository ↗</a></aside></div></section><section class="section sources-section source-identity"><p class="eyebrow">REPOSITORY IDENTITY</p><h2>Source repository ≠ model nationality or guaranteed publisher ownership.</h2><p>At large scale, some indexed repositories are maintained directly by model publishers and others can be community-maintained repositories. Open Model Weights therefore describes the indexed Hugging Face URL as the <strong>source repository</strong> unless publisher ownership is separately established. Organization location, when shown on developer pages, is likewise an organization fact and not a nationality assigned to a model.</p></section></main>{footer()}</body></html>'''

def api_docs(count,generated):
    endpoints=[
      ("/api/v1/meta.json","Registry metadata, count, schema and freshness."),
      ("/api/v1/models.json","Compact machine-readable model index."),
      ("/api/v1/models/{id}.json","Full field-verified record for one model."),
      ("/api/v1/developers.json","Developer aggregation."),
      ("/api/v1/licenses.json","License and commercial-use aggregation."),
      ("/api/v1/changes.json","Rolling release / verification change history."),
      ("/api/v1/history.json","Evidence-ledger index with snapshot/diff counts."),
      ("/api/v1/evidence/{id}.json","Observed evidence snapshots and field-level diffs for one model."),
      ("/api/v1/evidence-runs.json","Index of canonical daily evidence manifests."),
      ("/api/v1/compatibility.json","Structured model/runtime/format/precision/license/memory relationship graph."),
      ("/api/v1/benchmarks.json","Accepted reproducible deployment benchmark results."),
      ("/mcp","Stateless Streamable HTTP MCP endpoint for AI agents."),
      ("/openapi.json","OpenAPI 3.1 description of the static JSON layer."),
      ("/registry.json","Canonical full registry JSON.")
    ]
    rows="".join(f'<div class="api-endpoint"><code>{esc(p)}</code><p>{esc(d)}</p></div>' for p,d in endpoints)
    return f'''{head("Open Model Weights API & JSON documentation","Machine-readable JSON endpoints and schema documentation for the Open Model Weights field-verified registry.","https://openmodelweights.com/api/")}<body class="api-page">{header()}<main id="main-content"><section class="page-hero api-hero-v3"><div class="breadcrumbs"><a href="/">Home</a> / API</div><p class="eyebrow">MACHINE-READABLE LAYER · v1</p><h1>Use the registry as data.</h1><p class="lead">Static, cacheable JSON for {count:,} verified model records plus evidence history, compatibility relationships and benchmark results. The same data is exposed to AI agents through the public MCP endpoint.</p></section>{trust_strip(date(generated),date(generated))}<section class="section api-docs"><div class="api-grid">{rows}</div><div class="content"><h2>Stability</h2><p><code>/api/v1/</code> is the first versioned machine-readable surface. Additive fields may appear without a version bump; breaking shape changes will use a new API version.</p><h2>CORS & caching</h2><p>JSON API paths are configured for cross-origin read access and short public caching. The canonical registry remains available at <code>/registry.json</code>.</p><h2>Evidence semantics</h2><p>Machine-readable values preserve verification status, sources, explicit unknowns and the distinction between repository revision checks and full field verification.</p></div></section></main>{footer()}</body></html>'''

def compact_model(m):
    return {
      "id":m.get("id"),"name":m.get("name"),"developer":m.get("developer"),"family":m.get("family"),"variant":m.get("variant"),
      "model":m.get("model"),"license":m.get("license"),"hardware":m.get("hardware"),
      "formats":(m.get("weights") or {}).get("formats",[]),"repository":(m.get("weights") or {}).get("repository"),
      "lineage":m.get("lineage"),"runtime_support":m.get("runtime_support"),"hub":m.get("hub"),"verification":m.get("verification"),
      "url":f'https://openmodelweights.com/models/{m.get("id")}/',"history_url":f'https://openmodelweights.com/models/{m.get("id")}/history/',"evidence_url":f'https://openmodelweights.com/api/v1/evidence/{m.get("id")}.json'
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
    meta={"api_version":"v1","registry_schema":reg.get("schema_version"),"generated_at":reg.get("generated_at"),"model_count":len(models),"verification":report.get("stats",{}),"links":{"models":"https://openmodelweights.com/api/v1/models.json","changes":"https://openmodelweights.com/api/v1/changes.json","history":"https://openmodelweights.com/api/v1/history.json","compatibility":"https://openmodelweights.com/api/v1/compatibility.json","benchmarks":"https://openmodelweights.com/api/v1/benchmarks.json","mcp":"https://openmodelweights.com/mcp","openapi":"https://openmodelweights.com/openapi.json","registry":"https://openmodelweights.com/registry.json"}}
    (api/"meta.json").write_text(json.dumps(meta,indent=2,ensure_ascii=False)+"\n")
    schema={"$schema":"https://json-schema.org/draft/2020-12/schema","$id":"https://openmodelweights.com/api/v1/model.schema.json","title":"Open Model Weights model record","type":"object","required":["id","name","developer","model","weights","license","verification","sources"],"properties":{"id":{"type":"string"},"name":{"type":"string"},"developer":{"type":"string"},"family":{"type":["string","null"]},"model":{"type":"object"},"weights":{"type":"object"},"license":{"type":"object"},"hardware":{"type":"object"},"lineage":{"type":"object"},"training_assets":{"type":"object"},"runtime_support":{"type":"object"},"hub":{"type":"object"},"verification":{"type":"object"},"sources":{"type":"array"}}}
    (api/"model.schema.json").write_text(json.dumps(schema,indent=2)+"\n")
    openapi={"openapi":"3.1.0","info":{"title":"Open Model Weights JSON API","version":"1.0.0","description":"Static, versioned JSON surface for the field-verified Open Model Weights registry."},"servers":[{"url":"https://openmodelweights.com"}],"paths":{"/api/v1/meta.json":{"get":{"summary":"Registry metadata","responses":{"200":{"description":"Registry metadata"}}}},"/api/v1/models.json":{"get":{"summary":"Compact model index","responses":{"200":{"description":"Model index"}}}},"/api/v1/models/{id}.json":{"get":{"summary":"Full verified model record","parameters":[{"name":"id","in":"path","required":True,"schema":{"type":"string"}}],"responses":{"200":{"description":"Full model record"}}}},"/api/v1/developers.json":{"get":{"summary":"Developer aggregation","responses":{"200":{"description":"Developer aggregation"}}}},"/api/v1/licenses.json":{"get":{"summary":"License aggregation","responses":{"200":{"description":"License aggregation"}}}},"/api/v1/changes.json":{"get":{"summary":"Rolling change history","responses":{"200":{"description":"Change history"}}}},"/api/v1/history.json":{"get":{"summary":"Evidence-ledger index","responses":{"200":{"description":"History index"}}}},"/api/v1/evidence/{id}.json":{"get":{"summary":"Observed model evidence history","parameters":[{"name":"id","in":"path","required":True,"schema":{"type":"string"}}],"responses":{"200":{"description":"Evidence ledger"}}}},"/api/v1/evidence-runs.json":{"get":{"summary":"Daily evidence manifests","responses":{"200":{"description":"Evidence run index"}}}},"/api/v1/compatibility.json":{"get":{"summary":"Compatibility relationship graph","responses":{"200":{"description":"Compatibility graph"}}}},"/api/v1/benchmarks.json":{"get":{"summary":"Accepted deployment benchmark results","responses":{"200":{"description":"Benchmark results"}}}}}}
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

def methodology_page(generated):
    checked=date(generated)
    principles=[
      ("01","Source first","A field starts with observable evidence from the listed source repository or linked publisher documentation — not from naming conventions."),
      ("02","Field by field","Verification applies to individual claims. A record can contain verified fields alongside explicit unknown or not-disclosed values."),
      ("03","Unknown stays unknown","Missing evidence is preserved as missing. Open Model Weights does not fill gaps just to make records look complete."),
      ("04","History compounds","Repository revisions and verified-field changes become observed evidence over time instead of being overwritten by the newest state.")
    ]
    principle_html="".join(f'<article class="method-principle"><span>{n}</span><h3>{esc(title)}</h3><p>{esc(body)}</p></article>' for n,title,body in principles)
    steps=[
      ("01","Discover candidate","Identify a source repository that appears to publish open-weight model artifacts."),
      ("02","Pass publication gate","Require recognized weight artifacts and enough source evidence to create a real model record."),
      ("03","Verify fields","Check repository/API/config/model-card/license evidence field by field."),
      ("04","Classify explicitly","Store verified, declared, derived, not-disclosed or unknown states instead of silently inferring."),
      ("05","Check revisions daily","Read the current repository revision and fresh API metadata on the daily registry run."),
      ("06","Retain changes","When source evidence changes, create new observed history and field-level diffs.")
    ]
    steps_html="".join(f'<div class="method-step"><span>{n}</span><div><strong>{esc(title)}</strong><p>{esc(body)}</p></div></div>' for n,title,body in steps)
    fields=[
      ("Identity & weights","Source repository API + exact file listing","Repository exists, recognized weight artifacts are present, exact filenames are retained."),
      ("License","Model-card metadata + repository license files / linked terms","Declared terms are recorded with evidence. Commercial-use classification is a comparison aid, not legal advice."),
      ("Context & parameters","Structured config/API first; explicit source text second","Structured values are preferred. Naming conventions do not become facts."),
      ("Formats & precision","Observed repository artifacts, filenames and dtype/config signals","Positive signals are recorded. “Not observed” does not mean no third-party conversion exists."),
      ("Lineage","Declared base-model metadata","No parent model is invented from similarity, architecture family or naming."),
      ("Training assets","Repository files + obvious model-card disclosure","Disclosure signals are recorded; Open Model Weights does not reconstruct undisclosed training."),
      ("Runtime support","Source tags, model card and repository artifacts","Compatibility is source-derived unless a runtime is explicitly labeled as independently tested."),
      ("Hardware memory","Derived from verified parameter count","Weight-only estimate: excludes KV cache, activations, runtime overhead and sharding."),
      ("Popularity & freshness","Source repository API metadata","Downloads/likes aid discovery, not quality ranking. Revision checks are distinct from full field verification.")
    ]
    field_rows="".join(f'<tr><th scope="row">{esc(field)}</th><td>{esc(evidence)}</td><td>{esc(rule)}</td></tr>' for field,evidence,rule in fields)
    states=[
      ("Verified","Directly checked against the named evidence source."),
      ("Declared","Present in source metadata or publisher text, but semantically a publisher/source declaration."),
      ("Derived","Calculated from verified inputs and labeled as a derivation."),
      ("Not disclosed","The checked standard evidence did not expose the value."),
      ("Unknown","Available evidence is insufficient for a defensible value.")
    ]
    state_html="".join(f'<div class="method-state"><strong>{esc(name)}</strong><p>{esc(body)}</p></div>' for name,body in states)
    boundaries=[
      ("No guessed completeness","A blank field is preferable to a plausible but unsupported value."),
      ("No publisher ownership assumption","The indexed Hugging Face URL is called the source repository unless publisher ownership is independently established."),
      ("No deployment guarantee","Weight-memory estimates are comparison aids, not claims that a model will run within that amount of RAM or VRAM."),
      ("No untested runtime guarantee","Runtime entries remain source-derived unless an execution test is explicitly documented."),
      ("No legal determination","Commercial-use labels summarize checked terms for comparison and are not legal advice."),
      ("No quality score from popularity","Downloads and likes remain discovery signals and never become a model-quality ranking.")
    ]
    boundary_html="".join(f'<div><strong>{esc(title)}</strong><p>{esc(body)}</p></div>' for title,body in boundaries)
    return f'''{head("Methodology — how Open Model Weights verifies model evidence","The Open Model Weights methodology for source selection, field verification, unknown values, license classification, hardware estimates, freshness, history and reproducibility.","https://openmodelweights.com/methodology/")}<body class="methodology-page">{header()}<main id="main-content"><section class="page-hero methodology-hero"><div class="breadcrumbs"><a href="/">Home</a> / Methodology</div><p class="eyebrow">OPEN MODEL WEIGHTS · EVIDENCE METHODOLOGY</p><h1>Unknown is a valid value.</h1><p class="lead">The registry is designed to maximize useful coverage without converting assumptions into facts. Every important field should resolve to source evidence, an explicit classification rule, a labeled derivation — or an honest unknown.</p><div class="page-hero-chips"><span>Source-first</span><span>Field-level verification</span><span>Daily revision checks</span><span>Observed history</span></div></section>{trust_strip(checked,checked)}<section class="section methodology-principles"><div class="section-head"><div><p class="eyebrow">CORE PRINCIPLES</p><h2>The rules behind every record.</h2></div><p class="section-kicker">The goal is not to make every field look complete. The goal is to make every published claim inspectable.</p></div><div class="method-principle-grid">{principle_html}</div></section><section class="section methodology-pipeline"><div class="section-head"><div><p class="eyebrow">REGISTRY LIFECYCLE</p><h2>From repository to evidence record.</h2></div><p class="section-kicker">Discovery, verification, revision checks and history are separate stages.</p></div><div class="method-pipeline-grid">{steps_html}</div></section><section class="section methodology-fields"><div class="section-head"><div><p class="eyebrow">FIELD → EVIDENCE → RULE</p><h2>How individual claims are established.</h2></div><p class="section-kicker">Verification is specific to the field. One source does not automatically validate the whole record.</p></div><div class="method-table-wrap"><table class="method-table"><thead><tr><th>Field group</th><th>Primary evidence</th><th>Method / boundary</th></tr></thead><tbody>{field_rows}</tbody></table></div></section><section class="section methodology-states"><div class="methodology-split"><div><p class="eyebrow">EVIDENCE STATES</p><h2>“Verified” is not the only honest state.</h2><p>Open Model Weights preserves the difference between something we directly checked, something the source merely declares, something we calculate, and something the available evidence does not establish.</p></div><div class="method-state-grid">{state_html}</div></div></section><section class="section methodology-derived"><div class="section-head"><div><p class="eyebrow">DERIVED VALUES</p><h2>Hardware estimates are deliberately narrow.</h2></div><p class="section-kicker">They estimate storage for model weights only — not end-to-end deployment memory.</p></div><div class="method-formula-grid"><div><span>BF16 / FP16</span><strong>parameters × 2 bytes</strong><p>Approximate weight-only memory for 16-bit weights.</p></div><div><span>FP8 / INT8</span><strong>parameters × 1 byte</strong><p>Approximate weight-only memory for 8-bit weights.</p></div><div><span>INT4</span><strong>parameters × 0.5 byte</strong><p>Approximate weight-only memory for 4-bit weights.</p></div></div><div class="method-callout"><strong>Excluded by design</strong><p>KV cache, activations, optimizer state, runtime overhead, quantization metadata, device placement and sharding are not included. A displayed memory estimate is therefore not a deployment guarantee.</p></div></section><section class="section methodology-freshness"><div class="methodology-split"><div><p class="eyebrow">FRESHNESS & DATES</p><h2>Repository activity and verification are not the same thing.</h2><p>The daily pipeline checks current repository revision and fresh API metadata. If a source revision changes, relevant evidence is fetched again for field verification. The last revision check and the last full field verification are retained as distinct signals.</p></div><div class="method-date-grid"><div><span>Repository revision</span><strong>Freshness signal</strong><p>Used to detect source changes without re-fetching every unchanged artifact.</p></div><div><span>Full field verification</span><strong>Evidence check</strong><p>The most recent run that re-evaluated the relevant record fields.</p></div><div><span>Repository created</span><strong>Release-date proxy</strong><p>Used only when no separate structured release date is available, and labeled as a proxy.</p></div><div><span>Publisher updated</span><strong>Activity metadata</strong><p>A changed timestamp does not automatically become a semantic model release.</p></div></div></div></section><section class="section methodology-boundaries"><div class="method-boundary-panel"><div class="method-boundary-intro"><p class="eyebrow">BOUNDARIES</p><h2>What the registry does not claim.</h2><p>These limits are part of the methodology, not footnotes. They prevent useful discovery signals from being overstated as stronger evidence.</p></div><div class="method-boundary-grid">{boundary_html}</div></div></section><section class="section methodology-repro"><div class="section-head"><div><p class="eyebrow">REPRODUCIBILITY</p><h2>Inspect the evidence layer yourself.</h2></div><p class="section-kicker">The methodology is backed by public data surfaces rather than a closed scoring system.</p></div><div class="method-link-grid"><a href="/sources/"><strong>Source policy</strong><span>Evidence hierarchy and field rules →</span></a><a href="/verification/"><strong>Verification report</strong><span>Current registry verification status →</span></a><a href="/history/"><strong>Evidence Ledger</strong><span>Observed snapshots and field diffs →</span></a><a href="/registry.json"><strong>Registry JSON</strong><span>Canonical machine-readable registry →</span></a><a href="/api/"><strong>API / JSON</strong><span>Versioned data surfaces →</span></a><a href="/openapi.json"><strong>OpenAPI 3.1</strong><span>Machine-readable endpoint description →</span></a></div><div class="method-correction"><div><span>FOUND A QUESTIONABLE FIELD?</span><h3>Corrections should leave an evidence trail too.</h3><p>Report the model, the field in question and the strongest source you have. Public version control keeps changes attributable and inspectable.</p></div><a class="button primary" href="https://github.com/openmodelweights/openmodelweights/issues/new" rel="noopener">Report a correction ↗</a></div></section></main>{footer()}</body></html>'''

def patch_model_page(path,m,generated):
    text=path.read_text()
    text=re.sub(r'(?:<a class="skip-link"[^>]*>.*?</a>)?<header class="site-header">.*?</header>',header("models"),text,count=1,flags=re.S)
    if '<main>' in text:
        text=text.replace('<main>','<main id="main-content">',1)
    text=text.replace("official Hugging Face repository","listed Hugging Face source repository").replace("Official repository ↗","Source repository ↗")
    if 'class="trust-strip"' not in text:
        marker=re.search(r'(<section class="page-hero model-head">.*?</section>)',text,re.S)
        if marker:
            ver=m.get("verification") or {}
            strip=trust_strip(date(ver.get("checked_at") or generated),date(ver.get("full_verified_at") or ver.get("checked_at") or generated),ver.get("mode"))
            text=text[:marker.end()]+strip+text[marker.end():]
    if 'History & diff' not in text:
        compare_link=f'<a class="button compare-model-button" href="/compare/?models={esc(m["id"])}">Compare this model →</a>'
        history_link=f'<a class="button history-model-button" href="/models/{esc(m["id"])}/history/">History & diff →</a>'
        text=text.replace(compare_link,compare_link+history_link,1)
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
        section=route.strip("/").split("/",1)[0] if route.strip("/") else ""
        active=section if section in {"models","explore","developers","changes","sources"} else ""
        route_classes={
          "/developers/":"developers-page","/licenses/":"license-page explorer-product-page",
          "/hardware/":"hardware-page explorer-product-page","/formats/":"formats-page explorer-product-page",
          "/lineage/":"lineage-page explorer-product-page","/verification/":"verification-page",
          "/methodology/":"methodology-page","/about/":"about-page"
        }
        cls=route_classes.get(route)
        if route.startswith("/developers/") and route!="/developers/": cls="developer-page"
        if cls:
            if re.search(r'<body class="[^"]*">',text):
                text=re.sub(r'<body class="([^"]*)">',lambda m:'<body class="'+m.group(1)+(' ' if m.group(1) else '')+cls+'">' if cls not in m.group(1).split() else m.group(0),text,count=1)
            else:
                text=text.replace("<body>",f'<body class="{cls}">',1)
        text=re.sub(r'(?:<a class="skip-link"[^>]*>.*?</a>)?<header class="site-header">.*?</header>',header(active),text,count=1,flags=re.S)
        if '<main>' in text:
            text=text.replace('<main>','<main id="main-content">',1)
        if 'class="page-hero' in text and 'class="trust-strip"' not in text:
            m=re.search(r'(<section class="page-hero[^"]*">.*?</section>)',text,re.S)
            if m:text=text[:m.end()]+generic+text[m.end():]
        if route=="//" or p==PUBLIC/"index.html":
            if 'intelligence-section' not in text:
                m=re.search(r'(<section class="metric-strip">.*?</section>)',text,re.S)
                if m:
                    intelligence='''<section class="section intelligence-section"><div class="section-head"><div><p class="eyebrow">THE EVIDENCE LAYER</p><h2>History that compounds.</h2></div><p class="section-kicker">Lists can be copied. Observed evidence, revision diffs and reproducible deployment data accumulate over time.</p></div><div class="intelligence-grid"><a href="/history/"><span>01</span><strong>Evidence Ledger</strong><p>Versioned field snapshots and model diffs from observed states.</p></a><a href="/compatibility/"><span>02</span><strong>Compatibility Graph</strong><p>Runtime, format, precision, license and memory relationships.</p></a><a href="/benchmarks/"><span>03</span><strong>Deployment Benchmarks</strong><p>Measured runs tied to exact model revisions and hardware.</p></a><a href="/mcp/"><span>04</span><strong>MCP for AI agents</strong><p>Let other AI products query the verified evidence instead of guessing.</p></a></div></section>'''
                    text=text[:m.end()]+intelligence+text[m.end():]
            if 'home-trust' not in text:
                m=re.search(r'(<section class="hero[^"]*">.*?</section>)',text,re.S)
                if m:
                    home=f'<div class="home-trust"><div class="home-trust-brand"><span class="trust-signal" aria-hidden="true"><i></i></span><span><small>Registry signal</small><strong>Field-verified</strong></span></div><div class="home-trust-stat"><small>Last checked</small><strong>{esc(date(generated))}</strong></div><div class="home-trust-stat"><small>Scope</small><strong>700 verified records</strong></div><div class="home-trust-links"><a href="/sources/">Evidence policy →</a><a href="/api/">API / JSON →</a></div></div>'
                    text=text[:m.end()]+home+text[m.end():]
        text=re.sub(r'<footer(?: class="[^"]*")?>.*?</footer>',footer(),text,count=1,flags=re.S)
        p.write_text(text)

def write_brand_assets():
    try:
        from PIL import Image, ImageDraw, ImageFont
    except Exception as exc:
        raise RuntimeError("Pillow is required to render Open Model Weights brand assets") from exc

    size=512
    logo=Image.new("RGBA",(size,size),(0,0,0,0))
    draw=ImageDraw.Draw(logo)
    scale=size/64
    def pts(values):
        return [(int(x*scale),int(y*scale)) for x,y in values]
    layers=[
      ("#116BFF",[(32,5),(56,18),(32,31),(8,18),(32,5)]),
      ("#45C0F2",[(32,18),(56,31),(32,44),(8,31),(32,18)]),
      ("#082B57",[(32,31),(56,44),(32,57),(8,44),(32,31)]),
    ]
    for color,values in layers:
        draw.line(pts(values),fill=color,width=int(5.5*scale),joint="curve")
    draw.line(pts([(32,13),(32,51)]),fill="#0B4FA7",width=int(4*scale))
    for cy,color in ((15,"#116BFF"),(32,"#45C0F2"),(49,"#082B57")):
        radius=4.8*scale; cx=32*scale; yy=cy*scale
        draw.ellipse((cx-radius,yy-radius,cx+radius,yy+radius),fill=color)
    logo.save(PUBLIC/"logo.png",optimize=True)

    width,height=1200,630
    card=Image.new("RGB",(width,height),"#f7f7f4")
    c=ImageDraw.Draw(card)
    c.rounded_rectangle((24,24,width-24,height-24),radius=30,outline="#d9ddd6",width=2,fill="#fbfbf8")
    icon=logo.resize((210,210),Image.Resampling.LANCZOS)
    card.paste(icon,(72,92),icon)
    font_root=Path("/usr/share/fonts/truetype/dejavu")
    try:
        eyebrow=ImageFont.truetype(str(font_root/"DejaVuSans-Bold.ttf"),22)
        title_font=ImageFont.truetype(str(font_root/"DejaVuSans-Bold.ttf"),58)
        sub_font=ImageFont.truetype(str(font_root/"DejaVuSans.ttf"),28)
        small=ImageFont.truetype(str(font_root/"DejaVuSans-Bold.ttf"),18)
    except Exception:
        eyebrow=title_font=sub_font=small=ImageFont.load_default()
    x=340
    c.text((x,110),"OPEN MODEL WEIGHTS",font=eyebrow,fill="#4f5b52")
    c.text((x,165),"The evidence layer",font=title_font,fill="#171a17")
    c.text((x,235),"for open-weight AI.",font=title_font,fill="#171a17")
    c.text((x,338),"Field-verified model intelligence, source trails,",font=sub_font,fill="#5f6860")
    c.text((x,378),"change history and machine-readable access.",font=sub_font,fill="#5f6860")
    c.rounded_rectangle((x,475,x+400,523),radius=24,fill="#171a17")
    c.text((x+22,487),"SOURCE-FIRST · VERIFIED DAILY",font=small,fill="#f5f7f3")
    c.text((x,548),"openmodelweights.com",font=small,fill="#116BFF")
    card.save(PUBLIC/"social-card.png",optimize=True)

def patch_robots():
    p=PUBLIC/"robots.txt"
    text=p.read_text() if p.exists() else "User-agent: *\nAllow: /\n"
    lines=[line.rstrip() for line in text.splitlines()]
    for sitemap in ("https://openmodelweights.com/sitemap.xml","https://openmodelweights.com/news-sitemap.xml"):
        line="Sitemap: "+sitemap
        if line not in lines:
            lines.append(line)
    p.write_text("\n".join(lines).rstrip()+"\n")

def patch_sitemap(generated):
    p=PUBLIC/"sitemap.xml"
    if not p.exists():return
    text=p.read_text()
    for u in ("/sources/","/api/","/history/","/compatibility/","/benchmarks/","/mcp/"):
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
    if "## Evidence intelligence" not in text:
        text+=f"""\n## Evidence intelligence
- https://openmodelweights.com/history/ — observed evidence history and model diffs
- https://openmodelweights.com/compatibility/ — compatibility graph
- https://openmodelweights.com/benchmarks/ — reproducible deployment benchmarks
- https://openmodelweights.com/api/v1/evidence-runs.json — daily evidence manifests
- https://openmodelweights.com/api/v1/compatibility.json — machine-readable compatibility graph
- https://openmodelweights.com/mcp — MCP Streamable HTTP endpoint
- https://openmodelweights.com/mcp/ — MCP documentation
"""
    p.write_text(text)

def main():
    reg=json.loads(REGISTRY.read_text());models=reg.get("models",[])
    report=json.loads(REPORT.read_text()) if REPORT.exists() else {}
    feed=json.loads(CHANGE_FEED.read_text()) if CHANGE_FEED.exists() else {"events":[],"publisher_activity":[]}
    generated=reg.get("generated_at") or dt.datetime.now(dt.timezone.utc).isoformat()
    reg["schema_version"]="0.8.0"
    reg["model_count"]=len(models)
    reg["freshness"]={"last_registry_run":generated,"policy":"daily repository revision check; full field verification on changed/new repositories"}
    reg["api"]={"version":"v1","documentation":"https://openmodelweights.com/api/","models":"https://openmodelweights.com/api/v1/models.json","changes":"https://openmodelweights.com/api/v1/changes.json","history":"https://openmodelweights.com/api/v1/history.json","compatibility":"https://openmodelweights.com/api/v1/compatibility.json","benchmarks":"https://openmodelweights.com/api/v1/benchmarks.json","openapi":"https://openmodelweights.com/openapi.json"}
    reg["intelligence"]={"history":"https://openmodelweights.com/history/","compatibility":"https://openmodelweights.com/compatibility/","benchmarks":"https://openmodelweights.com/benchmarks/","mcp":"https://openmodelweights.com/mcp"}
    REGISTRY.write_text(json.dumps(reg,indent=2,ensure_ascii=False)+"\n")
    write_brand_assets()
    patch_robots()

    (PUBLIC/"models"/"index.html").write_text(model_discovery_page(models,generated))
    d=PUBLIC/"compare";d.mkdir(parents=True,exist_ok=True);(d/"index.html").write_text(compare_page(len(models),generated))
    d=PUBLIC/"changes";d.mkdir(parents=True,exist_ok=True);(d/"index.html").write_text(changes_page(feed,models,generated))
    d=PUBLIC/"sources";d.mkdir(parents=True,exist_ok=True);(d/"index.html").write_text(sources_page(generated,len(models)))
    d=PUBLIC/"api";d.mkdir(parents=True,exist_ok=True);(d/"index.html").write_text(api_docs(len(models),generated))
    d=PUBLIC/"methodology";d.mkdir(parents=True,exist_ok=True);(d/"index.html").write_text(methodology_page(generated))
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
