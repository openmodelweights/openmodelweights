#!/usr/bin/env python3
from __future__ import annotations

import concurrent.futures
import copy
import datetime as dt
import html
import json
import math
import os
import re
import time
from pathlib import Path
from urllib.parse import quote

import requests
import yaml

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "public"
REGISTRY = PUBLIC / "registry.json"
SOURCE = ROOT / "data" / "models-source.json"
REPORT = ROOT / "data" / "verification-report.json"
TODAY = dt.datetime.now(dt.timezone.utc).date().isoformat()
NOW = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()
UA = "OpenModelWeights/0.3 (+https://openmodelweights.com; source verification)"

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": UA, "Accept": "application/json,text/plain,*/*"})

TARGET_MODELS=int(os.getenv("OMW_TARGET_MODELS","700"))

def load_previous_models():
    try:
        if REGISTRY.exists():
            data=json.loads(REGISTRY.read_text())
            return {m["id"]:m for m in data.get("models",[]) if m.get("id")}
    except Exception:
        pass
    return {}

PREVIOUS_MODELS=load_previous_models()

PERMISSIVE = {
    "apache-2.0": ("allowed", "Apache-2.0 permits commercial use subject to the license conditions."),
    "mit": ("allowed", "MIT permits commercial use subject to the license conditions."),
    "bsd-2-clause": ("allowed", "BSD-2-Clause permits commercial use subject to the license conditions."),
    "bsd-3-clause": ("allowed", "BSD-3-Clause permits commercial use subject to the license conditions."),
    "cc-by-4.0": ("allowed", "CC BY 4.0 permits commercial use subject to attribution and the license conditions."),
}

RUNTIME_PATTERNS = {
    "Transformers": r"\btransformers\b",
    "vLLM": r"\bvllm\b",
    "SGLang": r"\bsglang\b",
    "llama.cpp": r"\bllama\.cpp\b",
    "TensorRT-LLM": r"\btensorrt[- ]?llm\b",
    "NeMo": r"\bnemo\b",
    "Diffusers": r"\bdiffusers\b",
    "MLX": r"\bmlx\b",
    "ONNX Runtime": r"\bonnx(?: runtime)?\b",
    "TGI": r"\btext generation inference\b|\btgi\b",
    "Ollama": r"\bollama\b",
    "mistral-common": r"\bmistral-common\b",
}

WEIGHT_EXTS = (
    ".safetensors", ".bin", ".pt", ".pth", ".gguf", ".onnx", ".nemo",
    ".ckpt", ".npz", ".h5", ".tflite", ".mlmodel", ".params"
)

def get(url, *, as_json=False, timeout=30):
    last = None
    for attempt in range(4):
        try:
            r = SESSION.get(url, timeout=timeout, allow_redirects=True)
            if r.status_code == 200:
                return r.json() if as_json else r.text
            if r.status_code in (401, 403, 404):
                return None
            last = f"HTTP {r.status_code}"
        except Exception as e:
            last = str(e)
        time.sleep(1.2 * (attempt + 1))
    raise RuntimeError(f"{url}: {last}")

def norm_list(v):
    if v is None:
        return []
    if isinstance(v, list):
        return [str(x) for x in v if x is not None]
    if isinstance(v, dict):
        if "id" in v:
            return [str(v["id"])]
        return [str(x) for x in v.values() if isinstance(x, (str, int, float))]
    return [str(v)]

def parse_frontmatter(readme):
    if not readme:
        return {}
    m = re.match(r"^\s*---\s*\n(.*?)\n---\s*(?:\n|$)", readme, re.S)
    if not m:
        return {}
    try:
        data = yaml.safe_load(m.group(1))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}

def deep_candidates(obj, wanted, path=""):
    out = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            p = f"{path}.{k}" if path else k
            if k in wanted and isinstance(v, (int, float)) and 64 <= v <= 10_000_000:
                out.append((p, int(v)))
            out.extend(deep_candidates(v, wanted, p))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            out.extend(deep_candidates(v, wanted, f"{path}[{i}]"))
    return out

def parse_human_number(s):
    s = s.strip().upper().replace(",", "")
    m = re.match(r"(\d+(?:\.\d+)?)\s*([KMBT]?)", s)
    if not m:
        return None
    n = float(m.group(1))
    mult = {"": 1, "K": 1_000, "M": 1_000_000, "B": 1_000_000_000, "T": 1_000_000_000_000}[m.group(2)]
    return int(n * mult)

def context_from_sources(config, readme):
    keys = {
        "max_position_embeddings", "max_seq_len", "max_seq_length",
        "model_max_length", "seq_length", "context_length", "max_sequence_length"
    }
    candidates = deep_candidates(config or {}, keys)
    if candidates:
        path, value = max(candidates, key=lambda x: x[1])
        return {"value": value, "display": f"{value:,} tokens", "status": "verified",
                "evidence": [{"source": "config.json", "detail": path}]}
    if readme:
        patterns = [
            r"(?:context window|context length|maximum context|supports? context)[^\n]{0,80}?([\d.]+\s*[KkMm]?)\s*(?:tokens?)?",
            r"([\d.]+\s*[KkMm]?)\s*(?:token )?context window",
        ]
        vals = []
        for pat in patterns:
            for hit in re.findall(pat, readme, re.I):
                v = parse_human_number(hit)
                if v and 512 <= v <= 10_000_000:
                    vals.append(v)
        if vals:
            value = max(vals)
            return {"value": value, "display": f"{value:,} tokens", "status": "verified",
                    "evidence": [{"source": "README.md", "detail": "explicit context statement"}]}
    return {"value": None, "display": "Not declared in checked config/model card",
            "status": "not-disclosed", "evidence": []}

def exact_files(api):
    siblings = api.get("siblings") or []
    names = []
    for s in siblings:
        if isinstance(s, dict):
            n = s.get("rfilename") or s.get("path")
        else:
            n = str(s)
        if n:
            names.append(n)
    return sorted(set(names))

def weight_files(files):
    out = []
    for f in files:
        low = f.lower()
        if low.endswith(WEIGHT_EXTS) or low.endswith(".safetensors.index.json") or low.endswith(".bin.index.json"):
            out.append(f)
    return out

def format_info(repo, files, api, config, readme):
    joined = "\n".join([repo] + files)
    low = joined.lower()
    formats = []
    if any(x.lower().endswith(".safetensors") for x in files):
        formats.append("Safetensors")
    if any(x.lower().endswith((".bin", ".pt", ".pth")) for x in files):
        formats.append("PyTorch")
    if any(x.lower().endswith(".gguf") for x in files):
        formats.append("GGUF")
    if any(x.lower().endswith(".onnx") for x in files):
        formats.append("ONNX")
    if any(x.lower().endswith(".nemo") for x in files):
        formats.append("NeMo")
    if any(x.lower().endswith(".tflite") for x in files):
        formats.append("TFLite")
    if any(x.lower().endswith(".mlmodel") for x in files):
        formats.append("CoreML")

    dtype_evidence = []
    safetensors = api.get("safetensors")
    if isinstance(safetensors, dict):
        params = safetensors.get("parameters")
        if isinstance(params, dict):
            dtype_evidence.extend(str(k).upper() for k in params.keys())
    torch_dtype = None
    if isinstance(config, dict):
        torch_dtype = config.get("torch_dtype") or config.get("dtype")
        if torch_dtype:
            dtype_evidence.append(str(torch_dtype).upper())
    scan = (" ".join(dtype_evidence) + " " + repo + " " + " ".join(files)).upper()

    def flag(label, needles):
        hit = any(n in scan for n in needles)
        return {"available": bool(hit), "status": "verified" if hit else "not-observed"}

    precision = {
        "bf16": flag("bf16", ["BF16", "BFLOAT16"]),
        "fp16": flag("fp16", ["FP16", "FLOAT16", "F16"]),
        "fp8": flag("fp8", ["FP8", "FLOAT8"]),
        "int8": flag("int8", ["INT8", "8BIT", "8-BIT"]),
        "int4": flag("int4", ["INT4", "4BIT", "4-BIT", "GPTQ"]),
        "gguf": {"available": any(x.lower().endswith(".gguf") for x in files),
                 "status": "verified" if any(x.lower().endswith(".gguf") for x in files) else "not-observed"},
    }
    return {"formats": formats or ["No recognized weight format observed"], "precision": precision,
            "dtype_evidence": sorted(set(dtype_evidence))}

def license_info(model, card):
    lid = str(card.get("license") or "").strip().lower()
    lname = str(card.get("license_name") or "").strip()
    llink = str(card.get("license_link") or "").strip()
    developer = model.get("developer", "")
    family = model.get("family", "")
    name = model.get("name", "")
    result = {
        "id": lid or None,
        "name": lname or (lid if lid else "Not declared in model-card metadata"),
        "url": llink or None,
        "status": "verified" if (lid or lname or llink) else "not-disclosed",
        "commercial_use": {"status": "unknown", "label": "Not determined from declared license",
                           "basis": None}
    }

    if lid in PERMISSIVE:
        st, basis = PERMISSIVE[lid]
        result["commercial_use"] = {"status": st, "label": "Allowed under license conditions", "basis": basis}
    elif (lname.lower() == "mrl" or "mistral research license" in lname.lower() or
          (llink and "MRL-" in llink.upper())):
        result["commercial_use"] = {
            "status": "not-allowed-without-commercial-license",
            "label": "Non-commercial research only without a separate commercial license",
            "basis": llink or "Mistral Research License"
        }
    elif developer == "Meta" or "llama" in lname.lower() or "llama" in lid:
        if "4" in family or "Llama-4" in name:
            fallback = "https://github.com/meta-llama/llama-models/blob/main/models/llama4/LICENSE"
        else:
            fallback = llink or "https://www.llama.com/llama3/license/"
        result["url"] = result["url"] or fallback
        result["commercial_use"] = {
            "status": "allowed-with-conditions",
            "label": "Commercial use allowed subject to Llama community-license conditions",
            "basis": result["url"]
        }
    elif developer == "Google" and "gemma" in (family + " " + name).lower():
        result["url"] = result["url"] or "https://ai.google.dev/gemma/terms"
        result["commercial_use"] = {
            "status": "allowed-with-conditions",
            "label": "Commercial use permitted subject to Gemma Terms",
            "basis": result["url"]
        }
    elif developer == "NVIDIA" or "nvidia" in lname.lower():
        result["url"] = result["url"] or "https://www.nvidia.com/en-us/agreements/enterprise-software/nvidia-open-model-license/"
        result["commercial_use"] = {
            "status": "allowed-with-conditions",
            "label": "Commercially usable subject to NVIDIA license conditions",
            "basis": result["url"]
        }
    return result

def training_info(files, readme):
    recipe_files = [f for f in files if re.search(r"(^|/)(train|training|recipe|recipes|finetune|fine-tune|sft|dpo|grpo|rlhf|pretrain|scripts?)(/|[_.-])", f, re.I)]
    has_section = bool(readme and re.search(r"^#{1,4}\s+.*(?:training|fine[- ]?tun|pre[- ]?train|recipe)", readme, re.I | re.M))
    urls = []
    if readme:
        for line in readme.splitlines():
            if re.search(r"recipe|training script|train(?:ing)? code|fine[- ]?tun", line, re.I):
                urls.extend(re.findall(r"https?://[^\s)>]+", line))
    urls = list(dict.fromkeys(urls))[:12]
    if recipe_files:
        status = "recipe-or-training-files-present"
    elif has_section:
        status = "training-described-in-model-card"
    else:
        status = "not-disclosed-in-checked-repository"
    return {"status": status, "files": recipe_files, "links": urls, "evidence": ["README.md"] if has_section else []}

def data_disclosure(card, readme):
    datasets = norm_list(card.get("datasets"))
    if datasets:
        return {"status": "dataset-metadata-declared", "datasets": datasets,
                "evidence": [{"source": "model-card metadata", "field": "datasets"}]}
    if readme and re.search(r"^#{1,4}\s+.*(?:training data|dataset|data sources?)", readme, re.I | re.M):
        return {"status": "described-in-model-card", "datasets": [],
                "evidence": [{"source": "README.md", "detail": "data/dataset section present"}]}
    return {"status": "not-disclosed-in-standard-metadata-or-obvious-model-card-section",
            "datasets": [], "evidence": []}

def base_model_info(card):
    bases = norm_list(card.get("base_model"))
    rel = card.get("base_model_relation")
    if bases:
        return {"status": "declared", "models": bases, "relation": rel,
                "evidence": [{"source": "model-card metadata", "field": "base_model"}]}
    return {"status": "not-declared", "models": [], "relation": rel, "evidence": []}

def runtime_info(api, card, readme, formats):
    library = api.get("library_name") or card.get("library_name")
    tags = [str(t) for t in (api.get("tags") or [])]
    declared = []
    mentioned = []
    if library:
        declared.append(str(library))
    for runtime, pat in RUNTIME_PATTERNS.items():
        if any(re.fullmatch(pat, t, re.I) for t in tags):
            declared.append(runtime)
        elif readme and re.search(pat, readme, re.I):
            mentioned.append(runtime)
    artifacts = []
    if "GGUF" in formats:
        artifacts.append("GGUF artifact present (commonly used with llama.cpp-compatible runtimes)")
    if "ONNX" in formats:
        artifacts.append("ONNX artifact present")
    return {
        "declared_library": library,
        "pipeline_tag": api.get("pipeline_tag") or card.get("pipeline_tag"),
        "declared": sorted(set(declared)),
        "mentioned_in_model_card": sorted(set(mentioned) - set(declared)),
        "artifact_signals": artifacts,
        "tested_by_openmodelweights": False,
    }

def parameter_total(model, api):
    existing = model.get("model", {}).get("total_parameters_billions")
    if isinstance(existing, (int, float)):
        return float(existing)
    st = api.get("safetensors")
    if isinstance(st, dict):
        total = st.get("total")
        if isinstance(total, int) and total > 0:
            return total / 1e9
        params = st.get("parameters")
        if isinstance(params, dict):
            vals = [v for v in params.values() if isinstance(v, int)]
            if vals:
                return sum(vals) / 1e9
    return None

def hardware(total_b):
    if not total_b:
        return {"status": "not-calculated", "note": "Total parameter count unavailable."}
    return {
        "status": "estimated",
        "weight_only_gb": {
            "bf16_fp16": round(total_b * 2, 2),
            "fp8_int8": round(total_b, 2),
            "int4": round(total_b * 0.5, 2),
        },
        "note": "Weight-only decimal-GB estimate from total parameter count; excludes KV cache, activations, runtime overhead, optimizer state and sharding."
    }

def repo_id(model):
    url = model.get("weights", {}).get("repository") or ""
    marker = "huggingface.co/"
    if marker in url:
        return url.split(marker, 1)[1].strip("/")
    for s in model.get("sources", []):
        u = s.get("url", "")
        if marker in u and not u.rstrip("/").endswith("/models"):
            return u.split(marker, 1)[1].strip("/")
    raise ValueError(f"No HF repository for {model.get('id')}")

def verify_one(seed):
    model = copy.deepcopy(seed)
    model.setdefault("model",{})
    model.setdefault("lineage",{})
    model.setdefault("training_assets",{})
    rid = repo_id(model)
    api_url = f"https://huggingface.co/api/models/{rid}"
    api = get(api_url, as_json=True)
    if not api:
        return {"ok": False, "id": model.get("id"), "repo": rid, "error": "Hugging Face model API unavailable"}

    # Fast daily freshness path: one API revision check is enough when the
    # publisher repository SHA has not changed since the previous full field verification.
    prev=PREVIOUS_MODELS.get(model.get("id"))
    prev_sha=((prev or {}).get("hub") or {}).get("sha")
    api_sha=api.get("sha")
    if prev and prev_sha and api_sha and prev_sha==api_sha and (prev.get("verification") or {}).get("level")=="field-verified":
        reused=copy.deepcopy(prev)
        reused.setdefault("hub",{})
        reused["hub"].update({
            "last_modified":api.get("lastModified"),
            "created_at":api.get("createdAt"),
            "downloads":api.get("downloads"),
            "likes":api.get("likes"),
            "sha":api_sha,
            "library_name":api.get("library_name"),
            "pipeline_tag":api.get("pipeline_tag"),
            "tags":api.get("tags") or [],
        })
        reused.setdefault("verification",{})
        reused["verification"]["checked_at"]=TODAY
        reused["verification"]["checked_at_iso"]=NOW
        reused["verification"].setdefault("full_verified_at",(prev.get("verification") or {}).get("checked_at",TODAY))
        reused["verification"]["mode"]="repository-revision-unchanged"
        if model.get("discovery"):
            reused["discovery"]=copy.deepcopy(model["discovery"])
        history=reused["verification"].setdefault("history",[])
        event={"date":TODAY,"event":"Repository revision check","detail":"Official Hugging Face repository SHA unchanged; prior field evidence retained."}
        if not history or history[0].get("date")!=TODAY or history[0].get("event")!="Repository revision check":
            history.insert(0,event)
        reused["verification"]["history"]=history[:30]
        return {"ok":True,"model":reused,"readme":reused["verification"].get("readme_accessible"),"config":reused["verification"].get("config_accessible"),"reused":True}

    files = exact_files(api)
    readme = get(f"https://huggingface.co/{rid}/resolve/main/README.md") if "README.md" in files else None
    config = get(f"https://huggingface.co/{rid}/resolve/main/config.json", as_json=True) if "config.json" in files else None
    card = {}
    if isinstance(api.get("cardData"), dict):
        card.update(api["cardData"])
    front = parse_frontmatter(readme)
    for k, v in front.items():
        card.setdefault(k, v)

    wf = weight_files(files)
    if not wf:
        return {"ok":False,"id":model.get("id"),"repo":rid,"error":"No recognized weight artifacts in source repository"}
    fmts = format_info(rid, files, api, config, readme or "")
    lic = license_info(model, card)
    total_b = parameter_total(model, api)
    context = context_from_sources(config, readme or "")
    base = base_model_info(card)
    train = training_info(files, readme or "")
    data = data_disclosure(card, readme or "")
    runtime = runtime_info(api, card, readme or "", fmts["formats"])

    gated = api.get("gated")
    access = "gated" if gated else "public"
    if isinstance(gated, str) and gated not in ("false", "False"):
        access = f"gated ({gated})"

    license_files = [f for f in files if re.search(r"(^|/)(license|licence|copying)(\.|$)", f, re.I)]
    source = f"https://huggingface.co/{rid}"

    model["weights"] = {
        "status": "verified-available" if wf else "repository-verified-no-recognized-weight-file",
        "repository": source,
        "access": access,
        "exact_files": wf,
        "file_count": len(wf),
        "formats": fmts["formats"],
        "precision_availability": fmts["precision"],
        "dtype_evidence": fmts["dtype_evidence"],
        "evidence": [{"source": api_url, "type": "Hugging Face model API siblings"}],
    }
    model["license"] = lic
    model["license"]["repository_license_files"] = license_files
    model["model"]["context"] = context
    model["model"]["total_parameters_billions"] = total_b
    if total_b and str(model["model"].get("parameters") or "").lower() in ("","unknown","pending verification","not declared"):
        model["model"]["parameters"] = f"{total_b:g}B"
    if not model["model"].get("modality") or model["model"].get("modality")=="Not declared":
        pipeline=api.get("pipeline_tag") or card.get("pipeline_tag")
        model["model"]["modality"] = str(pipeline).replace("-"," ").title() if pipeline else "Not declared"
    model["hardware"] = hardware(total_b)
    model["lineage"]["base_model"] = base
    model["training_assets"] = {
        "training_recipe": train,
        "data_disclosure": data,
        "evaluations": "Not classified by automated verifier",
        "intermediate_checkpoints": "Not classified by automated verifier",
    }
    model["runtime_support"] = runtime
    model["sources"] = [
        {"type": "model_repository", "url": source, "tier": "primary"},
        {"type": "model_api", "url": api_url, "tier": "primary"},
        {"type": "model_card", "url": f"{source}/blob/main/README.md", "tier": "primary", "available": bool(readme)},
        {"type": "config", "url": f"{source}/blob/main/config.json", "tier": "primary", "available": bool(config)},
    ]
    if lic.get("url"):
        model["sources"].append({"type": "license", "url": lic["url"], "tier": "primary-or-declared"})
    model["verification"] = {
        "level": "field-verified",
        "checked_at": TODAY,
        "checked_at_iso": NOW,
        "method": "Hugging Face API + repository file list + model card + config.json",
        "mode": "full-field-verification",
        "full_verified_at": TODAY,
        "readme_accessible": bool(readme),
        "config_accessible": bool(config),
        "fields": {
            "license": lic["status"],
            "commercial_use": "classified" if lic["commercial_use"]["status"] != "unknown" else "unknown",
            "context": context["status"],
            "weight_files": "verified" if wf else "no-recognized-artifacts",
            "formats": "verified",
            "base_model": base["status"],
            "training_recipe": train["status"],
            "data_disclosure": data["status"],
            "runtime_support": "source-derived-not-runtime-tested",
        },
        "history": [
            {"date": TODAY, "event": "Field-by-field verification",
             "detail": "Checked Hugging Face API metadata, exact repository file list, model card and config when accessible."},
            {"date": seed.get("verification", {}).get("checked_at", TODAY),
             "event": "Registry record created", "detail": f"Previous verification level: {seed.get('verification', {}).get('level', 'unknown')}."},
        ],
    }
    model["hub"] = {
        "last_modified": api.get("lastModified"),
        "created_at": api.get("createdAt"),
        "downloads": api.get("downloads"),
        "likes": api.get("likes"),
        "sha": api.get("sha"),
        "library_name": api.get("library_name"),
        "pipeline_tag": api.get("pipeline_tag"),
        "tags": api.get("tags") or [],
    }
    return {"ok": True, "model": model, "readme": bool(readme), "config": bool(config)}

def esc(v):
    return html.escape(str(v if v is not None else ""), quote=True)

def fmt_gb(v):
    if v is None:
        return "Not calculated"
    return f"~{v:,.1f} GB"

def source_links(model, source_type=None):
    sources = model.get("sources", [])
    if source_type:
        sources = [s for s in sources if s.get("type") == source_type]
    return sources

def evidence_link(label, url):
    return f'<a class="evidence-link" href="{esc(url)}" rel="noopener">{esc(label)} ↗</a>'

def model_page(m):
    rid = repo_id(m)
    ctx = m["model"]["context"]
    ctx_display = str(ctx.get("display") or "Not verified")
    if ctx_display.lower().endswith(" tokens"):
        ctx_value = ctx_display[:-7].strip()
        ctx_unit = "tokens"
    else:
        ctx_value = ctx_display
        ctx_unit = ""
    lic = m["license"]
    hw = m["hardware"]
    weights = m["weights"]
    base = m["lineage"]["base_model"]
    ta = m["training_assets"]
    rt = m["runtime_support"]
    repo = weights["repository"]
    exact = weights.get("exact_files", [])
    format_chips = "".join(f"<span>{esc(x)}</span>" for x in weights.get("formats", []))
    precisions = []
    labels = {"bf16":"BF16","fp16":"FP16","fp8":"FP8","int8":"INT8","int4":"INT4","gguf":"GGUF"}
    for k,v in weights.get("precision_availability",{}).items():
        precisions.append(f'<span class="precision {"yes" if v.get("available") else "no"}">{labels.get(k,k)}: {"observed" if v.get("available") else "not observed"}</span>')
    file_items = "".join(
        f'<li><a href="{repo}/blob/main/{quote(f, safe="/")}" rel="noopener"><code>{esc(f)}</code></a></li>' for f in exact
    ) or "<li>No recognized weight artifact was listed by the API.</li>"
    bases = ", ".join(base.get("models", [])) or "Not declared in model-card metadata"
    datasets = ta["data_disclosure"].get("datasets") or []
    dataset_html = ", ".join(esc(x) for x in datasets) if datasets else esc(ta["data_disclosure"]["status"])
    recipe = ta["training_recipe"]
    recipe_summary = recipe["status"]
    if recipe.get("files"):
        recipe_summary += " · " + ", ".join(recipe["files"][:6])
    runtime_rows = []
    if rt.get("declared_library"):
        runtime_rows.append(("Declared library", rt["declared_library"]))
    runtime_rows.append(("Declared/tagged", ", ".join(rt["declared"]) or "None observed"))
    runtime_rows.append(("Mentioned in model card", ", ".join(rt["mentioned_in_model_card"]) or "None observed"))
    runtime_rows.append(("Artifact signals", ", ".join(rt["artifact_signals"]) or "None"))
    runtime_rows.append(("Tested by Open Model Weights", "No — source-derived support only"))
    runtime_html = "".join(f"<div><span>{esc(a)}</span><strong>{esc(b)}</strong></div>" for a,b in runtime_rows)

    license_evidence = lic.get("url") or repo + "/blob/main/README.md"
    jsonld = json.dumps({
        "@context":"https://schema.org","@type":"Dataset","name":m["name"]+" model weights",
        "url":f"https://openmodelweights.com/models/{m['id']}/","creator":{"@type":"Organization","name":m["developer"]},
        "dateModified":TODAY,"sameAs":repo
    }, separators=(",",":"))

    header = '<header class="site-header"><a class="brand" href="/">Open Model Weights</a><nav><a href="/models/">Models</a><a href="/developers/">Developers</a><a href="/explore/">Explore</a><a href="/changes/">Changes</a><a href="/verification/">Verification</a><a href="/methodology/">Methodology</a><a href="/about/">About</a></nav></header>'
    footer = '<footer><div><strong>Open Model Weights</strong><p>The independent registry for open-weight AI.</p></div><div class="footer-links"><a href="/registry.json">Registry JSON</a><a href="/verification/">Verification</a><a href="/llms.txt">llms.txt</a></div></footer>'
    title = f'{m["name"]} — verified weights, license, hardware & runtime | Open Model Weights'
    desc = f'Field-by-field verification for {m["name"]}: exact weight files, license, commercial-use classification, context, formats, base model, training/data disclosure and runtime support.'
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(title)}</title><meta name="description" content="{esc(desc)}"><link rel="canonical" href="https://openmodelweights.com/models/{esc(m["id"])}/"><meta name="robots" content="index,follow,max-snippet:-1"><link rel="stylesheet" href="/styles.css"><script type="application/ld+json">{jsonld}</script></head><body>{header}<main>
<section class="page-hero model-head"><div class="model-title"><div class="breadcrumbs"><a href="/">Home</a> / <a href="/models/">Models</a> / {esc(m["name"])}</div><p class="eyebrow">{esc(m["developer"].upper())} · FIELD-VERIFIED</p><h1>{esc(m["name"])}</h1><p class="lead">Checked against the listed Hugging Face source repository on {TODAY}. Unknown values are left explicit rather than inferred.</p><div class="hero-actions model-hero-actions"><a class="button primary" href="{esc(repo)}" rel="noopener">Source repository ↗</a><a class="button compare-model-button" href="/compare/?models={esc(m["id"])}">Compare this model →</a><a class="button history-model-button" href="/models/{esc(m["id"])}/history/">History & diff →</a><a class="button machine-model-button" href="/api/v1/models/{esc(m["id"])}.json">Machine-readable JSON ↗</a><span class="pill verified">Field-verified {TODAY}</span></div></div>
<aside class="model-snapshot" aria-label="Model snapshot">
  <div class="snapshot-kicker"><span>MODEL SNAPSHOT</span><strong>{esc(m["developer"])}</strong></div>
  <div class="snapshot-primary">
    <div><span>PARAMETERS</span><strong>{esc(m["model"].get("parameters") or "Not verified")}</strong></div>
    <div class="snapshot-context"><span>CONTEXT</span><strong><b>{esc(ctx_value)}</b>{f'<em>{esc(ctx_unit)}</em>' if ctx_unit else ''}</strong></div>
  </div>
  <dl class="snapshot-details">
    <div><dt>License</dt><dd>{esc(lic["name"])}</dd></div>
    <div><dt>Access</dt><dd>{esc(weights["access"])}</dd></div>
    <div><dt>Weight files</dt><dd>{len(exact)}</dd></div>
  </dl>
  <div class="snapshot-status"><i aria-hidden="true"></i><span>Field-verified registry record</span></div>
</aside></section>
<nav class="detail-nav"><a href="#weights">Weights</a><a href="#license">License</a><a href="#hardware">Hardware</a><a href="#formats">Formats</a><a href="#lineage">Lineage</a><a href="#training-assets">Training assets</a><a href="#runtime">Runtime</a><a href="#sources">Sources</a><a href="#verification">Verification</a></nav>
<section id="weights" class="model-section"><p class="eyebrow">01 · WEIGHTS</p><h2>Exact repository artifacts</h2><div class="info-panel"><div><span>Status</span><strong>{esc(weights["status"])}</strong></div><div><span>Access</span><strong>{esc(weights["access"])}</strong></div><div><span>Repository</span><strong>{esc(rid)}</strong></div><div><span>Recognized weight files</span><strong>{len(exact)}</strong></div></div><details class="file-details"><summary>Show all {len(exact)} exact weight files</summary><ul class="file-list">{file_items}</ul></details>{evidence_link("HF API file listing", source_links(m,"model_api")[0]["url"])}</section>
<section id="license" class="model-section"><p class="eyebrow">02 · LICENSE</p><h2>License & commercial use</h2><div class="info-panel"><div><span>Declared license</span><strong>{esc(lic["name"])}</strong></div><div><span>License ID</span><strong>{esc(lic.get("id") or "Not declared")}</strong></div><div><span>Commercial use</span><strong>{esc(lic["commercial_use"]["label"])}</strong></div><div><span>Repository license files</span><strong>{esc(", ".join(lic.get("repository_license_files",[])) or "None observed")}</strong></div></div><p class="note">Classification describes the checked license terms; it is not legal advice.</p>{evidence_link("License / model-card evidence", license_evidence)}</section>
<section id="hardware" class="model-section"><p class="eyebrow">03 · HARDWARE</p><h2>Weight-memory estimate</h2><div class="hardware-grid"><div><span>BF16 / FP16</span><strong>{fmt_gb(hw.get("weight_only_gb",{}).get("bf16_fp16"))}</strong></div><div><span>FP8 / INT8</span><strong>{fmt_gb(hw.get("weight_only_gb",{}).get("fp8_int8"))}</strong></div><div><span>INT4</span><strong>{fmt_gb(hw.get("weight_only_gb",{}).get("int4"))}</strong></div></div><p class="note">{esc(hw.get("note"))}</p></section>
<section id="formats" class="model-section"><p class="eyebrow">04 · FORMATS</p><h2>Formats & precision evidence</h2><div class="chips">{format_chips}</div><div class="precision-grid">{"".join(precisions)}</div><p class="note">“Not observed” means no matching repository artifact/name/dtype signal was found; it does not prove no third-party conversion exists.</p></section>
<section id="lineage" class="model-section"><p class="eyebrow">05 · LINEAGE</p><h2>Base model & family</h2><div class="info-panel"><div><span>Family</span><strong>{esc(m.get("family"))}</strong></div><div><span>Variant</span><strong>{esc(m.get("variant"))}</strong></div><div><span>Declared base model</span><strong>{esc(bases)}</strong></div><div><span>Relation</span><strong>{esc(base.get("relation") or "Not declared")}</strong></div></div></section>
<section id="training-assets" class="model-section"><p class="eyebrow">06 · TRAINING ASSETS</p><h2>Recipe & data disclosure</h2><div class="info-panel"><div><span>Training recipe</span><strong>{esc(recipe_summary)}</strong></div><div><span>Data disclosure</span><strong>{dataset_html}</strong></div><div><span>Evaluations</span><strong>{esc(ta["evaluations"])}</strong></div><div><span>Intermediate checkpoints</span><strong>{esc(ta["intermediate_checkpoints"])}</strong></div></div></section>
<section id="runtime" class="model-section"><p class="eyebrow">07 · RUNTIME SUPPORT</p><h2>Declared and mentioned runtimes</h2><div class="profile">{runtime_html}</div><p class="note">Open Model Weights does not claim runtime compatibility unless it is declared, tagged, mentioned by the publisher, or evidenced by an artifact. No inference benchmark is implied.</p></section>
<section id="sources" class="model-section"><p class="eyebrow">08 · SOURCES</p><h2>Field evidence</h2><div class="source-list">{"".join(f'<div><span>{esc(s["type"])}</span><a href="{esc(s["url"])}" rel="noopener">{esc(s["url"])}</a></div>' for s in m["sources"])}</div></section>
<section id="verification" class="model-section"><p class="eyebrow">09 · VERIFICATION HISTORY</p><h2>Checked, not assumed</h2><div class="timeline">{"".join(f'<div><time>{esc(x["date"])}</time><div><strong>{esc(x["event"])}</strong><p>{esc(x["detail"])}</p></div></div>' for x in m["verification"]["history"])}</div><div class="field-status">{"".join(f'<div><span>{esc(k.replace("_"," "))}</span><strong>{esc(v)}</strong></div>' for k,v in m["verification"]["fields"].items())}</div></section>
</main>{footer}</body></html>'''

def models_page(models):
    rows = []
    for m in models:
        lic = m["license"]
        ctx = m["model"]["context"]["display"] if isinstance(m["model"].get("context"), dict) else m["model"].get("context")
        rows.append(f'''<a class="registry-row" href="/models/{esc(m["id"])}/" data-name="{esc((m["name"]+" "+m["developer"]+" "+str(m.get("family",""))+" "+lic["name"]).lower())}" data-org="{esc(m["developer"].lower())}" data-status="field-verified"><div><div class="row-title">{esc(m["name"])}</div><div class="row-sub">{esc(m["developer"])} · {esc(m["model"].get("modality",""))}</div></div><div>{esc(ctx)}</div><div><span class="pill">{esc(lic["name"])}</span></div><div><span class="pill verified">Field-verified</span></div></a>''')
    orgs = sorted(set(m["developer"] for m in models))
    options = "".join(f'<option value="{esc(x.lower())}">{esc(x)}</option>' for x in orgs)
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{len(models)} field-verified open-weight AI models — Open Model Weights</title><meta name="description" content="Browse {len(models)} field-by-field verified model records covering weights, license, context, formats, lineage, training-data disclosure and runtime support."><link rel="canonical" href="https://openmodelweights.com/models/"><link rel="stylesheet" href="/styles.css"><script src="/app.js?v=2" defer></script></head><body><header class="site-header"><a class="brand" href="/">Open Model Weights</a><nav><a href="/models/">Models</a><a href="/developers/">Developers</a><a href="/explore/">Explore</a><a href="/changes/">Changes</a><a href="/verification/">Verification</a><a href="/methodology/">Methodology</a></nav></header><main><section class="page-hero"><div class="breadcrumbs"><a href="/">Home</a> / Models</div><p class="eyebrow">FIELD-VERIFIED REGISTRY · {len(models)} RECORDS</p><h1>Open-weight AI models</h1><p class="lead">Every listed record has been checked field-by-field against its official Hugging Face repository. Missing metadata is shown as missing, not guessed.</p></section><section class="section registry-section"><div class="filters"><input id="model-search" type="search" placeholder="Search model, lab, family or license…"><select id="org-filter"><option value="">All developers</option>{options}</select><select id="status-filter"><option value="">All verification levels</option><option value="field-verified">Field-verified</option></select></div><p id="registry-result-count" class="registry-result-count" aria-live="polite"></p><div class="registry-list">{"".join(rows)}</div><p id="no-results" class="note" hidden>No matching models.</p></section></main></body></html>'''

def developer_page(dev, items):
    rows = []
    for m in items:
        rows.append(f'<a class="registry-row" href="/models/{esc(m["id"])}/"><div><div class="row-title">{esc(m["name"])}</div><div class="row-sub">{esc(m["model"].get("modality",""))}</div></div><div>{esc(m["model"]["context"]["display"])}</div><div><span class="pill">{esc(m["license"]["name"])}</span></div><div><span class="pill verified">Field-verified</span></div></a>')
    slug = re.sub(r"[^a-z0-9]+","-",dev.lower()).strip("-")
    return slug, f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(dev)} open-weight models — Open Model Weights</title><meta name="description" content="{len(items)} field-verified {esc(dev)} model records."><link rel="canonical" href="https://openmodelweights.com/developers/{slug}/"><link rel="stylesheet" href="/styles.css"></head><body><header class="site-header"><a class="brand" href="/">Open Model Weights</a><nav><a href="/models/">Models</a><a href="/developers/">Developers</a><a href="/explore/">Explore</a><a href="/changes/">Changes</a><a href="/verification/">Verification</a></nav></header><main><section class="page-hero"><div class="breadcrumbs"><a href="/">Home</a> / <a href="/developers/">Developers</a> / {esc(dev)}</div><p class="eyebrow">FIELD-VERIFIED DEVELOPER INDEX</p><h1>{esc(dev)}</h1><p class="lead">{len(items)} checked model records.</p></section><section class="section registry-section"><div class="registry-list">{"".join(rows)}</div></section></main></body></html>'''

def verification_page(report):
    errors = report["errors"]
    err = "".join(f"<li><strong>{esc(x['id'])}</strong>: {esc(x['error'])}</li>" for x in errors) or "<li>None</li>"
    cards = "".join(f'<div><span>{esc(k.replace("_"," "))}</span><strong>{esc(v)}</strong></div>' for k,v in report["stats"].items())
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Verification report — Open Model Weights</title><meta name="description" content="Latest field-by-field verification status for the Open Model Weights registry."><link rel="canonical" href="https://openmodelweights.com/verification/"><link rel="stylesheet" href="/styles.css"></head><body><header class="site-header"><a class="brand" href="/">Open Model Weights</a><nav><a href="/models/">Models</a><a href="/explore/">Explore</a><a href="/changes/">Changes</a><a href="/verification/">Verification</a><a href="/methodology/">Methodology</a></nav></header><main><section class="page-hero"><div class="breadcrumbs"><a href="/">Home</a> / Verification</div><p class="eyebrow">VERIFICATION REPORT · {TODAY}</p><h1>Field evidence, at registry scale.</h1><p class="lead">The verifier checks the official Hugging Face model API, exact repository file list, model-card metadata/text and config.json where accessible.</p></section><section class="section"><div class="verification-stats">{cards}</div></section><section class="section content"><h2>Errors / incomplete fetches</h2><ul>{err}</ul><h2>What “verified” means</h2><p>A field is verified against the named source. “Not disclosed” means the checked standard metadata and obvious model-card sections did not declare the value; it does not prove the information exists nowhere else.</p><h2>Runtime support</h2><p>Runtime entries are source-derived. They are not claims that Open Model Weights executed the model on that runtime.</p></section></main></body></html>'''

def build_report(models, errors):
    stats = {
        "total_seed_records": len(models) + len(errors),
        "field_verified": len(models),
        "errors": len(errors),
        "license_declared": sum(m["license"]["status"] == "verified" for m in models),
        "commercial_use_classified": sum(m["license"]["commercial_use"]["status"] != "unknown" for m in models),
        "context_verified": sum(m["model"]["context"]["status"] == "verified" for m in models),
        "exact_weight_lists": sum(bool(m["weights"]["exact_files"]) for m in models),
        "base_model_declared": sum(m["lineage"]["base_model"]["status"] == "declared" for m in models),
        "training_recipe_signal": sum(m["training_assets"]["training_recipe"]["status"] != "not-disclosed-in-checked-repository" for m in models),
        "data_disclosure_signal": sum(m["training_assets"]["data_disclosure"]["status"] != "not-disclosed-in-standard-metadata-or-obvious-model-card-section" for m in models),
        "runtime_signal": sum(bool(m["runtime_support"]["declared"] or m["runtime_support"]["mentioned_in_model_card"] or m["runtime_support"]["artifact_signals"]) for m in models),
    }
    return {"generated_at": NOW, "stats": stats, "errors": errors}

def main():
    seed_path = SOURCE if SOURCE.exists() else REGISTRY
    seed = json.loads(seed_path.read_text())
    seeds = seed["models"]
    verified, errors = [], []
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as ex:
        futs = {ex.submit(verify_one, m): m for m in seeds}
        for i, fut in enumerate(concurrent.futures.as_completed(futs), 1):
            s = futs[fut]
            try:
                res = fut.result()
                if res.get("ok"):
                    verified.append(res["model"])
                    print(f"[{i}/{len(seeds)}] OK {s['id']}")
                else:
                    errors.append({"id": s["id"], "error": res.get("error","unknown")})
                    print(f"[{i}/{len(seeds)}] FAIL {s['id']}: {res.get('error')}")
            except Exception as e:
                errors.append({"id": s["id"], "error": str(e)})
                print(f"[{i}/{len(seeds)}] ERROR {s['id']}: {e}")
    order = {m["id"]: i for i,m in enumerate(seeds)}
    verified.sort(key=lambda m: order.get(m["id"], 999999))
    verified_before_crop=len(verified)
    if TARGET_MODELS and verified_before_crop < TARGET_MODELS:
        raise RuntimeError(f"Only {verified_before_crop} candidates passed field verification; refusing to publish below target {TARGET_MODELS}.")
    if TARGET_MODELS and len(verified) >= TARGET_MODELS:
        verified=verified[:TARGET_MODELS]

    report = build_report(verified, errors)
    report["candidate_count"]=len(seeds)
    report["successful_candidates"]=verified_before_crop
    report["publication_target"]=TARGET_MODELS
    report["publication_shortfall"]=max(0,TARGET_MODELS-len(verified))
    new_registry = {
        "schema_version": "0.3.0",
        "generated_at": NOW,
        "project": "Open Model Weights",
        "homepage": "https://openmodelweights.com",
        "methodology": "https://openmodelweights.com/methodology/",
        "verification_report": "https://openmodelweights.com/verification/",
        "models": verified,
        "verification_errors": errors,
    }
    REGISTRY.write_text(json.dumps(new_registry, indent=2, ensure_ascii=False) + "\n")
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")

    for m in verified:
        d = PUBLIC / "models" / m["id"]
        d.mkdir(parents=True, exist_ok=True)
        (d / "index.html").write_text(model_page(m))

    (PUBLIC / "models" / "index.html").write_text(models_page(verified))
    groups = {}
    for m in verified:
        groups.setdefault(m["developer"], []).append(m)
    for dev, items in groups.items():
        slug, page = developer_page(dev, items)
        d = PUBLIC / "developers" / slug
        d.mkdir(parents=True, exist_ok=True)
        (d / "index.html").write_text(page)

    vd = PUBLIC / "verification"
    vd.mkdir(parents=True, exist_ok=True)
    (vd / "index.html").write_text(verification_page(report))

    urls = ["/","/models/","/developers/","/verification/","/methodology/","/about/"]
    urls += [f"/models/{m['id']}/" for m in verified]
    urls += [f"/developers/{re.sub(r'[^a-z0-9]+','-',d.lower()).strip('-')}/" for d in groups]
    sitemap = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    sitemap += "\n".join(f"<url><loc>https://openmodelweights.com{u}</loc><lastmod>{TODAY}</lastmod></url>" for u in urls)
    sitemap += "\n</urlset>\n"
    (PUBLIC / "sitemap.xml").write_text(sitemap)

    print(json.dumps(report, indent=2))
    if errors:
        # Do not fail: preserve report and successful verifications, but surface incompleteness.
        print(f"Completed with {len(errors)} incomplete repositories.")

if __name__ == "__main__":
    main()
