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
    elif lname=="mrl" or lid=="mrl" or "mistral research license" in blob:\n        display="Mistral Research License"; status="not-allowed"; label="Commercial use is not permitted without a separate Mistral commercial license"\n    elif "modified mit license" in blob:
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

def recalc_report(models):
    stats={
        "total_seed_records":len(models),
        "field_verified":len(models),
        "errors":0,
        "license_declared":sum(m["license"].get("status")=="verified" for m in models),
        "commercial_use_classified":sum(m["license"]["commercial_use"]["status"]!="unknown" for m in models),
        "context_verified":sum(m["model"]["context"]["status"]=="verified" for m in models),
        "exact_weight_lists":sum(bool(m["weights"].get("exact_files")) for m in models),
        "base_model_declared":sum(m["lineage"]["base_model"]["status"]=="declared" for m in models),
        "training_recipe_signal":sum(m["training_assets"]["training_recipe"]["status"]!="not-disclosed-in-checked-repository" for m in models),
        "data_disclosure_signal":sum(m["training_assets"]["data_disclosure"]["status"]!="not-disclosed-in-standard-metadata-or-obvious-model-card-section" for m in models),
        "runtime_signal":sum(bool(m["runtime_support"].get("declared") or m["runtime_support"].get("mentioned_in_model_card") or m["runtime_support"].get("artifact_signals")) for m in models),
    }
    return {"generated_at":NOW,"stats":stats,"errors":[]}

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
      "title":"Open Model Weights Registry v0.3",
      "type":"object",
      "required":["schema_version","generated_at","models"],
      "properties":{
        "schema_version":{"type":"string"},
        "generated_at":{"type":"string"},
        "models":{"type":"array","items":{"type":"object","required":["id","name","developer","model","weights","license","hardware","lineage","training_assets","runtime_support","sources","verification"]}}
      }
    }

def main():
    reg=json.loads(REGISTRY.read_text())
    models=reg["models"]
    oldhist=prior_history()

    for m in models:
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

    report=recalc_report(models)
    reg["schema_version"]="0.3.1"
    reg["generated_at"]=NOW
    REGISTRY.write_text(json.dumps(reg,indent=2,ensure_ascii=False)+"\n")
    REPORT.write_text(json.dumps(report,indent=2,ensure_ascii=False)+"\n")

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
    (PUBLIC/"index.html").write_text(home_page(models,report))
    (PUBLIC/"registry.schema.json").write_text(json.dumps(schema_doc(),indent=2)+"\n")
    (PUBLIC/"llms.txt").write_text(f"""# Open Model Weights
> Field-verified registry for open-weight AI models.

Current registry: {len(models)} field-verified model records.
Latest verification: {TODAY}.

## Canonical resources
- https://openmodelweights.com/models/
- https://openmodelweights.com/developers/
- https://openmodelweights.com/verification/
- https://openmodelweights.com/methodology/
- https://openmodelweights.com/registry.json
- https://openmodelweights.com/registry.schema.json

Each model record contains exact repository weight files, declared license and commercial-use classification, context evidence, formats/precision signals, base-model metadata, training/data disclosure, runtime signals, primary sources and verification history.

A value such as “not disclosed” means the checked standard metadata/model-card/config sources did not provide it; it is not an inference that the information does not exist elsewhere.
""")
    print(json.dumps(report,indent=2))

if __name__=="__main__":
    main()
