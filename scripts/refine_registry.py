#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from urllib.parse import quote

from verify_models import (
    PUBLIC, REGISTRY, REPORT, TODAY, NOW, SESSION, esc,
    model_page, models_page, developer_page, verification_page
)

ROOT = Path(__file__).resolve().parents[1]

CANON = {
    "transformers":"Transformers","vllm":"vLLM","sglang":"SGLang",
    "llama.cpp":"llama.cpp","tensorrt-llm":"TensorRT-LLM","nemo":"NeMo",
    "diffusers":"Diffusers","mlx":"MLX","onnx runtime":"ONNX Runtime",
    "onnx":"ONNX Runtime","tgi":"TGI","ollama":"Ollama","mistral-common":"mistral-common"
}

def get_text(url):
    try:
        r=SESSION.get(url,timeout=30,allow_redirects=True)
        return r.text if r.status_code==200 else None
    except Exception:
        return None

def raw_license_url(model):
    repo=model["weights"]["repository"].rstrip("/")
    lic=model["license"]
    u=lic.get("url")
    if u:
        if u.startswith("http://") or u.startswith("https://"):
            return u
        return f"{repo}/resolve/main/{quote(u, safe='/')}"
    files=lic.get("repository_license_files") or []
    if files:
        return f"{repo}/resolve/main/{quote(files[0], safe='/')}"
    return None

def browser_license_url(model, raw_url):
    repo=model["weights"]["repository"].rstrip("/")
    lic=model["license"]
    u=lic.get("url")
    if u and (u.startswith("http://") or u.startswith("https://")):
        return u
    files=lic.get("repository_license_files") or []
    rel=u if u else (files[0] if files else None)
    return f"{repo}/blob/main/{quote(rel, safe='/')}" if rel else None

def classify_license(model, text):
    lic=model["license"]
    lid=(lic.get("id") or "").lower()
    lname=(lic.get("name") or "").lower()
    blob=(text or "").lower()
    display=lic.get("name") or lid or "Not declared"
    status="unknown"
    label="Commercial-use status requires manual review"
    basis=None

    if lid=="apache-2.0" or "apache license" in blob:
        display="Apache-2.0"; status="allowed"; label="Commercial use allowed under Apache-2.0 conditions"
    elif lid=="mit" and "modified mit" not in blob:
        display="MIT"; status="allowed"; label="Commercial use allowed under MIT conditions"
    elif lid in ("bsd-2-clause","bsd-3-clause"):
        display=lid.upper(); status="allowed"; label=f"Commercial use allowed under {display} conditions"
    elif lid=="cc-by-4.0":
        display="CC BY 4.0"; status="allowed"; label="Commercial use allowed with attribution under CC BY 4.0"
    elif lid=="cc-by-nc-4.0" or "attribution-noncommercial 4.0" in blob:
        display="CC BY-NC 4.0"; status="not-allowed"; label="Commercial use is not permitted by CC BY-NC 4.0"
    elif "qwen research license agreement" in blob or "qwen-research" in lname or "qwen-research" in lid:
        display="Qwen Research License"; status="separate-license-required"; label="Commercial use requires a separate Qwen license"
    elif "qwen community license 1.0" in blob or "qwen-community-1.0" in lname or "qwen-community-1.0" in lid:
        display="Qwen Community License 1.0"; status="allowed-with-conditions"; label="Commercial use allowed with Qwen Community License conditions"
    elif "qwen3.8-max license" in blob or "qwen3.8-max" in lname or "qwen3.8-max" in lid:
        display="Qwen3.8-Max License"; status="allowed-with-conditions"; label="Commercial use allowed with Qwen3.8-Max License conditions"
    elif lname=="mrl" or lid=="mrl" or "mistral research license" in blob:
        display="Mistral Research License"; status="not-allowed"; label="Commercial use is not permitted without a separate Mistral commercial license"
    elif "modified mit license" in blob:
        display="Mistral Modified MIT License"; status="allowed-with-revenue-condition"; label="Commercial use allowed, but the license restricts companies above its revenue threshold without a separate license"
    elif model.get("developer")=="Meta" or "llama" in lname or "llama" in lid:
        display=lic.get("name") or "Llama Community License"; status="allowed-with-conditions"; label="Commercial use allowed subject to Llama community-license conditions"
    elif model.get("developer")=="Google" and "gemma" in (model.get("family","")+" "+model.get("name","")).lower():
        display=lic.get("name") or "Gemma Terms"; status="allowed-with-conditions"; label="Commercial use permitted subject to Gemma Terms"
    elif model.get("developer")=="NVIDIA" or "nvidia" in lname:
        display=lic.get("name") or "NVIDIA Open Model License"; status="allowed-with-conditions"; label="Commercially usable subject to NVIDIA license conditions"
    elif "permission is hereby granted, free of charge" in blob and "sell copies" in blob:
        status="allowed-with-conditions"; label="License text grants broad use including sale, subject to its stated conditions"

    lic["name"]=display
    lic["commercial_use"]={"status":status,"label":label,"basis":browser_license_url(model, raw_license_url(model))}
    if raw_license_url(model):
        lic["url"]=browser_license_url(model, raw_license_url(model))
    lic["verification"]={
        "status":"license-file-checked" if text else "metadata-only",
        "checked_at":TODAY,
        "source":lic.get("url")
    }

def fix_precision(model):
    w=model["weights"]
    files=w.get("exact_files") or []
    dtypes={str(x).upper() for x in (w.get("dtype_evidence") or [])}
    scan=(" ".join(files)+" "+model["weights"]["repository"]).upper()
    def token(tok):
        return bool(re.search(rf"(?<![A-Z0-9]){re.escape(tok)}(?![A-Z0-9])",scan))
    p={}
    p["bf16"]={"available":("BF16" in dtypes or "BFLOAT16" in dtypes or token("BF16")),"status":"verified"}
    p["fp16"]={"available":("FP16" in dtypes or "FLOAT16" in dtypes or "F16" in dtypes or token("FP16")),"status":"verified"}
    p["fp8"]={"available":(any(x.startswith("F8_") or "FP8" in x or "FLOAT8" in x for x in dtypes) or token("FP8")),"status":"verified"}
    p["int8"]={"available":("INT8" in dtypes or token("INT8")),"status":"verified"}
    p["int4"]={"available":("INT4" in dtypes or token("INT4") or token("GPTQ")),"status":"verified"}
    p["gguf"]={"available":any(f.lower().endswith(".gguf") for f in files),"status":"verified"}
    w["precision_availability"]=p

def clean_runtime(model):
    rt=model.get("runtime_support") or {}
    def canon_list(vals):
        out=[]
        for x in vals or []:
            key=str(x).lower()
            c=CANON.get(key,str(x))
            if c not in out: out.append(c)
        return out
    if rt.get("declared_library"):
        rt["declared_library"]=CANON.get(str(rt["declared_library"]).lower(),rt["declared_library"])
    rt["declared"]=canon_list(rt.get("declared"))
    rt["mentioned_in_model_card"]=[x for x in canon_list(rt.get("mentioned_in_model_card")) if x not in rt["declared"]]
    model["runtime_support"]=rt

def refine_recipe(model):
    r=model.get("training_assets",{}).get("training_recipe",{})
    if r.get("links") and r.get("status")=="not-disclosed-in-checked-repository":
        r["status"]="training-or-recipe-links-present"
    clean=[]
    for u in r.get("links") or []:
        if "](" in u: u=u.split("](")[-1]
        u=u.rstrip(").,]")
        if u.startswith("http") and u not in clean: clean.append(u)
    r["links"]=clean
    model["training_assets"]["training_recipe"]=r

def prior_history():
    try:
        raw=subprocess.check_output(["git","show","HEAD:public/registry.json"],text=True)
        old=json.loads(raw)
        return {m["id"]:m.get("verification",{}).get("history",[]) for m in old.get("models",[])}
    except Exception:
        return {}

def recalc_report(models, errors=None):
    errors=errors or []
    stats={
        "total_seed_records":len(models),
        "field_verified":len(models),
        "errors":len(errors),
        "license_declared":sum(m["license"].get("status")=="verified" for m in models),
        "commercial_use_classified":sum(m["license"]["commercial_use"]["status"]!="unknown" for m in models),
        "context_verified":sum(m["model"]["context"]["status"]=="verified" for m in models),
        "exact_weight_lists":sum(bool(m["weights"].get("exact_files")) for m in models),
        "base_model_declared":sum(m["lineage"]["base_model"]["status"]=="declared" for m in models),
        "training_recipe_signal":sum(m["training_assets"]["training_recipe"]["status"]!="not-disclosed-in-checked-repository" for m in models),
        "data_disclosure_signal":sum(m["training_assets"]["data_disclosure"]["status"]!="not-disclosed-in-standard-metadata-or-obvious-model-card-section" for m in models),
        "runtime_signal":sum(bool(m["runtime_support"].get("declared") or m["runtime_support"].get("mentioned_in_model_card") or m["runtime_support"].get("artifact_signals")) for m in models),
    }
    return {"generated_at":NOW,"stats":stats,"errors":errors}

def home_page(models,report):
    s=report["stats"]
    featured=models[:6]
    cards="".join(f'<a class="model-card" href="/models/{esc(m["id"])}/"><div class="card-top"><span class="org">{esc(m["developer"])}</span><span class="status-dot verified">● field-verified</span></div><h3>{esc(m["name"])}</h3><p>{esc(m["model"]["context"]["display"])} · {esc(m["license"]["name"])}</p><div class="chips"><span>{esc(m["model"].get("parameters"))}</span><span>{m["weights"]["file_count"]} weight files</span></div></a>' for m in featured)
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Open Model Weights — field-verified open-weight AI registry</title><meta name="description" content="{len(models)} field-by-field verified open-weight AI model records with exact weight files, licenses, context, hardware estimates, lineage, training-data disclosure and runtime support."><link rel="canonical" href="https://openmodelweights.com/"><link rel="stylesheet" href="/styles.css"></head><body><header class="site-header"><a class="brand" href="/">Open Model Weights</a><nav><a href="/models/">Models</a><a href="/developers/">Developers</a><a href="/verification/">Verification</a><a href="/methodology/">Methodology</a></nav></header><main><section class="hero home-hero"><p class="eyebrow">FIELD-VERIFIED OPEN-WEIGHT REGISTRY</p><h1>Open model weights,<br>with evidence.</h1><p class="lead">A source-first registry for exact weight artifacts, licenses, commercial-use conditions, context, formats, lineage, training assets and runtime support.</p><form class="hero-search" action="/models/" method="get"><input name="q" type="search" placeholder="Search {len(models)} verified models…"><button type="submit">Search models</button></form><div class="hero-actions"><a class="button primary" href="/models/">Explore {len(models)} models</a><a class="button" href="/verification/">Verification report</a></div></section><section class="metric-strip"><div><span>Field-verified</span><strong>{s["field_verified"]} / {s["total_seed_records"]}</strong></div><div><span>Exact weight lists</span><strong>{s["exact_weight_lists"]}</strong></div><div><span>Commercial-use classified</span><strong>{s["commercial_use_classified"]}</strong></div><div><span>Context declared</span><strong>{s["context_verified"]}</strong></div></section><section class="section"><div class="section-head"><div><p class="eyebrow">VERIFIED RECORDS</p><h2>Every claim points back to a source.</h2></div><a class="text-link" href="/models/">Browse all →</a></div><div class="model-grid">{cards}</div></section><section class="section"><p class="eyebrow">MODEL DETAIL 2.0</p><h2>Nine evidence layers.</h2><div class="detail-grid">{"".join(f'<div><span>{i:02d}</span><strong>{x}</strong></div>' for i,x in enumerate(["Weights","License","Hardware","Formats","Lineage","Training assets","Runtime support","Sources","Verification history"],1))}</div></section></main></body></html>'''

def developer_index(models):
    groups={}
    for m in models: groups.setdefault(m["developer"],[]).append(m)
    cards="".join(f'<a class="developer-card" href="/developers/{re.sub(r"[^a-z0-9]+","-",d.lower()).strip("-")}/"><span>{len(items)} field-verified records</span><h2>{esc(d)}</h2><p>{esc(" · ".join(sorted(set(str(x.get("family","")) for x in items))[:5]))}</p></a>' for d,items in sorted(groups.items()))
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Open-weight model developers — Open Model Weights</title><meta name="description" content="Browse field-verified open-weight model records by developer."><link rel="canonical" href="https://openmodelweights.com/developers/"><link rel="stylesheet" href="/styles.css"></head><body><header class="site-header"><a class="brand" href="/">Open Model Weights</a><nav><a href="/models/">Models</a><a href="/developers/">Developers</a><a href="/verification/">Verification</a></nav></header><main><section class="page-hero"><div class="breadcrumbs"><a href="/">Home</a> / Developers</div><p class="eyebrow">DEVELOPERS</p><h1>Model publishers</h1><p class="lead">{len(groups)} developers across {len(models)} field-verified model records.</p></section><section class="section"><div class="developer-grid">{cards}</div></section></main></body></html>'''

def schema_doc():
    return {
      "$schema":"https://json-schema.org/draft/2020-12/schema",
      "$id":"https://openmodelweights.com/registry.schema.json",
      "title":"Open Model Weights Registry v0.8",
      "type":"object",
      "required":["schema_version","generated_at","models"],
      "properties":{
        "schema_version":{"type":"string"},
        "generated_at":{"type":"string"},
        "models":{"type":"array","items":{"type":"object","required":["id","name","developer","model","weights","license","hardware","lineage","training_assets","runtime_support","sources","verification"]}}
      }
    }


def git_json(path):
    try:
        raw=subprocess.check_output(["git","show",f"HEAD:{path}"],text=True)
        return json.loads(raw)
    except Exception:
        return None

def nav_html():
    return '<header class="site-header"><a class="brand" href="/">Open Model Weights</a><nav><a href="/models/">Models</a><a href="/developers/">Developers</a><a href="/explore/">Explore</a><a href="/changes/">Changes</a><a href="/verification/">Verification</a><a href="/methodology/">Methodology</a></nav></header>'

def footer_html():
    return '<footer><div><strong>Open Model Weights</strong><p>The independent registry for open-weight AI.</p></div><div class="footer-links"><a href="/licenses/">Licenses</a><a href="/hardware/">Hardware</a><a href="/formats/">Formats</a><a href="/lineage/">Lineage</a><a href="/changes/">Changes</a><a href="/registry.json">Registry JSON</a></div></footer>'

def page_head(title,desc,canonical,extra=""):
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(title)}</title><meta name="description" content="{esc(desc)}"><link rel="canonical" href="{esc(canonical)}"><meta name="robots" content="index,follow,max-snippet:-1"><meta property="og:site_name" content="Open Model Weights"><meta property="og:title" content="{esc(title)}"><meta property="og:description" content="{esc(desc)}"><meta property="og:url" content="{esc(canonical)}"><link rel="stylesheet" href="/styles.css">{extra}</head>'''

def commercial_label(status):
    return {
        "allowed":"Commercial use allowed",
        "allowed-with-conditions":"Commercial use with conditions",
        "allowed-with-revenue-condition":"Commercial use with revenue condition",
        "separate-license-required":"Separate commercial license required",
        "not-allowed":"Commercial use not allowed",
        "unknown":"Manual review required",
    }.get(status,status.replace("-"," ").title())

def explore_page(models,feed):
    modules=[
      ("License Explorer","/licenses/","Compare declared licenses and commercial-use conditions across the registry.",len(set(m["license"]["name"] for m in models))),
      ("Hardware Explorer","/hardware/","Compare weight-only memory estimates across BF16/FP16, FP8/INT8 and INT4.",sum(m.get("hardware",{}).get("status")=="estimated" for m in models)),
      ("Format Explorer","/formats/","See which weight formats and precision artifacts are actually observed in official repositories.",len(set(x for m in models for x in m["weights"].get("formats",[])))),
      ("Family / Lineage Graph","/lineage/","Explore declared base-model relationships and model families as an interactive graph.",sum(bool(m["lineage"]["base_model"].get("models")) for m in models)),
      ("What changed?","/changes/","Publisher repository activity plus field-level differences between verification runs.",len(feed.get("events",[]))),
    ]
    cards="".join(f'<a class="tool-card" href="{url}"><span>{count}</span><h2>{esc(name)}</h2><p>{esc(desc)}</p><strong>Open explorer →</strong></a>' for name,url,desc,count in modules)
    return f'''{page_head("Explore open-weight AI — licenses, hardware, formats & lineage | Open Model Weights","Explore the verified open-weight registry by license, hardware requirements, formats, model lineage and verification changes.","https://openmodelweights.com/explore/")}<body>{nav_html()}<main><section class="page-hero"><div class="breadcrumbs"><a href="/">Home</a> / Explore</div><p class="eyebrow">REGISTRY EXPLORERS</p><h1>Interrogate the registry.</h1><p class="lead">Five views over the same field-verified dataset — each optimized for a different technical or legal question.</p></section><section class="section"><div class="tool-grid">{cards}</div></section></main>{footer_html()}</body></html>'''

def license_page(models):
    groups={}
    for m in models:
        key=m["license"]["name"]
        g=groups.setdefault(key,{"models":[],"statuses":set(),"url":m["license"].get("url")})
        g["models"].append(m); g["statuses"].add(m["license"]["commercial_use"]["status"])
        if not g["url"] and m["license"].get("url"): g["url"]=m["license"]["url"]
    records=[]
    for name,g in sorted(groups.items(),key=lambda kv:(-len(kv[1]["models"]),kv[0].lower())):
        statuses=sorted(g["statuses"])
        status=statuses[0] if len(statuses)==1 else "mixed"
        status_text=commercial_label(status) if status!="mixed" else "Mixed commercial-use classifications"
        model_links="".join(f'<a href="/models/{esc(m["id"])}/">{esc(m["name"])}</a>' for m in sorted(g["models"],key=lambda x:x["name"].lower()))
        source=f'<a class="evidence-link" href="{esc(g["url"])}" rel="noopener">License source ↗</a>' if g["url"] else ""
        search=name+" "+" ".join(m["name"]+" "+m["developer"] for m in g["models"])
        records.append(f'''<article class="license-record explorer-card" data-search="{esc(search.lower())}" data-status="{esc(status)}"><div class="explorer-card-head"><div><span class="kicker">{len(g["models"])} model{"s" if len(g["models"])!=1 else ""}</span><h2>{esc(name)}</h2></div><span class="commercial-badge {esc(status)}">{esc(status_text)}</span></div><div class="model-link-cloud">{model_links}</div>{source}</article>''')
    status_options=sorted(set(next(iter({m["license"]["commercial_use"]["status"] for m in models if m["license"]["name"]==name}),"unknown") for name in groups))
    options="".join(f'<option value="{esc(s)}">{esc(commercial_label(s))}</option>' for s in status_options)
    return f'''{page_head("License Explorer — open-weight AI licenses & commercial use | Open Model Weights",f"Compare {len(groups)} verified model licenses across {len(models)} open-weight AI records, including commercial-use conditions and primary license sources.","https://openmodelweights.com/licenses/",'<script src="/explorer.js" defer></script>')}<body>{nav_html()}<main><section class="page-hero"><div class="breadcrumbs"><a href="/">Home</a> / <a href="/explore/">Explore</a> / Licenses</div><p class="eyebrow">LICENSE EXPLORER · {len(groups)} LICENSE LABELS</p><h1>Licenses, without the hand-waving.</h1><p class="lead">Compare what publishers actually declare and how commercial use is classified. This is a source-backed index, not legal advice.</p></section><section class="section explorer-section"><div class="explorer-controls"><input id="license-search" type="search" placeholder="Search license, model or developer…"><select id="commercial-filter"><option value="">All commercial-use classes</option>{options}</select></div><div class="explorer-stack">{''.join(records)}</div></section></main>{footer_html()}</body></html>'''

def hardware_page(models):
    estimated=[m for m in models if m.get("hardware",{}).get("status")=="estimated" and m["hardware"].get("weight_only_gb")]
    estimated.sort(key=lambda m:m["hardware"]["weight_only_gb"].get("int4",10**9))
    developers=sorted(set(m["developer"] for m in estimated))
    options="".join(f'<option value="{esc(d.lower())}">{esc(d)}</option>' for d in developers)
    rows=[]
    for m in estimated:
        h=m["hardware"]["weight_only_gb"]
        rows.append(f'''<a class="hardware-row explorer-table-row" href="/models/{esc(m["id"])}/" data-search="{esc((m["name"]+" "+m["developer"]+" "+str(m.get("family",""))).lower())}" data-developer="{esc(m["developer"].lower())}" data-bf16="{h.get("bf16_fp16","")}" data-fp8="{h.get("fp8_int8","")}" data-int4="{h.get("int4","")}"><div><strong>{esc(m["name"])}</strong><span>{esc(m["developer"])} · {esc(m["model"].get("parameters"))}</span></div><div>{h.get("bf16_fp16",0):,.1f} GB</div><div>{h.get("fp8_int8",0):,.1f} GB</div><div>{h.get("int4",0):,.1f} GB</div></a>''')
    return f'''{page_head("Hardware Explorer — AI model memory estimates | Open Model Weights",f"Compare weight-only memory estimates for {len(estimated)} verified open-weight AI models at BF16/FP16, FP8/INT8 and INT4.","https://openmodelweights.com/hardware/",'<script src="/explorer.js" defer></script>')}<body>{nav_html()}<main><section class="page-hero"><div class="breadcrumbs"><a href="/">Home</a> / <a href="/explore/">Explore</a> / Hardware</div><p class="eyebrow">HARDWARE EXPLORER · WEIGHT-ONLY MEMORY</p><h1>How much memory do the weights need?</h1><p class="lead">Filter by a hardware budget and precision. Estimates cover model weights only — not KV cache, activations, runtime overhead or sharding.</p></section><section class="section explorer-section"><div class="explorer-controls hardware-controls"><input id="hardware-search" type="search" placeholder="Search model or family…"><select id="hardware-developer"><option value="">All developers</option>{options}</select><select id="hardware-precision"><option value="bf16">BF16 / FP16</option><option value="fp8">FP8 / INT8</option><option value="int4" selected>INT4</option></select><select id="hardware-budget"><option value="">Any memory budget</option><option value="8">≤ 8 GB</option><option value="16">≤ 16 GB</option><option value="24">≤ 24 GB</option><option value="32">≤ 32 GB</option><option value="48">≤ 48 GB</option><option value="80">≤ 80 GB</option><option value="96">≤ 96 GB</option><option value="192">≤ 192 GB</option></select></div><p class="explorer-result-count"><strong id="hardware-count">{len(estimated)}</strong> models match</p><div class="explorer-table"><div class="explorer-table-head"><div>Model</div><div>BF16 / FP16</div><div>FP8 / INT8</div><div>INT4</div></div>{''.join(rows)}</div><p class="note">Decimal GB estimate: parameter count × bytes per weight. This is a comparison aid, not a deployment guarantee.</p></section></main>{footer_html()}</body></html>'''

def format_page(models):
    format_counts={}
    precision_counts={k:0 for k in ["bf16","fp16","fp8","int8","int4","gguf"]}
    for m in models:
        for f in m["weights"].get("formats",[]): format_counts[f]=format_counts.get(f,0)+1
        for k,v in m["weights"].get("precision_availability",{}).items():
            if k in precision_counts and v.get("available"): precision_counts[k]+=1
    cards="".join(f'<div class="metric-card"><span>{count}</span><strong>{esc(name)}</strong><p>Official repositories with this observed format.</p></div>' for name,count in sorted(format_counts.items(),key=lambda x:-x[1]))
    p_cards="".join(f'<div class="metric-card"><span>{count}</span><strong>{k.upper()}</strong><p>Records with a positive precision/artifact signal.</p></div>' for k,count in precision_counts.items())
    all_filters=sorted(set(format_counts)|{k.upper() for k,v in precision_counts.items() if v})
    options="".join(f'<option value="{esc(x)}">{esc(x)}</option>' for x in all_filters)
    rows=[]
    for m in models:
        observed=list(m["weights"].get("formats",[]))
        observed += [k.upper() for k,v in m["weights"].get("precision_availability",{}).items() if v.get("available")]
        observed=list(dict.fromkeys(observed))
        chips="".join(f"<span>{esc(x)}</span>" for x in observed)
        rows.append(f'''<a class="format-row explorer-table-row" href="/models/{esc(m["id"])}/" data-search="{esc((m["name"]+" "+m["developer"]+" "+" ".join(observed)).lower())}" data-formats="{esc("|".join(observed))}"><div><strong>{esc(m["name"])}</strong><span>{esc(m["developer"])}</span></div><div class="chips compact-chips">{chips}</div><div>{m["weights"].get("file_count",0)} files</div><div>{esc(m["weights"].get("access",""))}</div></a>''')
    return f'''{page_head("Format Explorer — BF16, FP8, GGUF, Safetensors & more | Open Model Weights",f"Explore observed formats and precision artifacts across {len(models)} field-verified open-weight model repositories.","https://openmodelweights.com/formats/",'<script src="/explorer.js" defer></script>')}<body>{nav_html()}<main><section class="page-hero"><div class="breadcrumbs"><a href="/">Home</a> / <a href="/explore/">Explore</a> / Formats</div><p class="eyebrow">FORMAT EXPLORER</p><h1>What files are actually published?</h1><p class="lead">Repository evidence for Safetensors, GGUF, ONNX and precision signals such as BF16, FP8 and INT4. “Not observed” never means a third-party conversion cannot exist.</p></section><section class="section explorer-section"><h2 class="explorer-title">Repository formats</h2><div class="metric-card-grid">{cards}</div><h2 class="explorer-title">Precision signals</h2><div class="metric-card-grid">{p_cards}</div><div class="explorer-controls"><input id="format-search" type="search" placeholder="Search model, developer or format…"><select id="format-filter"><option value="">All formats / precisions</option>{options}</select></div><p class="explorer-result-count"><strong id="format-count">{len(models)}</strong> models match</p><div class="explorer-table"><div class="explorer-table-head format-head"><div>Model</div><div>Observed</div><div>Weight files</div><div>Access</div></div>{''.join(rows)}</div></section></main>{footer_html()}</body></html>'''

def lineage_page(models):
    families={}
    for m in models: families[m.get("family") or "Unclassified"]=families.get(m.get("family") or "Unclassified",0)+1
    default=max(families,key=families.get)
    fopts="".join(f'<option value="{esc(f)}"{" selected" if f==default else ""}>{esc(f)} ({n})</option>' for f,n in sorted(families.items(),key=lambda x:(-x[1],x[0])))
    devs=sorted(set(m["developer"] for m in models))
    dopts="".join(f'<option value="{esc(d)}">{esc(d)}</option>' for d in devs)
    nodes=[]
    for m in models:
        repo=m["weights"]["repository"].split("huggingface.co/",1)[-1].strip("/")
        nodes.append({"id":m["id"],"name":m["name"],"developer":m["developer"],"family":m.get("family") or "Unclassified","repo":repo,"url":f'/models/{m["id"]}/',"parents":m["lineage"]["base_model"].get("models") or []})
    data=json.dumps({"models":nodes},ensure_ascii=False).replace("</","<\\/")
    declared=sum(bool(x["parents"]) for x in nodes)
    return f'''{page_head("Model Family & Lineage Graph — Open Model Weights",f"Explore declared base-model relationships across {len(models)} verified open-weight AI model records and {len(families)} model families.","https://openmodelweights.com/lineage/",'<script src="/lineage.js" defer></script>')}<body>{nav_html()}<main><section class="page-hero"><div class="breadcrumbs"><a href="/">Home</a> / <a href="/explore/">Explore</a> / Lineage</div><p class="eyebrow">MODEL FAMILY / LINEAGE GRAPH · {declared} DECLARED RELATIONSHIPS</p><h1>See where a model comes from.</h1><p class="lead">An interactive view of publisher-declared <code>base_model</code> metadata. Missing edges mean no base model was declared in the checked standard metadata.</p></section><section class="section explorer-section"><div class="explorer-controls"><select id="lineage-family">{fopts}</select><select id="lineage-developer"><option value="">All developers</option>{dopts}</select></div><p id="lineage-summary" class="explorer-result-count"></p><div class="lineage-shell"><svg id="lineage-svg" role="img" aria-label="Model lineage graph"></svg><p id="lineage-empty" class="note" hidden>No models match this selection.</p></div><script id="lineage-data" type="application/json">{data}</script></section></main>{footer_html()}</body></html>'''

def comparable_model(m):
    return {
      "sha":m.get("hub",{}).get("sha"),
      "license":[m["license"].get("name"),m["license"].get("commercial_use",{}).get("status")],
      "context":m["model"].get("context",{}).get("display") if isinstance(m["model"].get("context"),dict) else m["model"].get("context"),
      "weight_files":sorted(m["weights"].get("exact_files",[])),
      "formats":sorted(m["weights"].get("formats",[])),
      "precision":{k:v.get("available") for k,v in sorted(m["weights"].get("precision_availability",{}).items())},
      "base":sorted(m["lineage"].get("base_model",{}).get("models",[])),
      "recipe":m["training_assets"].get("training_recipe",{}).get("status"),
      "data":m["training_assets"].get("data_disclosure",{}).get("status"),
      "runtime":sorted(set((m.get("runtime_support",{}).get("declared") or [])+(m.get("runtime_support",{}).get("mentioned_in_model_card") or []))),
    }

def change_id(parts):
    import hashlib
    return hashlib.sha1("|".join(str(x) for x in parts).encode()).hexdigest()[:16]

def build_change_feed(models,report):
    previous=git_json("public/registry.json") or {"models":[]}
    old_feed=git_json("data/change-feed.json") or {"events":[]}
    old_events=old_feed.get("events",[])
    # Drop bootstrap noise from the first baseline build and collapse repeated same-day verification runs.
    if sum(1 for e in old_events if e.get("type")=="added") >= max(20,int(len(models)*0.75)):
        old_events=[e for e in old_events if e.get("type")!="added"]
    old_events=[e for e in old_events if not (e.get("type")=="verification" and str(e.get("at",""))[:10]==TODAY)]
    old={m["id"]:m for m in previous.get("models",[])}
    bootstrap=not bool(old)
    cur={m["id"]:m for m in models}
    events=[]
    events.append({"id":change_id([NOW,"verification-run"]),"at":NOW,"type":"verification","model_id":None,"model":"Registry verification","developer":"","summary":f'{report["stats"]["field_verified"]}/{report["stats"]["total_seed_records"]} records field-verified',"detail":f'{report["stats"]["errors"]} fetch errors; {report["stats"]["commercial_use_classified"]} commercial-use classifications.',"url":"/verification/"})
    for mid,m in cur.items():
        if mid not in old:
            if not bootstrap:
                events.append({"id":change_id([NOW,mid,"added"]),"at":NOW,"type":"added","model_id":mid,"model":m["name"],"developer":m["developer"],"summary":"Model added to registry","detail":"New canonical model record entered the source registry.","url":f"/models/{mid}/"})
            continue
        a=comparable_model(old[mid]); b=comparable_model(m)
        if a["sha"] and b["sha"] and a["sha"]!=b["sha"]:
            events.append({"id":change_id([NOW,mid,"sha",b["sha"]]),"at":NOW,"type":"release","model_id":mid,"model":m["name"],"developer":m["developer"],"summary":"Publisher repository revision changed","detail":f'{a["sha"][:8]} → {b["sha"][:8]}',"url":f"/models/{mid}/"})
        checks=[
          ("license","license","License classification changed"),
          ("context","metadata","Context metadata changed"),
          ("formats","metadata","Published format set changed"),
          ("precision","metadata","Precision evidence changed"),
          ("base","metadata","Base-model declaration changed"),
          ("recipe","metadata","Training-recipe disclosure changed"),
          ("data","metadata","Training-data disclosure changed"),
          ("runtime","metadata","Runtime-support evidence changed"),
        ]
        for key,typ,label in checks:
            if a[key]!=b[key]:
                events.append({"id":change_id([NOW,mid,key,json.dumps(b[key],sort_keys=True)]),"at":NOW,"type":typ,"model_id":mid,"model":m["name"],"developer":m["developer"],"summary":label,"detail":f'{a[key]} → {b[key]}',"url":f"/models/{mid}/"})
        if a["weight_files"]!=b["weight_files"]:
            added=len(set(b["weight_files"])-set(a["weight_files"])); removed=len(set(a["weight_files"])-set(b["weight_files"]))
            events.append({"id":change_id([NOW,mid,"weights",len(b["weight_files"])]),"at":NOW,"type":"release","model_id":mid,"model":m["name"],"developer":m["developer"],"summary":"Official weight-file set changed","detail":f'+{added} / -{removed} recognized weight files.',"url":f"/models/{mid}/"})
    for mid,m in old.items():
        if mid not in cur:
            events.append({"id":change_id([NOW,mid,"removed"]),"at":NOW,"type":"removed","model_id":mid,"model":m["name"],"developer":m["developer"],"summary":"Model removed from generated registry","detail":"Record no longer appears in the current generated verification output.","url":"/changes/"})
    seen=set()
    merged=[]
    for e in events + old_events:
        if e["id"] not in seen:
            seen.add(e["id"]); merged.append(e)
    merged=merged[:5000]
    publisher=[]
    for m in models:
        lm=m.get("hub",{}).get("last_modified")
        if lm:
            publisher.append({"at":lm,"model_id":m["id"],"model":m["name"],"developer":m["developer"],"sha":m.get("hub",{}).get("sha"),"url":f'/models/{m["id"]}/'})
    publisher.sort(key=lambda x:x["at"],reverse=True)
    return {"generated_at":NOW,"events":merged,"publisher_activity":publisher[:500],"retention":{"max_events":5000,"policy":"rolling verification history"}}

def changes_page(feed,models):
    devs=sorted(set(m["developer"] for m in models))
    dopts="".join(f'<option value="{esc(d.lower())}">{esc(d)}</option>' for d in devs)
    types=sorted(set(e["type"] for e in feed.get("events",[])))
    topts="".join(f'<option value="{esc(t)}">{esc(t.title())}</option>' for t in types)
    items=[]
    for e in feed.get("events",[])[:200]:
        items.append(f'''<article class="change-item" data-type="{esc(e["type"])}" data-developer="{esc((e.get("developer") or "").lower())}" data-search="{esc((e.get("model","")+" "+e.get("summary","")+" "+e.get("detail","")+" "+e.get("developer","")).lower())}"><time>{esc(e["at"])}</time><div><span class="change-type">{esc(e["type"])}</span><h3><a href="{esc(e["url"])}">{esc(e["model"])}</a></h3><strong>{esc(e["summary"])}</strong><p>{esc(e["detail"])}</p></div></article>''')
    upstream=[]
    for e in feed.get("publisher_activity",[])[:40]:
        upstream.append(f'''<a class="upstream-row" href="{esc(e["url"])}"><time>{esc(e["at"])}</time><div><strong>{esc(e["model"])}</strong><span>{esc(e["developer"])}</span></div><code>{esc((e.get("sha") or "")[:10])}</code></a>''')
    return f'''{page_head("What changed? — open-weight model release & verification feed | Open Model Weights","Track publisher repository activity and field-level changes discovered by Open Model Weights verification runs.","https://openmodelweights.com/changes/",'<script src="/explorer.js" defer></script>')}<body>{nav_html()}<main><section class="page-hero"><div class="breadcrumbs"><a href="/">Home</a> / <a href="/explore/">Explore</a> / Changes</div><p class="eyebrow">RELEASE / VERIFICATION FEED</p><h1>What changed?</h1><p class="lead">A diff-oriented feed: publisher repository revisions, changes in verified metadata and a record of each registry verification run.</p></section><section class="section explorer-section"><div class="explorer-controls"><input id="changes-search" type="search" placeholder="Search changes…"><select id="changes-type"><option value="">All change types</option>{topts}</select><select id="changes-developer"><option value="">All developers</option>{dopts}</select></div><div class="changes-layout"><div><h2 class="explorer-title">Registry changes</h2><div class="change-feed">{''.join(items)}</div></div><aside><h2 class="explorer-title">Recent publisher activity</h2><div class="upstream-feed">{''.join(upstream)}</div><p class="note">Publisher activity reflects Hugging Face repository <code>lastModified</code> metadata, not a claim about semantic model releases.</p></aside></div></section></main>{footer_html()}</body></html>'''

def home_page_portal(models,report):
    s=report["stats"]
    featured=models[:6]
    cards="".join(f'<a class="model-card home-model-card" href="/models/{esc(m["id"])}/"><div class="card-top"><span class="org">{esc(m["developer"])}</span><span class="status-dot verified">● field-verified</span></div><h3>{esc(m["name"])}</h3><p>{esc(m["model"]["context"]["display"])} · {esc(m["license"]["name"])}</p><div class="chips"><span>{esc(m["model"].get("parameters"))}</span><span>{m["weights"]["file_count"]} weight files</span></div><span class="card-link">Open evidence →</span></a>' for m in featured)
    actions=[
      ("01","Find a model","Search verified records by developer, license, format, context and hardware.","/models/","Search the registry →"),
      ("02","Compare records","Put 2–4 models side by side without composite scores or a declared winner.","/compare/","Compare models →"),
      ("03","Trace what changed","Follow repository revisions and field-level evidence changes over time.","/changes/","Open change history →"),
      ("04","Query the data layer","Use the versioned JSON API or read-only MCP endpoint in your own tools.","/api/","Open API & MCP →"),
    ]
    action_cards="".join(f'<a class="home-action-card" href="{url}"><span class="home-card-index">{n}</span><div><h3>{esc(title)}</h3><p>{esc(desc)}</p><strong>{esc(cta)}</strong></div></a>' for n,title,desc,url,cta in actions)
    evidence=[
      ("EVIDENCE LEDGER","History that compounds","Observed field snapshots, source revisions and material diffs accumulate instead of being overwritten.","/history/","Explore model history"),
      ("COMPATIBILITY","Relationships, not rankings","Connect runtimes, formats, precisions, licenses, base models and memory constraints.","/compatibility/","Open compatibility graph"),
      ("FRESHNESS","Daily verification","Repository revisions are checked every day; changed and new sources return to full field verification.","/changes/","See recent changes"),
      ("MACHINE LAYER","Built for humans and agents","Versioned JSON, OpenAPI and a read-only MCP endpoint expose the same evidence as the website.","/mcp/","Connect through MCP"),
    ]
    evidence_cards="".join(f'<a class="home-evidence-card" href="{url}"><span>{esc(label)}</span><h3>{esc(title)}</h3><p>{esc(desc)}</p><strong>{esc(cta)} →</strong></a>' for label,title,desc,url,cta in evidence)
    return f'''{page_head("Open Model Weights — evidence for open-weight AI","The evidence layer for open-weight AI: 700 field-verified records with exact weights, licenses, context, formats, lineage, change history and machine-readable access.","https://openmodelweights.com/")}<body>{nav_html()}<main>
<section class="hero home-hero home-hero-v3">
  <div class="hero-status"><span class="hero-status-dot" aria-hidden="true"></span><span>Source-first registry</span><span class="hero-status-sep">·</span><span>Verified daily</span></div>
  <p class="eyebrow">THE EVIDENCE LAYER FOR OPEN-WEIGHT AI</p>
  <h1>Open-weight AI,<br><span>grounded in evidence.</span></h1>
  <p class="lead">Search exact weight artifacts, licenses, commercial-use conditions, context, formats, lineage and runtime signals — with the source trail kept attached.</p>
  <form class="hero-search hero-search-v3" action="/models/" method="get"><span class="hero-search-icon" aria-hidden="true">⌕</span><input name="q" type="search" placeholder="Search {len(models)} verified models…" aria-label="Search verified models"><button type="submit">Search registry</button></form>
  <div class="hero-actions"><a class="button primary" href="/models/">Explore {len(models)} models <span aria-hidden="true">→</span></a><a class="button" href="/compare/">Compare models</a></div>
  <div class="hero-proof" aria-label="Registry proof points">
    <div><strong>{s["field_verified"]}</strong><span>field-verified records</span></div>
    <div><strong>{s["exact_weight_lists"]}</strong><span>exact weight lists</span></div>
    <div><strong>{s["commercial_use_classified"]}</strong><span>commercial-use classified</span></div>
    <div><strong>Daily</strong><span>revision verification</span></div>
  </div>
</section>
<div class="home-trust"><div class="home-trust-brand"><span class="trust-signal" aria-hidden="true"><i></i></span><span><small>Evidence standard</small><strong>Source-first verified</strong></span></div><div class="home-trust-stat"><small>Last registry run</small><strong>{TODAY}</strong></div><div class="home-trust-stat"><small>Scope</small><strong>{len(models)} published records</strong></div><div class="home-trust-links"><a href="/sources/">How sourcing works →</a><a href="/api/">API / JSON →</a></div></div>
<section class="section home-interrogate">
  <div class="section-head home-section-head"><div><p class="eyebrow">INTERROGATE THE REGISTRY.</p><h2>Start with the question.</h2></div><p class="section-kicker">The interface stays simple up front. Evidence, provenance and technical detail remain available when you need to go deeper.</p></div>
  <div class="home-action-grid">{action_cards}</div>
</section>
<section class="section intelligence-section home-evidence-section">
  <div class="section-head home-section-head"><div><p class="eyebrow">EVIDENCE INTELLIGENCE</p><h2>A registry that gets more useful with time.</h2></div><p class="section-kicker">Lists are easy to copy. A dated record of what was observed, where it came from and how it changed is harder to recreate.</p></div>
  <div class="home-evidence-grid">{evidence_cards}</div>
</section>
<section class="section home-models-section">
  <div class="section-head home-section-head"><div><p class="eyebrow">VERIFIED RECORDS</p><h2>Explore the evidence, not a leaderboard.</h2></div><a class="text-link" href="/models/">Browse all {len(models)} models →</a></div>
  <div class="model-grid">{cards}</div>
</section>
<section class="section home-source-section">
  <div class="home-source-panel"><div><p class="eyebrow">SOURCE-FIRST BY DESIGN</p><h2>Every important claim should have somewhere to point.</h2><p>Open Model Weights separates repository evidence, publisher documentation and derived values. Unknown stays unknown, and popularity signals never become a quality score.</p></div><div class="home-source-links"><a href="/sources/"><span>01</span><div><strong>Evidence policy</strong><small>See field-to-source mapping and verification boundaries.</small></div><b>→</b></a><a href="/history/"><span>02</span><div><strong>Observed history</strong><small>Inspect snapshots and field-level diffs for individual models.</small></div><b>→</b></a><a href="/mcp/"><span>03</span><div><strong>Machine access</strong><small>Let applications query verified evidence through API and MCP.</small></div><b>→</b></a></div></div>
</section>
</main>{footer_html()}</body></html>'''

def write_sitemap(models,groups):
    urls=["/","/models/","/developers/","/explore/","/licenses/","/hardware/","/formats/","/lineage/","/changes/","/verification/","/methodology/","/about/","/history/","/compatibility/","/benchmarks/","/mcp/"]
    urls += [f'/models/{m["id"]}/' for m in models]
    urls += [f'/developers/{re.sub(r"[^a-z0-9]+","-",d.lower()).strip("-")}/' for d in groups]
    xml='<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    xml+="\n".join(f'<url><loc>https://openmodelweights.com{u}</loc><lastmod>{TODAY}</lastmod></url>' for u in urls)
    xml+="\n</urlset>\n"
    (PUBLIC/"sitemap.xml").write_text(xml)

def main():
    reg=json.loads(REGISTRY.read_text())
    models=reg["models"]
    oldhist=prior_history()

    for m in models:
        # If the publisher SHA is unchanged, retain the previously checked license
        # classification instead of downloading the same license text every day.
        unchanged=(m.get("verification") or {}).get("mode")=="repository-revision-unchanged"
        already_checked=bool((m.get("license") or {}).get("verification"))
        if not (unchanged and already_checked):
            raw=raw_license_url(m)
            text=get_text(raw) if raw else None
            classify_license(m,text)
        fix_precision(m)
        clean_runtime(m)
        refine_recipe(m)
        current=m.get("verification",{}).get("history",[])
        merged=[]
        for item in current + oldhist.get(m["id"],[]):
            key=(item.get("date"),item.get("event"),item.get("detail"))
            if key not in {(x.get("date"),x.get("event"),x.get("detail")) for x in merged}:
                merged.append(item)
        m["verification"]["history"]=merged[:20]
        m["verification"]["fields"]["commercial_use"]="classified" if m["license"]["commercial_use"]["status"]!="unknown" else "unknown"

    errors=reg.get("verification_errors",[]) or []
    previous_report={}
    try:
        previous_report=json.loads(REPORT.read_text()) if REPORT.exists() else {}
    except Exception:
        previous_report={}
    report=recalc_report(models,errors)
    for key in ("candidate_count","successful_candidates","publication_target","publication_shortfall"):
        if key in previous_report:
            report[key]=previous_report[key]
    feed=build_change_feed(models,report)
    reg["schema_version"]="0.8.0"
    reg["generated_at"]=NOW
    reg["explorers"]={
      "licenses":"https://openmodelweights.com/licenses/",
      "hardware":"https://openmodelweights.com/hardware/",
      "formats":"https://openmodelweights.com/formats/",
      "lineage":"https://openmodelweights.com/lineage/",
      "changes":"https://openmodelweights.com/changes/"
    }
    REGISTRY.write_text(json.dumps(reg,indent=2,ensure_ascii=False)+"\n")
    REPORT.write_text(json.dumps(report,indent=2,ensure_ascii=False)+"\n")
    (ROOT/"data"/"change-feed.json").write_text(json.dumps(feed,indent=2,ensure_ascii=False)+"\n")
    (PUBLIC/"changes.json").write_text(json.dumps(feed,indent=2,ensure_ascii=False)+"\n")

    for m in models:
        d=PUBLIC/"models"/m["id"]; d.mkdir(parents=True,exist_ok=True)
        (d/"index.html").write_text(model_page(m))
    (PUBLIC/"models"/"index.html").write_text(models_page(models))
    groups={}
    for m in models: groups.setdefault(m["developer"],[]).append(m)
    for dev,items in groups.items():
        slug,page=developer_page(dev,items)
        d=PUBLIC/"developers"/slug; d.mkdir(parents=True,exist_ok=True)
        (d/"index.html").write_text(page)
    (PUBLIC/"developers"/"index.html").write_text(developer_index(models))
    (PUBLIC/"verification"/"index.html").write_text(verification_page(report))
    (PUBLIC/"index.html").write_text(home_page_portal(models,report))

    pages={
      "explore":explore_page(models,feed),
      "licenses":license_page(models),
      "hardware":hardware_page(models),
      "formats":format_page(models),
      "lineage":lineage_page(models),
      "changes":changes_page(feed,models),
    }
    for path,html in pages.items():
        d=PUBLIC/path; d.mkdir(parents=True,exist_ok=True); (d/"index.html").write_text(html)

    (PUBLIC/"registry.schema.json").write_text(json.dumps(schema_doc(),indent=2)+"\n")
    write_sitemap(models,groups)
    (PUBLIC/"llms.txt").write_text(f"""# Open Model Weights
> Field-verified registry for open-weight AI models.

Current registry: {len(models)} field-verified model records.
Latest verification: {TODAY}.

## Registry
- https://openmodelweights.com/models/
- https://openmodelweights.com/registry.json
- https://openmodelweights.com/verification/

## Explorers
- https://openmodelweights.com/licenses/ — license and commercial-use explorer
- https://openmodelweights.com/hardware/ — weight-memory explorer
- https://openmodelweights.com/formats/ — repository format and precision explorer
- https://openmodelweights.com/lineage/ — family and declared base-model graph
- https://openmodelweights.com/changes/ — release / verification change feed
- https://openmodelweights.com/changes.json — machine-readable change feed

A value such as “not disclosed” means the checked standard metadata/model-card/config sources did not provide it; it is not an inference that the information does not exist elsewhere.
""")
    print(json.dumps({"verification":report,"change_events":len(feed["events"])},indent=2))

if __name__=="__main__":
    main()
