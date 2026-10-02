#!/usr/bin/env python3
# Portal extras renderer
from __future__ import annotations

import html
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "public"
REGISTRY = PUBLIC / "registry.json"

DEVELOPER_LOCATIONS = {
    "NVIDIA": {
        "flag":"🇺🇸","country":"United States","country_code":"US",
        "location":"Santa Clara, California, United States",
        "label":"Corporate headquarters","organization":"NVIDIA",
        "sources":[{"label":"NVIDIA — Contact / Corporate location","url":"https://www.nvidia.com/en-us/contact/"}]
    },
    "Mistral AI": {
        "flag":"🇫🇷","country":"France","country_code":"FR",
        "location":"Paris, France",
        "label":"Registered office","organization":"Mistral AI",
        "sources":[{"label":"Mistral AI — Legal terms","url":"https://legal.mistral.ai/terms/eu-consumers-terms-of-service/"}]
    },
    "Qwen": {
        "flag":"🇨🇳","country":"China","country_code":"CN",
        "location":"Hangzhou, Zhejiang, China",
        "label":"Primary organization location","organization":"Alibaba Group / Qwen",
        "sources":[
            {"label":"Alibaba Group — Global locations","url":"https://www.alibabagroup.com/en-US/global-location"},
            {"label":"Alibaba Group — About / Qwen family","url":"https://home.alibabagroup.com/en-US/about-alibaba"}
        ]
    },
    "Meta": {
        "flag":"🇺🇸","country":"United States","country_code":"US",
        "location":"Menlo Park, California, United States",
        "label":"Corporate address","organization":"Meta Platforms",
        "sources":[{"label":"Meta Investor Relations — Contact the Board","url":"https://investor.atmeta.com/leadership-and-governance/?section=contact"}]
    },
    "Google": {
        "flag":"🇺🇸","country":"United States","country_code":"US",
        "location":"Mountain View, California, United States",
        "label":"Primary organization location (Googleplex)","organization":"Google",
        "sources":[{"label":"Google — Office locations","url":"https://about.google/company-info/locations/"}]
    },
    "DeepSeek": {
        "flag":"🇨🇳","country":"China","country_code":"CN",
        "location":"Hangzhou, China",
        "label":"Primary organization location","organization":"Hangzhou DeepSeek Artificial Intelligence Co., Ltd.",
        "sources":[{"label":"DeepSeek — Terms of Use","url":"https://cdn.deepseek.com/policies/en-US/deepseek-terms-of-use.html"}]
    },
    "OpenAI": {
        "flag":"🇺🇸","country":"United States","country_code":"US",
        "location":"San Francisco, California, United States",
        "label":"US registered office / primary organization location","organization":"OpenAI",
        "sources":[{"label":"OpenAI — US Privacy Policy","url":"https://openai.com/policies/us-privacy-policy/"}]
    }
}

def esc(v):
    return html.escape(str(v if v is not None else ""), quote=True)

def slug(v):
    return re.sub(r"[^a-z0-9]+","-",v.lower()).strip("-")

def nav():
    return header_for("/")

def footer():
    return footer_html()

def head(title, desc, canonical, extra=""):
    return f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="theme-color" content="#f7f7f4"><title>{esc(title)}</title><meta name="description" content="{esc(desc)}"><link rel="canonical" href="{esc(canonical)}"><meta name="robots" content="index,follow,max-snippet:-1"><meta property="og:site_name" content="Open Model Weights"><meta property="og:title" content="{esc(title)}"><meta property="og:description" content="{esc(desc)}"><meta property="og:url" content="{esc(canonical)}"><link rel="stylesheet" href="/styles.css">{extra}</head>'

def header_for(path):
    explore_paths=("/explore/","/licenses/","/hardware/","/formats/","/lineage/")
    active="explore" if path.startswith(explore_paths) else (
        "models" if path.startswith("/models/") else
        "developers" if path.startswith("/developers/") else
        "changes" if path.startswith("/changes/") else
        "verification" if path.startswith("/verification/") else
        "compare" if path.startswith("/compare/") else ""
    )
    links=[
        ("models","/models/","Models"),
        ("explore","/explore/","Explore"),
        ("developers","/developers/","Developers"),
        ("changes","/changes/","Changes"),
        ("verification","/verification/","Verification"),
    ]
    items=[]
    for key,url,label in links:
        current=' aria-current="page"' if active==key else ""
        items.append(f'<a class="nav-link" href="{url}"{current}>{label}</a>')
    current=' aria-current="page"' if active=="compare" else ""
    items.append(f'<a class="nav-link nav-compare" href="/compare/"{current}>Compare <span aria-hidden="true">→</span></a>')
    return '<header class="site-header"><a class="brand" href="/" aria-label="Open Model Weights home">Open Model Weights</a><nav aria-label="Primary navigation">'+''.join(items)+'</nav></header>'

def footer_html():
    return '<footer class="site-footer"><div class="footer-brand"><strong>Open Model Weights</strong><p>Field-verified intelligence for open-weight AI.</p></div><div class="footer-links"><a href="/models/">Models</a><a href="/compare/">Compare</a><a href="/verification/">Verification</a><a href="/methodology/">Methodology</a><a href="/about/">About</a><a href="/registry.json">Registry JSON</a><a href="https://github.com/openmodelweights/openmodelweights" rel="noopener">GitHub ↗</a><a href="https://huggingface.co/openmodelweights" rel="noopener">Hugging Face ↗</a></div></footer>'

def page_path(path):
    rel=path.relative_to(PUBLIC)
    if str(rel)=="index.html":
        return "/"
    return "/"+str(rel.parent).replace("\\","/").strip("/")+"/"

def add_body_class(text, class_name):
    if not class_name:
        return text
    m=re.search(r'<body(?: class="([^"]*)")?>',text)
    if not m:
        return text
    classes=(m.group(1) or "").split()
    if class_name not in classes:
        classes.append(class_name)
    return text[:m.start()]+f'<body class="{" ".join(classes)}">'+text[m.end():]

def compare_page():
    presets = [
        ("Qwen3-32B vs Mistral Small 4","qwen3-32b,mistral-small-4-119b-a6b"),
        ("DeepSeek-R1 vs gpt-oss-120b","deepseek-r1,gpt-oss-120b"),
        ("Gemma 3 vs Llama 3.3","gemma-3-27b-it,llama-3-3-70b-instruct"),
    ]
    links = "".join(f'<a class="compare-preset" href="/compare/?models={esc(ids)}">{esc(label)}</a>' for label,ids in presets)
    return f'''{head("Compare open-weight AI models — license, hardware, formats & lineage | Open Model Weights","Compare two to four field-verified open-weight AI models side by side across license, commercial use, context, hardware, formats, lineage, runtime and training disclosure.","https://openmodelweights.com/compare/",'<script src="/compare.js" defer></script>')}<body>{nav()}<main><section class="page-hero"><div class="breadcrumbs"><a href="/">Home</a> / <a href="/explore/">Explore</a> / Compare</div><p class="eyebrow">COMPARE MODELS · 2–4 VERIFIED RECORDS</p><h1>Put the evidence side by side.</h1><p class="lead">Compare technical, legal and provenance fields from the same verified registry. No composite score and no hidden weighting.</p></section><section class="section compare-section"><div class="compare-picker"><div class="compare-select-grid"><label>Model 1<select id="compare-1" class="compare-select"></select></label><label>Model 2<select id="compare-2" class="compare-select"></select></label><label>Model 3 <span>optional</span><select id="compare-3" class="compare-select"></select></label><label>Model 4 <span>optional</span><select id="compare-4" class="compare-select"></select></label></div><div class="compare-actions"><label class="compare-toggle"><input id="differences-only" type="checkbox"> Show differences only</label><button id="share-comparison" class="button" type="button">Copy comparison link</button></div><div class="compare-presets"><span>Try:</span>{links}</div></div><div id="compare-message" class="compare-message" hidden></div><div id="compare-output" class="compare-output" aria-live="polite"><p class="note">Loading verified registry…</p></div></section></main>{footer()}</body></html>'''

def developer_index(models):
    groups={}
    for m in models:
        groups.setdefault(m["developer"],[]).append(m)
    cards=[]
    for dev,items in sorted(groups.items()):
        loc=DEVELOPER_LOCATIONS.get(dev,{})
        flag=loc.get("flag","")
        location=loc.get("location","Location not yet sourced")
        families=" · ".join(sorted(set(str(x.get("family","")) for x in items))[:5])
        cards.append(f'<a class="developer-card" href="/developers/{slug(dev)}/"><span>{len(items)} field-verified records</span><h2>{flag} {esc(dev)}</h2><p class="developer-location-compact">{esc(location)}</p><p>{esc(families)}</p></a>')
    return f'''{head("Open-weight model developers — Open Model Weights","Browse field-verified open-weight model records by developer and sourced primary organization location.","https://openmodelweights.com/developers/")}<body>{nav()}<main><section class="page-hero"><div class="breadcrumbs"><a href="/">Home</a> / Developers</div><p class="eyebrow">DEVELOPERS</p><h1>Model publishers</h1><p class="lead">{len(groups)} developers across {len(models)} field-verified model records. Location refers to the developer organization, not model nationality.</p></section><section class="section"><div class="developer-grid">{''.join(cards)}</div></section></main>{footer()}</body></html>'''

def developer_page(dev, items):
    loc=DEVELOPER_LOCATIONS.get(dev)
    if loc:
        source_links="".join(f'<a class="evidence-link" href="{esc(s["url"])}" rel="noopener">{esc(s["label"])} ↗</a>' for s in loc.get("sources",[]))
        location_html=f'''<div class="developer-location-card"><div class="developer-flag" aria-hidden="true">{loc.get("flag","")}</div><div><span class="kicker">{esc(loc.get("label","Organization location"))}</span><h2>{esc(loc.get("location",""))}</h2><p><strong>{esc(loc.get("organization",dev))}</strong></p><div class="developer-location-sources">{source_links}</div></div></div><p class="note">This location describes the developer or primary organization. It is not the nationality of a model, dataset, contributor, training run or infrastructure.</p>'''
    else:
        location_html='<p class="note">A sourced primary organization location has not yet been added for this developer.</p>'
    rows=[]
    for m in items:
        ctx=m["model"]["context"]["display"] if isinstance(m["model"].get("context"),dict) else m["model"].get("context")
        rows.append(f'<a class="registry-row" href="/models/{esc(m["id"])}/"><div><div class="row-title">{esc(m["name"])}</div><div class="row-sub">{esc(m["model"].get("modality",""))}</div></div><div>{esc(ctx)}</div><div><span class="pill">{esc(m["license"]["name"])}</span></div><div><span class="pill verified">Field-verified</span></div></a>')
    return f'''{head(f"{dev} open-weight models — Open Model Weights",f"{len(items)} field-verified {dev} model records plus sourced developer organization location.",f"https://openmodelweights.com/developers/{slug(dev)}/")}<body>{nav()}<main><section class="page-hero"><div class="breadcrumbs"><a href="/">Home</a> / <a href="/developers/">Developers</a> / {esc(dev)}</div><p class="eyebrow">FIELD-VERIFIED DEVELOPER INDEX</p><h1>{esc(dev)}</h1><p class="lead">{len(items)} checked model records.</p></section><section class="section developer-location-section"><p class="eyebrow">DEVELOPER HQ / PRIMARY ORGANIZATION LOCATION</p>{location_html}</section><section class="section registry-section"><div class="registry-list">{''.join(rows)}</div></section></main>{footer()}</body></html>'''

def patch_html(path, model_id=None):
    text=path.read_text()
    route=page_path(path)
    text=re.sub(r'<header class="site-header">.*?</header>',header_for(route),text,count=1,flags=re.S)
    text=re.sub(r'<footer(?: class="[^"]*")?>.*?</footer>',footer_html(),text,count=1,flags=re.S)
    if route=="/":
        text=add_body_class(text,"home-page")
    elif route=="/explore/":
        text=add_body_class(text,"explore-page")
    elif route=="/compare/":
        text=add_body_class(text,"compare-page")
    elif route.startswith("/models/") and route!="/models/":
        text=add_body_class(text,"model-detail-page")
    if model_id and 'Compare this model' not in text:
        pat=r'(<a class="button primary" href="[^"]+" rel="noopener">Official repository ↗</a>)'
        text=re.sub(pat,rf'\1<a class="button compare-model-button" href="/compare/?models={model_id}">Compare this model →</a>',text,count=1)
    path.write_text(text)

def patch_home():
    p=PUBLIC/"index.html"
    if not p.exists(): return
    text=p.read_text()
    if 'href="/compare/"' not in text:
        text=text.replace('</nav></header>','<a href="/compare/">Compare</a></nav></header>',1)
    marker='<div class="mini-tool-grid">'
    card='<a class="mini-tool" href="/compare/"><strong>Compare Models</strong><span>2–4 models side by side →</span></a>'
    if marker in text and card not in text:
        text=text.replace(marker,marker+card,1)
    text=add_body_class(text,"home-page")
    p.write_text(text)

def patch_explore():
    p=PUBLIC/"explore"/"index.html"
    if not p.exists(): return
    text=p.read_text().replace('Five views over the same field-verified dataset','Six views over the same field-verified dataset')
    card='<a class="tool-card" href="/compare/"><span>2–4</span><h2>Compare Models</h2><p>Compare verified models side by side across technical, legal and provenance fields.</p><strong>Open comparison →</strong></a>'
    marker='<div class="tool-grid">'
    if card not in text and marker in text:
        text=text.replace(marker,marker+card,1)
    labels={
        "/compare/":"MODELS",
        "/licenses/":"LICENSES",
        "/hardware/":"MODELS WITH ESTIMATES",
        "/formats/":"FORMATS",
        "/lineage/":"MODELS WITH LINEAGE",
        "/changes/":"FEED EVENTS",
    }
    for href,label in labels.items():
        pat=rf'(<a class="tool-card" href="{re.escape(href)}"><span)(?: class="tool-stat")?>([^<]+)</span>'
        def stat_label(m):
            value=m.group(2).strip()
            suffix="FEED EVENT" if href=="/changes/" and value=="1" else label
            return f'{m.group(1)} class="tool-stat">{value} {suffix}</span>'
        text=re.sub(pat,stat_label,text,count=1)
    text=add_body_class(text,"explore-page")
    p.write_text(text)

def patch_sitemap():
    p=PUBLIC/"sitemap.xml"
    if not p.exists(): return
    text=p.read_text()
    loc='<url><loc>https://openmodelweights.com/compare/</loc></url>'
    if 'https://openmodelweights.com/compare/' not in text:
        text=text.replace('</urlset>',loc+'\n</urlset>')
    p.write_text(text)

def patch_llms():
    p=PUBLIC/"llms.txt"
    if not p.exists(): return
    text=p.read_text()
    line='- https://openmodelweights.com/compare/ — compare 2–4 verified model records side by side\n'
    if line not in text:
        text=text.replace('## Explorers\n','## Explorers\n'+line)
    p.write_text(text)

def main():
    reg=json.loads(REGISTRY.read_text())
    models=reg.get("models",[])
    reg["schema_version"]="0.5.0"
    reg["developers"]={name:{k:v for k,v in meta.items() if k!="flag"} for name,meta in DEVELOPER_LOCATIONS.items()}
    reg.setdefault("explorers",{})["compare"]="https://openmodelweights.com/compare/"
    REGISTRY.write_text(json.dumps(reg,indent=2,ensure_ascii=False)+"\n")

    schema_path=PUBLIC/"registry.schema.json"
    if schema_path.exists():
        schema=json.loads(schema_path.read_text())
        schema["title"]="Open Model Weights Registry v0.5"
        schema.setdefault("properties",{})["developers"]={"type":"object"}
        schema_path.write_text(json.dumps(schema,indent=2)+"\n")

    compare_dir=PUBLIC/"compare";compare_dir.mkdir(parents=True,exist_ok=True)
    (compare_dir/"index.html").write_text(compare_page())

    groups={}
    for m in models: groups.setdefault(m["developer"],[]).append(m)
    dev_root=PUBLIC/"developers";dev_root.mkdir(parents=True,exist_ok=True)
    (dev_root/"index.html").write_text(developer_index(models))
    for dev,items in groups.items():
        d=dev_root/slug(dev);d.mkdir(parents=True,exist_ok=True)
        (d/"index.html").write_text(developer_page(dev,items))

    for p in PUBLIC.rglob("index.html"):
        mid=p.parent.name if p.parent.parent.name=="models" else None
        patch_html(p,mid)

    patch_home()
    patch_explore()
    patch_sitemap()
    patch_llms()
    print(json.dumps({"compare":True,"developer_locations":len(DEVELOPER_LOCATIONS),"models":len(models)},indent=2))

if __name__=="__main__":
    main()
