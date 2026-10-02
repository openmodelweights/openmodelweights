#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import hashlib
import html
import json
import re
import subprocess
from collections import Counter, defaultdict
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
PUBLIC=ROOT/"public"
DATA=ROOT/"data"
REGISTRY=PUBLIC/"registry.json"
LEDGERS=DATA/"evidence-ledger"
RUNS=DATA/"evidence-runs"
API=PUBLIC/"api"/"v1"

def esc(v):
    return html.escape(str(v if v is not None else ""),quote=True)

def write_json(path,obj):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(obj,indent=2,ensure_ascii=False)+"\n")

def git_json(path):
    try:
        return json.loads(subprocess.check_output(["git","show",f"HEAD:{path}"],text=True))
    except Exception:
        return None

def canonical(obj):
    return json.dumps(obj,sort_keys=True,separators=(",",":"),ensure_ascii=False)

def digest(obj):
    return hashlib.sha256(canonical(obj).encode()).hexdigest()

def date(v):
    return str(v)[:10] if v else "Not declared"

def slug(v):
    return re.sub(r"[^a-z0-9]+","-",str(v).lower()).strip("-")

def context_value(m):
    c=(m.get("model") or {}).get("context")
    if isinstance(c,dict):
        return c.get("value")
    return None

def context_display(m):
    c=(m.get("model") or {}).get("context")
    if isinstance(c,dict):
        return c.get("display")
    return c

def precision_list(m):
    return sorted(k for k,v in ((m.get("weights") or {}).get("precision_availability") or {}).items() if isinstance(v,dict) and v.get("available"))

def runtime_list(m):
    rt=m.get("runtime_support") or {}
    vals=[]
    for source in ("declared","mentioned_in_model_card","artifact_signals"):
        for x in rt.get(source) or []:
            if isinstance(x,dict):
                x=x.get("runtime") or x.get("name") or x.get("type")
            if x and str(x) not in vals:
                vals.append(str(x))
    if rt.get("declared_library") and str(rt["declared_library"]) not in vals:
        vals.insert(0,str(rt["declared_library"]))
    return sorted(vals)

def evidence_fields(m):
    lic=m.get("license") or {}
    com=lic.get("commercial_use") or {}
    weights=m.get("weights") or {}
    lineage=m.get("lineage") or {}
    training=m.get("training_assets") or {}
    hardware=m.get("hardware") or {}
    hub=m.get("hub") or {}
    return {
      "identity":{
        "name":m.get("name"),"developer":m.get("developer"),"family":m.get("family"),"variant":m.get("variant")
      },
      "model":{
        "parameters":(m.get("model") or {}).get("parameters"),
        "total_parameters_billions":(m.get("model") or {}).get("total_parameters_billions"),
        "context_tokens":context_value(m),
        "context_display":context_display(m),
        "modality":(m.get("model") or {}).get("modality"),
      },
      "license":{
        "name":lic.get("name"),"id":lic.get("id"),"url":lic.get("url"),
        "commercial_use_status":com.get("status"),"commercial_use_label":com.get("label"),
      },
      "weights":{
        "repository":weights.get("repository"),"access":weights.get("access"),
        "file_count":weights.get("file_count"),"exact_files":sorted(weights.get("exact_files") or []),
        "formats":sorted(weights.get("formats") or []),"precision":precision_list(m),
      },
      "lineage":{
        "base_models":sorted(((lineage.get("base_model") or {}).get("models") or [])),
        "base_status":(lineage.get("base_model") or {}).get("status"),
      },
      "training":{
        "recipe_status":((training.get("training_recipe") or {}).get("status")),
        "data_status":((training.get("data_disclosure") or {}).get("status")),
        "datasets":sorted(((training.get("data_disclosure") or {}).get("datasets") or [])),
      },
      "runtime":{"signals":runtime_list(m)},
      "hardware":{"weight_only_gb":hardware.get("weight_only_gb"),"status":hardware.get("status")},
      "hub":{"sha":hub.get("sha"),"created_at":hub.get("created_at"),"last_modified":hub.get("last_modified")},
    }

def make_snapshot(m,observed_at,kind):
    fields=evidence_fields(m)
    repo_sha=((m.get("hub") or {}).get("sha") or "")
    evidence_hash=digest(fields)
    snapshot_id=((repo_sha[:12] if repo_sha else "no-sha")+"-"+evidence_hash[:10]).lower()
    return {
      "snapshot_id":snapshot_id,
      "observed_at":observed_at,
      "kind":kind,
      "repository_sha":repo_sha or None,
      "evidence_hash":evidence_hash,
      "verification_mode":(m.get("verification") or {}).get("mode"),
      "full_verified_at":(m.get("verification") or {}).get("full_verified_at") or (m.get("verification") or {}).get("checked_at"),
      "source_repository":(m.get("weights") or {}).get("repository"),
      "sources":m.get("sources") or [],
      "fields":fields,
    }

def field_map(snapshot):
    f=snapshot.get("fields") or {}
    out={}
    def add(prefix,obj):
        if isinstance(obj,dict):
            for k,v in obj.items():
                if prefix=="weights" and k=="exact_files":
                    continue
                add(f"{prefix}.{k}" if prefix else k,v)
        elif isinstance(obj,list):
            out[prefix]=obj
        else:
            out[prefix]=obj
    add("",f)
    return out

def diff_snapshots(a,b):
    av=field_map(a); bv=field_map(b)
    changes=[]
    for key in sorted(set(av)|set(bv)):
        if av.get(key)!=bv.get(key):
            changes.append({"field":key,"before":av.get(key),"after":bv.get(key)})
    af=set((((a.get("fields") or {}).get("weights") or {}).get("exact_files") or []))
    bf=set((((b.get("fields") or {}).get("weights") or {}).get("exact_files") or []))
    if af!=bf:
        changes.append({
          "field":"weights.exact_files",
          "before_count":len(af),"after_count":len(bf),
          "added":sorted(bf-af),"removed":sorted(af-bf)
        })
    return {
      "diff_id":digest([a.get("snapshot_id"),b.get("snapshot_id")])[:16],
      "observed_at":b.get("observed_at"),
      "from_snapshot":a.get("snapshot_id"),
      "to_snapshot":b.get("snapshot_id"),
      "from_repository_sha":a.get("repository_sha"),
      "to_repository_sha":b.get("repository_sha"),
      "change_count":len(changes),
      "changes":changes,
    }

def load_ledger(mid):
    p=LEDGERS/f"{mid}.json"
    if p.exists():
        try:return json.loads(p.read_text())
        except Exception:return None
    return None

def build_ledgers(models,previous,generated):
    LEDGERS.mkdir(parents=True,exist_ok=True)
    API_EVIDENCE=API/"evidence";API_EVIDENCE.mkdir(parents=True,exist_ok=True)
    current={m["id"]:m for m in models}
    old={m["id"]:m for m in previous.get("models",[])}
    ledgers={}
    for mid,m in current.items():
        ledger=load_ledger(mid) or {
          "ledger_version":"1.0.0","model_id":mid,"created_at":generated,
          "snapshots":[],"diffs":[]
        }
        if not ledger["snapshots"]:
            if mid in old:
                prior_at=previous.get("generated_at") or ((old[mid].get("verification") or {}).get("checked_at")) or generated
                ledger["snapshots"].append(make_snapshot(old[mid],prior_at,"observed-baseline"))
            else:
                ledger["snapshots"].append(make_snapshot(m,generated,"observed-baseline"))
        current_snap=make_snapshot(m,generated,"observed-change")
        latest=ledger["snapshots"][-1]
        if current_snap["evidence_hash"]!=latest.get("evidence_hash"):
            d=diff_snapshots(latest,current_snap)
            ledger["snapshots"].append(current_snap)
            ledger["diffs"].append(d)
        ledger["model_name"]=m.get("name")
        ledger["developer"]=m.get("developer")
        ledger["source_repository"]=(m.get("weights") or {}).get("repository")
        ledger["current_repository_sha"]=((m.get("hub") or {}).get("sha"))
        ledger["last_registry_check"]=(m.get("verification") or {}).get("checked_at")
        ledger["last_full_field_verification"]=(m.get("verification") or {}).get("full_verified_at") or (m.get("verification") or {}).get("checked_at")
        ledger["status"]="active"
        ledger["snapshot_count"]=len(ledger["snapshots"])
        ledger["diff_count"]=len(ledger["diffs"])
        ledger["history_url"]=f"https://openmodelweights.com/models/{mid}/history/"
        ledger["diff_url"]=f"https://openmodelweights.com/diff/{mid}/"
        write_json(LEDGERS/f"{mid}.json",ledger)
        write_json(API_EVIDENCE/f"{mid}.json",ledger)
        ledgers[mid]=ledger
    return ledgers

def run_manifest(models,ledgers,generated,registry_schema):
    day=date(generated)
    entries=[]
    for m in models:
        l=ledgers[m["id"]]
        entries.append({
          "model_id":m["id"],
          "repository_sha":((m.get("hub") or {}).get("sha")),
          "evidence_hash":l["snapshots"][-1]["evidence_hash"],
          "verification_mode":(m.get("verification") or {}).get("mode"),
          "checked_at":(m.get("verification") or {}).get("checked_at"),
          "full_verified_at":(m.get("verification") or {}).get("full_verified_at") or (m.get("verification") or {}).get("checked_at"),
        })
    payload={
      "manifest_version":"1.0.0","date":day,"generated_at":generated,
      "registry_schema":registry_schema,"model_count":len(entries),
      "note":"One canonical evidence manifest per UTC day. Re-running on the same day replaces that day's manifest with the latest successful registry state.",
      "models":entries,
    }
    write_json(RUNS/f"{day}.json",payload)
    pub=API/"evidence-runs";pub.mkdir(parents=True,exist_ok=True)
    write_json(pub/f"{day}.json",payload)
    dates=sorted((p.stem for p in RUNS.glob("*.json")),reverse=True)
    index={"generated_at":generated,"count":len(dates),"runs":[{"date":d,"url":f"https://openmodelweights.com/api/v1/evidence-runs/{d}.json"} for d in dates]}
    write_json(API/"evidence-runs.json",index)
    return payload,index

def history_index_page(models,ledgers):
    items=[]
    ranked=sorted(models,key=lambda m:(-ledgers[m["id"]]["diff_count"],m.get("developer",""),m.get("name","")))
    for m in ranked:
        l=ledgers[m["id"]]
        items.append(f'''<a class="history-card" href="/models/{esc(m["id"])}/history/"><div><span>{esc(m.get("developer"))}</span><strong>{esc(m.get("name"))}</strong></div><div><b>{l["snapshot_count"]}</b><small>snapshots</small></div><div><b>{l["diff_count"]}</b><small>field diffs</small></div><div><b>{esc(date(l.get("last_registry_check")))}</b><small>last checked</small></div></a>''')
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Model evidence history — Open Model Weights</title><meta name="description" content="Versioned evidence history and field-level diffs for open-weight AI model records."><link rel="stylesheet" href="/styles.css"></head><body class="history-page"><header class="site-header"><a class="brand" href="/">Open Model Weights</a></header><main><section class="page-hero"><div class="breadcrumbs"><a href="/">Home</a> / History</div><p class="eyebrow">EVIDENCE LEDGER</p><h1>Model history, from observation forward.</h1><p class="lead">Open Model Weights keeps versioned evidence snapshots when verified model fields change. The ledger begins with states we actually observed; it does not fabricate earlier history.</p></section><section class="section"><div class="history-list">{''.join(items)}</div></section></main><footer></footer></body></html>'''

def model_history_page(m,ledger):
    snaps=ledger["snapshots"]
    diffs_by_to={d["to_snapshot"]:d for d in ledger.get("diffs",[])}
    rows=[]
    for i,s in enumerate(reversed(snaps)):
        d=diffs_by_to.get(s["snapshot_id"])
        diff_html=""
        if d:
            previous=d["from_snapshot"]
            diff_html=f'<a href="/diff/{esc(m["id"])}/?from={esc(previous)}&to={esc(s["snapshot_id"])}">{d["change_count"]} changed fields →</a>'
        else:
            diff_html='<span>Observed baseline</span>'
        rows.append(f'''<article class="ledger-entry"><div class="ledger-rail"><i></i></div><div><time>{esc(s.get("observed_at"))}</time><h2>{esc(s.get("kind","snapshot").replace("-"," ").title())}</h2><div class="ledger-meta"><span>Repository <code>{esc((s.get("repository_sha") or "not exposed")[:12])}</code></span><span>Evidence <code>{esc(s.get("evidence_hash","")[:12])}</code></span></div>{diff_html}</div></article>''')
    note="" if len(snaps)>1 else '<div class="history-baseline-note"><strong>History starts here.</strong><p>No earlier field diff is claimed. Future repository or verified-field changes will create additional immutable evidence snapshots.</p></div>'
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(m.get("name"))} evidence history — Open Model Weights</title><meta name="description" content="Observed verification snapshots and field-level changes for {esc(m.get("name"))}."><link rel="stylesheet" href="/styles.css"></head><body class="history-detail-page"><header class="site-header"><a class="brand" href="/">Open Model Weights</a></header><main><section class="page-hero"><div class="breadcrumbs"><a href="/">Home</a> / <a href="/models/">Models</a> / <a href="/models/{esc(m["id"])}/">{esc(m.get("name"))}</a> / History</div><p class="eyebrow">EVIDENCE LEDGER · {ledger["snapshot_count"]} SNAPSHOTS</p><h1>{esc(m.get("name"))} history.</h1><p class="lead">Observed repository identity and verified field states, retained only when the evidence changes.</p><div class="hero-actions"><a class="button primary" href="/diff/{esc(m["id"])}/">Open revision diff</a><a class="button" href="/api/v1/evidence/{esc(m["id"])}.json">Evidence JSON ↗</a><a class="button" href="/models/{esc(m["id"])}/">Current record</a></div></section>{note}<section class="section ledger-timeline">{''.join(rows)}</section></main><footer></footer></body></html>'''

def diff_page(m):
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(m.get("name"))} revision diff — Open Model Weights</title><meta name="description" content="Compare two observed evidence snapshots for {esc(m.get("name"))}."><link rel="stylesheet" href="/styles.css"><script src="/history.js?v=1" defer></script></head><body class="diff-page" data-model-id="{esc(m["id"])}"><header class="site-header"><a class="brand" href="/">Open Model Weights</a></header><main><section class="page-hero"><div class="breadcrumbs"><a href="/">Home</a> / <a href="/models/{esc(m["id"])}/">{esc(m.get("name"))}</a> / Diff</div><p class="eyebrow">MODEL DIFF</p><h1>What changed?</h1><p class="lead">Compare any two evidence snapshots. Differences are source-derived and shown field by field without a quality judgment.</p></section><section class="section"><div class="diff-controls"><label>From<select id="diff-from"></select></label><span>→</span><label>To<select id="diff-to"></select></label><button id="diff-swap" type="button">Swap</button></div><div id="diff-summary" class="diff-summary"></div><div id="diff-output" class="diff-output"><p class="note">Loading evidence ledger…</p></div></section></main><footer></footer></body></html>'''

def build_compatibility(models,generated):
    nodes={}
    edges=[]
    compact=[]
    def node(node_id,node_type,label,meta=None):
        if node_id not in nodes:
            nodes[node_id]={"id":node_id,"type":node_type,"label":label}
            if meta:nodes[node_id]["meta"]=meta
    def edge(source,target,relation,evidence):
        edges.append({"source":source,"target":target,"relation":relation,"evidence":evidence})
    buckets=[16,24,32,48,80,96,192]
    for m in models:
        mid="model:"+m["id"];node(mid,"model",m.get("name"),{"developer":m.get("developer"),"url":f"/models/{m['id']}/"})
        lic=(m.get("license") or {}).get("name") or "Not declared"
        lid="license:"+slug(lic);node(lid,"license",lic);edge(mid,lid,"licensed_under","repository-or-publisher-evidence")
        fmts=sorted((m.get("weights") or {}).get("formats") or [])
        for x in fmts:
            fid="format:"+slug(x);node(fid,"format",x);edge(mid,fid,"publishes_format","repository-evidence")
        precisions=precision_list(m)
        for x in precisions:
            pid="precision:"+slug(x);node(pid,"precision",x.upper());edge(mid,pid,"observed_precision","repository-evidence")
        runtimes=runtime_list(m)
        for x in runtimes:
            rid="runtime:"+slug(x);node(rid,"runtime",x);edge(mid,rid,"runtime_signal","publisher-or-repository-evidence")
        bases=sorted((((m.get("lineage") or {}).get("base_model") or {}).get("models") or []))
        for x in bases:
            bid="base-reference:"+slug(x);node(bid,"base_model_reference",x);edge(mid,bid,"declares_base_model","publisher-metadata")
        hw=((m.get("hardware") or {}).get("weight_only_gb") or {})
        fit={}
        for mode in ("bf16_fp16","fp8_int8","int4"):
            val=hw.get(mode)
            if isinstance(val,(int,float)):
                fit[mode]=val
                bucket=next((b for b in buckets if val<=b),None)
                if bucket:
                    hid=f"memory:{mode}:{bucket}gb";node(hid,"memory_bucket",f"{mode} weight-only ≤ {bucket} GB",{"precision":mode,"gb":bucket})
                    edge(mid,hid,"fits_weight_only_estimate","derived-estimate")
        compact.append({
          "id":m["id"],"name":m.get("name"),"developer":m.get("developer"),
          "license":lic,"commercial_use":((m.get("license") or {}).get("commercial_use") or {}).get("status","unknown"),
          "context_tokens":context_value(m),"formats":fmts,"precisions":precisions,"runtimes":runtimes,
          "weight_only_gb":fit,"repository":(m.get("weights") or {}).get("repository"),
          "last_checked":(m.get("verification") or {}).get("checked_at"),
          "url":f"/models/{m['id']}/"
        })
    return {
      "schema_version":"1.0.0","generated_at":generated,
      "semantics":{
        "runtime_signal":"Declared/tagged/mentioned/artifact evidence; not necessarily independently executed.",
        "fits_weight_only_estimate":"Derived from verified parameter count and excludes KV cache, activations, runtime overhead and sharding."
      },
      "node_count":len(nodes),"edge_count":len(edges),"nodes":list(nodes.values()),"edges":edges,"models":compact
    }

def compatibility_page(graph):
    runtimes=sorted({x for m in graph["models"] for x in m["runtimes"]})
    formats=sorted({x for m in graph["models"] for x in m["formats"]})
    precisions=sorted({x for m in graph["models"] for x in m["precisions"]})
    def opts(vals):return "".join(f'<option value="{esc(x)}">{esc(x)}</option>' for x in vals)
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Model compatibility graph — Open Model Weights</title><meta name="description" content="Query source-derived relationships between open-weight models, runtimes, formats, precisions, licenses and weight-memory estimates."><link rel="stylesheet" href="/styles.css"><script src="/compatibility.js?v=1" defer></script></head><body class="compatibility-page"><header class="site-header"><a class="brand" href="/">Open Model Weights</a></header><main><section class="page-hero"><div class="breadcrumbs"><a href="/">Home</a> / Compatibility</div><p class="eyebrow">COMPATIBILITY GRAPH · {graph["node_count"]:,} NODES · {graph["edge_count"]:,} EDGES</p><h1>Which models actually fit the constraints?</h1><p class="lead">Query structured relationships between model evidence, runtime signals, published formats, observed precisions, license classes and weight-only memory estimates.</p></section><section class="section"><div class="compat-controls"><input id="compat-search" type="search" placeholder="Search model or developer…"><select id="compat-runtime"><option value="">Any runtime signal</option>{opts(runtimes)}</select><select id="compat-format"><option value="">Any format</option>{opts(formats)}</select><select id="compat-precision"><option value="">Any observed precision</option>{opts(precisions)}</select><select id="compat-commercial"><option value="">Any commercial-use class</option><option value="allowed">Allowed</option><option value="allowed-with-conditions">Allowed with conditions</option><option value="allowed-with-revenue-condition">Revenue condition</option><option value="separate-license-required">Separate license required</option><option value="not-allowed">Not allowed</option><option value="unknown">Unknown</option></select><label>Min context<input id="compat-context" type="number" min="0" step="1024" placeholder="tokens"></label><label>Max weight memory<input id="compat-memory" type="number" min="0" step="1" placeholder="GB"></label><select id="compat-memory-mode"><option value="int4">INT4 estimate</option><option value="fp8_int8">FP8 / INT8 estimate</option><option value="bf16_fp16">BF16 / FP16 estimate</option></select></div><div class="compat-meta"><p id="compat-count"></p><a href="/api/v1/compatibility.json">Compatibility graph JSON ↗</a></div><div id="compat-results" class="compat-results"></div><p class="note">Runtime relationships are evidence signals, not execution guarantees. Memory filters use weight-only estimates and exclude KV cache, activations, runtime overhead and sharding.</p></section></main><footer></footer></body></html>'''

def benchmark_protocol():
    return {
      "protocol_version":"1.0.0","benchmark_id":"omw-deployment-v1",
      "purpose":"Reproducible deployment-performance evidence for open-weight model artifacts; not a general intelligence or quality ranking.",
      "measurement":{
        "warmup_runs":2,"measured_runs":5,"concurrency":1,"temperature":0,
        "max_new_tokens":128,
        "report_aggregation":"median across measured runs; retain per-run raw values in evidence artifact"
      },
      "required_environment":[
        "model_id","source_repository_sha","weight_artifact_or_quantization","runtime_name","runtime_version",
        "runtime_command_or_config","hardware_vendor","hardware_model","device_count","device_memory_gb",
        "driver_version","framework_versions","operating_system","input_tokens","output_tokens","date_utc"
      ],
      "required_metrics":[
        {"name":"time_to_first_token_ms","unit":"ms"},
        {"name":"output_tokens_per_second","unit":"tokens/s"},
        {"name":"peak_device_memory_gb","unit":"GB"},
        {"name":"peak_host_memory_gb","unit":"GB","optional":True}
      ],
      "rules":[
        "No extrapolated or vendor-marketing numbers.",
        "Every accepted result must identify the exact source repository revision and runtime version.",
        "Results from different precisions, quantizations, runtimes or hardware are separate observations.",
        "Weight-only memory estimates from the registry are not benchmark measurements.",
        "Raw command/config and a public evidence artifact URL are required for accepted community submissions."
      ]
    }

def benchmark_schema():
    return {
      "$schema":"https://json-schema.org/draft/2020-12/schema",
      "$id":"https://openmodelweights.com/api/v1/benchmark.schema.json",
      "title":"Open Model Weights deployment benchmark result","type":"object",
      "required":["result_id","model_id","source_repository_sha","date_utc","runtime","hardware","artifact","metrics","evidence_url","measured_runs"],
      "properties":{
        "result_id":{"type":"string","minLength":6},"model_id":{"type":"string","minLength":1},
        "source_repository_sha":{"type":"string","minLength":7},"date_utc":{"type":"string"},
        "runtime":{"type":"object","required":["name","version"],"properties":{"name":{"type":"string"},"version":{"type":"string"},"command_or_config":{"type":"string"}}},
        "hardware":{"type":"object","required":["vendor","model","device_count","device_memory_gb"],"properties":{"vendor":{"type":"string"},"model":{"type":"string"},"device_count":{"type":"integer","minimum":1},"device_memory_gb":{"type":"number","exclusiveMinimum":0}}},
        "artifact":{"type":"object","required":["precision_or_quantization"],"properties":{"precision_or_quantization":{"type":"string"},"weight_file_or_variant":{"type":"string"}}},
        "metrics":{"type":"object","required":["time_to_first_token_ms","output_tokens_per_second","peak_device_memory_gb"],"properties":{"time_to_first_token_ms":{"type":"number","exclusiveMinimum":0},"output_tokens_per_second":{"type":"number","exclusiveMinimum":0},"peak_device_memory_gb":{"type":"number","exclusiveMinimum":0},"peak_host_memory_gb":{"type":"number","exclusiveMinimum":0}}},
        "measured_runs":{"type":"integer","minimum":3},"evidence_url":{"type":"string","pattern":"^https://"}
      }
    }

def benchmarks_page(results,protocol):
    n=len(results.get("results") or [])
    rows=""
    for r in (results.get("results") or [])[:100]:
        rows+=f'''<article class="benchmark-result"><div><span>{esc(r.get("model_id"))}</span><strong>{esc((r.get("hardware") or {}).get("model"))}</strong></div><div><b>{esc((r.get("runtime") or {}).get("name"))} {esc((r.get("runtime") or {}).get("version"))}</b><small>{esc((r.get("artifact") or {}).get("precision_or_quantization"))}</small></div><div><b>{esc((r.get("metrics") or {}).get("output_tokens_per_second"))} tok/s</b><small>{esc((r.get("metrics") or {}).get("time_to_first_token_ms"))} ms TTFT</small></div><a href="{esc(r.get("evidence_url"))}" rel="noopener">Evidence ↗</a></article>'''
    if not rows:
        rows='''<div class="benchmark-empty"><strong>No accepted benchmark measurements yet.</strong><p>The protocol and schema are live first. Measurements will appear only after they include exact model revision, runtime version, hardware, raw configuration and public evidence.</p></div>'''
    metrics="".join(f'<div><span>{esc(x["name"].replace("_"," "))}</span><strong>{esc(x["unit"])}</strong></div>' for x in protocol["required_metrics"])
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Reproducible model deployment benchmarks — Open Model Weights</title><meta name="description" content="A reproducible protocol for open-weight model deployment measurements tied to exact model revisions, runtimes and hardware."><link rel="stylesheet" href="/styles.css"></head><body class="benchmarks-page"><header class="site-header"><a class="brand" href="/">Open Model Weights</a></header><main><section class="page-hero"><div class="breadcrumbs"><a href="/">Home</a> / Benchmarks</div><p class="eyebrow">OMW DEPLOYMENT BENCHMARK · PROTOCOL v{esc(protocol["protocol_version"])}</p><h1>Measurements you can reproduce.</h1><p class="lead">Benchmarks are accepted only when tied to an exact model revision, runtime version, hardware environment and public evidence artifact. No marketing numbers and no extrapolation.</p><div class="hero-actions"><a class="button primary" href="https://github.com/openmodelweights/openmodelweights/issues/new?template=benchmark.yml" rel="noopener">Submit benchmark evidence ↗</a><a class="button" href="/benchmarks/protocol.json">Protocol JSON ↗</a><a class="button" href="/api/v1/benchmark.schema.json">Result schema ↗</a></div></section><section class="metric-strip"><div><span>Accepted results</span><strong>{n}</strong></div><div><span>Warmup runs</span><strong>{protocol["measurement"]["warmup_runs"]}</strong></div><div><span>Measured runs</span><strong>{protocol["measurement"]["measured_runs"]}</strong></div><div><span>Aggregation</span><strong>median</strong></div></section><section class="section"><p class="eyebrow">CORE METRICS</p><h2>Deployment performance, not a quality leaderboard.</h2><div class="benchmark-metrics">{metrics}</div></section><section class="section"><div class="section-head"><div><p class="eyebrow">ACCEPTED EVIDENCE</p><h2>Observed benchmark runs.</h2></div><p class="section-kicker">Every row must link back to public run evidence.</p></div><div class="benchmark-results">{rows}</div></section><section class="section content"><h2>Protocol rules</h2><ol>{''.join(f'<li>{esc(x)}</li>' for x in protocol["rules"])}</ol></section></main><footer></footer></body></html>'''

def mcp_page():
    tools=[
      ("search_models","Search verified models with evidence-aware constraints."),
      ("get_model","Fetch the full verified record for one model."),
      ("compare_models","Return neutral side-by-side fields for 2–4 model IDs."),
      ("find_compatible_models","Filter by runtime, format, precision, context, commercial-use class and weight-memory ceiling."),
      ("get_model_history","Read the observed evidence ledger for a model."),
      ("get_recent_changes","Read recent registry/repository change events."),
      ("get_registry_status","Return model count, schema and verification freshness."),
      ("get_benchmark_protocol","Return the reproducible deployment benchmark protocol.")
    ]
    cards="".join(f'<div class="mcp-tool"><code>{esc(n)}</code><p>{esc(d)}</p></div>' for n,d in tools)
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Open Model Weights MCP server</title><meta name="description" content="Connect AI agents to the Open Model Weights evidence registry through a stateless Streamable HTTP MCP server."><link rel="stylesheet" href="/styles.css"></head><body class="mcp-page"><header class="site-header"><a class="brand" href="/">Open Model Weights</a></header><main><section class="page-hero"><div class="breadcrumbs"><a href="/">Home</a> / MCP</div><p class="eyebrow">MODEL CONTEXT PROTOCOL</p><h1>Let AI apps query the evidence layer.</h1><p class="lead">The public MCP endpoint exposes read-only tools over the same verified registry, evidence history, compatibility graph and benchmark protocol used by the website.</p><div class="mcp-endpoint"><span>Streamable HTTP endpoint</span><code>https://openmodelweights.com/mcp</code></div></section><section class="section"><div class="mcp-tool-grid">{cards}</div><p class="note">The MCP surface is read-only. It returns evidence and constraints; it does not rank political choices, make legal determinations or turn popularity into model quality.</p></section></main><footer></footer></body></html>'''

def patch_explore():
    p=PUBLIC/"explore"/"index.html"
    if not p.exists():return
    text=p.read_text()
    if 'href="/history/"' in text:return
    extra='''<a class="tool-card" href="/history/"><span class="tool-stat">EVIDENCE LEDGER</span><h2>Model History</h2><p>Observed evidence snapshots and field-level diffs that accumulate over time.</p><strong>Open history →</strong></a><a class="tool-card" href="/compatibility/"><span class="tool-stat">RELATIONSHIP GRAPH</span><h2>Compatibility Graph</h2><p>Query runtimes, formats, precisions, licenses and weight-memory constraints together.</p><strong>Open graph →</strong></a><a class="tool-card" href="/benchmarks/"><span class="tool-stat">REPRODUCIBLE RUNS</span><h2>Deployment Benchmarks</h2><p>Measured performance tied to exact model revisions, runtimes and hardware.</p><strong>Open benchmarks →</strong></a>'''
    text=text.replace('</div></section></main>',extra+'</div></section></main>',1)
    text=text.replace('Six views over the same field-verified dataset','Nine views over the same field-verified dataset')
    p.write_text(text)

def patch_sitemap(models,generated):
    p=PUBLIC/"sitemap.xml"
    if not p.exists():return
    text=p.read_text()
    urls=["/history/","/compatibility/","/benchmarks/","/mcp/"]
    urls += [f'/models/{m["id"]}/history/' for m in models]
    urls += [f'/diff/{m["id"]}/' for m in models]
    for u in urls:
        full="https://openmodelweights.com"+u
        if full not in text:
            text=text.replace("</urlset>",f'<url><loc>{full}</loc><lastmod>{date(generated)}</lastmod></url>\n</urlset>')
    p.write_text(text)

def patch_llms(count):
    p=PUBLIC/"llms.txt"
    text=p.read_text() if p.exists() else "# Open Model Weights\n"
    if "## Evidence intelligence" not in text:
        text+=f'''
## Evidence intelligence
- https://openmodelweights.com/history/ — versioned evidence ledger and model diffs
- https://openmodelweights.com/compatibility/ — compatibility graph
- https://openmodelweights.com/benchmarks/ — reproducible deployment benchmark protocol/results
- https://openmodelweights.com/api/v1/compatibility.json — machine-readable compatibility graph
- https://openmodelweights.com/api/v1/evidence-runs.json — daily evidence manifests
- https://openmodelweights.com/mcp — MCP Streamable HTTP endpoint
- https://openmodelweights.com/mcp/ — MCP documentation
'''
    p.write_text(text)

def main():
    reg=json.loads(REGISTRY.read_text())
    models=reg.get("models",[])
    generated=reg.get("generated_at") or dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()
    previous=git_json("public/registry.json") or {"models":[]}
    ledgers=build_ledgers(models,previous,generated)
    manifest,run_index=run_manifest(models,ledgers,generated,reg.get("schema_version"))

    history_summary={
      "generated_at":generated,"model_count":len(models),
      "models":[{
        "id":m["id"],"name":m.get("name"),"developer":m.get("developer"),
        "snapshot_count":ledgers[m["id"]]["snapshot_count"],"diff_count":ledgers[m["id"]]["diff_count"],
        "history_url":f"https://openmodelweights.com/models/{m['id']}/history/",
        "evidence_url":f"https://openmodelweights.com/api/v1/evidence/{m['id']}.json"
      } for m in models]
    }
    write_json(API/"history.json",history_summary)

    graph=build_compatibility(models,generated)
    write_json(API/"compatibility.json",graph)

    results_path=DATA/"benchmark-results.json"
    if results_path.exists():
        results=json.loads(results_path.read_text())
    else:
        results={"schema_version":"1.0.0","protocol_version":"1.0.0","results":[]}
        write_json(results_path,results)
    protocol=benchmark_protocol()
    write_json(PUBLIC/"benchmarks"/"protocol.json",protocol)
    write_json(API/"benchmark.schema.json",benchmark_schema())
    write_json(API/"benchmarks.json",{"generated_at":generated,"protocol":"/benchmarks/protocol.json","result_count":len(results.get("results") or []),"results":results.get("results") or []})

    d=PUBLIC/"history";d.mkdir(parents=True,exist_ok=True);(d/"index.html").write_text(history_index_page(models,ledgers))
    for m in models:
        d=PUBLIC/"models"/m["id"]/"history";d.mkdir(parents=True,exist_ok=True);(d/"index.html").write_text(model_history_page(m,ledgers[m["id"]]))
        d=PUBLIC/"diff"/m["id"];d.mkdir(parents=True,exist_ok=True);(d/"index.html").write_text(diff_page(m))
    d=PUBLIC/"compatibility";d.mkdir(parents=True,exist_ok=True);(d/"index.html").write_text(compatibility_page(graph))
    d=PUBLIC/"benchmarks";d.mkdir(parents=True,exist_ok=True);(d/"index.html").write_text(benchmarks_page(results,protocol))
    d=PUBLIC/"mcp";d.mkdir(parents=True,exist_ok=True);(d/"index.html").write_text(mcp_page())
    write_json(PUBLIC/".well-known"/"mcp.json",{
      "name":"Open Model Weights","endpoint":"https://openmodelweights.com/mcp",
      "transport":"streamable-http","protocols":["2026-07-28","2025-11-25"],
      "documentation":"https://openmodelweights.com/mcp/","read_only":True
    })
    patch_explore()
    patch_sitemap(models,generated)
    patch_llms(len(models))
    print(json.dumps({
      "models":len(models),"evidence_ledgers":len(ledgers),
      "evidence_run":manifest["date"],"compatibility_nodes":graph["node_count"],
      "compatibility_edges":graph["edge_count"],"benchmark_results":len(results.get("results") or [])
    },indent=2))

if __name__=="__main__":
    main()
