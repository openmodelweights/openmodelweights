#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import json
import math
import os
import re
from pathlib import Path

from huggingface_hub import HfApi

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/"data"/"models-source.json"
TARGET=int(os.getenv("OMW_TARGET_MODELS","700"))
BUFFER=int(os.getenv("OMW_DISCOVERY_BUFFER","120"))
POOL=int(os.getenv("OMW_DISCOVERY_POOL","5000"))
NOW=dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()
TODAY=NOW[:10]

WEIGHT_EXTS=(".safetensors",".bin",".pt",".pth",".gguf",".onnx",".nemo",".ckpt",".npz",".h5",".tflite",".mlmodel",".params")

DEV_NAMES={
 "meta-llama":"Meta","google":"Google","mistralai":"Mistral AI","qwen":"Qwen",
 "deepseek-ai":"DeepSeek","nvidia":"NVIDIA","openai":"OpenAI","microsoft":"Microsoft",
 "tiiuae":"Technology Innovation Institute","bigscience":"BigScience","stabilityai":"Stability AI",
 "black-forest-labs":"Black Forest Labs","cohereforai":"Cohere For AI","allenai":"AllenAI",
 "ibm-granite":"IBM","ibm":"IBM","databricks":"Databricks","01-ai":"01.AI",
 "deepcogito":"Deep Cogito","moonshotai":"Moonshot AI","zai-org":"Z.ai","baai":"BAAI",
 "tencent":"Tencent","bytedance":"ByteDance","minimaxai":"MiniMax","hunyuanvideo":"Tencent Hunyuan",
 "facebook":"Meta","sentence-transformers":"Sentence Transformers"
}

EXCLUDE_NAME=re.compile(r"(?:^|[-_. ])(lora|adapter|adapters|qlora|delta|merge|merged|uncensored-merge|gguf|awq|gptq|exl2|mlx|bnb[-_ ]?4bit|4bit|8bit|quant(?:ized|ization)?)(?:$|[-_. ])",re.I)
EXCLUDE_TAGS={"lora","peft","adapter-transformers","textual-inversion"}
GOOD_LIBS={"transformers","diffusers","sentence-transformers","timm","nemo","mlx","setfit","spacy"}

def s(v):
    return "" if v is None else str(v)

def dt_iso(v):
    if not v:
        return None
    if hasattr(v,"isoformat"):
        return v.isoformat()
    return str(v)

def rid(info):
    return getattr(info,"id",None) or getattr(info,"modelId",None)

def files(info):
    out=[]
    for x in getattr(info,"siblings",None) or []:
        name=getattr(x,"rfilename",None) or getattr(x,"path",None)
        if name: out.append(name)
    return out

def has_weight_artifact(info):
    fs=files(info)
    if not fs:
        return True  # full list responses do not always include siblings; verifier is authoritative.
    recognized=[f for f in fs if f.lower().endswith(WEIGHT_EXTS)]
    if not recognized:
        return False
    non_adapter=[f for f in recognized if "adapter_model" not in f.lower()]
    return bool(non_adapter)

def developer(author):
    if not author: return "Independent / community"
    return DEV_NAMES.get(author.lower(),author)

def modality(pipeline):
    p=(pipeline or "").lower()
    mapping={
      "text-generation":"Text","text2text-generation":"Text","conversational":"Text",
      "image-text-to-text":"Image + text → text","visual-question-answering":"Image + text → text",
      "text-to-image":"Text → image","image-to-image":"Image → image","image-classification":"Image",
      "automatic-speech-recognition":"Audio → text","text-to-speech":"Text → audio",
      "audio-text-to-text":"Audio + text → text","feature-extraction":"Embeddings / features",
      "sentence-similarity":"Text embeddings","fill-mask":"Text","token-classification":"Text",
      "object-detection":"Image","image-segmentation":"Image","depth-estimation":"Image",
      "video-text-to-text":"Video + text → text","text-to-video":"Text → video"
    }
    return mapping.get(p,p.replace("-"," ").title() if p else "Not declared")

def family(repo_name):
    x=repo_name
    x=re.sub(r"(?i)[-_.](instruct|chat|base|it|sft|dpo|rlhf|preview|experimental|bf16|fp16|fp8)$","",x)
    x=re.sub(r"(?i)[-_.](?:\d+(?:\.\d+)?)[bBmM](?:[-_.].*)?$","",x)
    return x or repo_name

def slug(repo):
    x=re.sub(r"[^a-z0-9]+","-",repo.lower()).strip("-")
    return x[:120]

def score(info):
    downloads=max(0,int(getattr(info,"downloads",0) or 0))
    likes=max(0,int(getattr(info,"likes",0) or 0))
    lm=getattr(info,"last_modified",None)
    freshness=0.0
    if lm:
        try:
            if not hasattr(lm,"tzinfo"):
                lm=dt.datetime.fromisoformat(str(lm).replace("Z","+00:00"))
            days=max(0,(dt.datetime.now(dt.timezone.utc)-lm).days)
            freshness=max(0,365-days)/365
        except Exception:
            pass
    return math.log10(downloads+1)*10 + math.log10(likes+1)*3 + freshness

def seed_from(info,rank):
    repo=rid(info)
    author=(repo.split("/",1)[0] if repo and "/" in repo else getattr(info,"author",None)) or "community"
    name=(repo.split("/",1)[-1] if repo else "unknown")
    tags=[str(x) for x in (getattr(info,"tags",None) or [])]
    return {
      "id":slug(repo),
      "name":name,
      "developer":developer(author),
      "family":family(name),
      "variant":name,
      "model":{
        "parameters":"Pending verification",
        "total_parameters_billions":None,
        "context":"Pending verification",
        "modality":modality(getattr(info,"pipeline_tag",None)),
        "tags":tags[:20],
      },
      "weights":{
        "status":"pending-verification",
        "repository":f"https://huggingface.co/{repo}",
        "access":"Pending verification",
        "formats":[],
      },
      "license":{"name":"Pending verification","commercial_use":"Pending verification","classification_status":"pending"},
      "hardware":{"status":"pending-verification"},
      "lineage":{"family":family(name),"variant":name,"base_model":{"status":"pending","models":[]}},
      "training_assets":{"recipe":"pending","data":"pending"},
      "sources":[{"type":"model_repository","url":f"https://huggingface.co/{repo}","tier":"primary"}],
      "verification":{"level":"discovered-pending","checked_at":TODAY},
      "discovery":{
        "source":"Hugging Face public model index",
        "repo_id":repo,
        "rank":rank,
        "downloads":getattr(info,"downloads",None),
        "likes":getattr(info,"likes",None),
        "last_modified":dt_iso(getattr(info,"last_modified",None)),
        "created_at":dt_iso(getattr(info,"created_at",None)),
        "library_name":getattr(info,"library_name",None),
        "pipeline_tag":getattr(info,"pipeline_tag",None),
        "discovered_at":NOW,
        "pinned":False,
      }
    }

def main():
    existing=json.loads(SOURCE.read_text()) if SOURCE.exists() else {"models":[]}
    current=existing.get("models",[])
    pinned=[]
    for m in current:
        d=m.get("discovery") or {}
        auto_discovered=(d.get("source")=="Hugging Face public model index" and d.get("pinned") is False)
        if auto_discovered:
            continue
        m.setdefault("discovery",{})
        m["discovery"].setdefault("source","Open Model Weights curated seed")
        m["discovery"]["pinned"]=True
        repo=(m.get("weights",{}).get("repository") or "").split("huggingface.co/",1)[-1].strip("/")
        if repo: m["discovery"].setdefault("repo_id",repo)
        pinned.append(m)

    existing_repos={m.get("discovery",{}).get("repo_id") or (m.get("weights",{}).get("repository") or "").split("huggingface.co/",1)[-1].strip("/") for m in pinned}
    existing_repos={x.lower() for x in existing_repos if x}
    target_candidates=max(TARGET+BUFFER,len(pinned))
    api=HfApi()

    pool=[]
    for info in api.list_models(sort="downloads",full=True,limit=POOL):
        repo=rid(info)
        if not repo or repo.lower() in existing_repos: continue
        if getattr(info,"private",False) or getattr(info,"disabled",False): continue
        name=repo.split("/",1)[-1]
        tags={str(x).lower() for x in (getattr(info,"tags",None) or [])}
        if tags & EXCLUDE_TAGS: continue
        if EXCLUDE_NAME.search(name): continue
        if not has_weight_artifact(info): continue
        lib=(getattr(info,"library_name",None) or "").lower()
        pipeline=(getattr(info,"pipeline_tag",None) or "").lower()
        if not lib and not pipeline and not tags.intersection({"transformers","diffusers","safetensors"}): continue
        pool.append((score(info),info))
    pool.sort(key=lambda x:x[0],reverse=True)

    selected=[]
    counts={}
    used_ids={m.get("id") for m in pinned if m.get("id")}
    # Pass one: diversity cap prevents a single namespace from taking the registry.
    for _,info in pool:
        repo=rid(info); author=repo.split("/",1)[0].lower(); candidate_id=slug(repo)
        cap=55
        if counts.get(author,0)>=cap or candidate_id in used_ids: continue
        selected.append(info); counts[author]=counts.get(author,0)+1; used_ids.add(candidate_id)
        if len(pinned)+len(selected)>=target_candidates: break
    # Pass two: fill remaining buffer if the cap left us short.
    if len(pinned)+len(selected)<target_candidates:
        chosen={rid(x).lower() for x in selected}
        for _,info in pool:
            repo=rid(info); candidate_id=slug(repo)
            if repo.lower() in chosen or candidate_id in used_ids: continue
            selected.append(info); chosen.add(repo.lower()); used_ids.add(candidate_id)
            if len(pinned)+len(selected)>=target_candidates: break

    if len(pinned)+len(selected)<TARGET:
        raise SystemExit(f"Discovery produced only {len(pinned)+len(selected)} candidates; refusing to claim a {TARGET}-model registry.")

    new_models=list(pinned)
    for i,info in enumerate(selected,1):
        new_models.append(seed_from(info,len(pinned)+i))

    payload={
      "schema_version":"0.6.0",
      "generated_at":NOW,
      "target_verified_models":TARGET,
      "candidate_buffer":BUFFER,
      "discovery_policy":{
        "source":"Hugging Face public model index",
        "ranking":"downloads + likes + recency, with namespace diversity cap",
        "exclusions":["private/disabled repos","obvious LoRA/adapter-only repos","obvious quantization/conversion mirrors"],
        "note":"Discovery only creates candidates. Publication requires the field verifier."
      },
      "models":new_models
    }
    SOURCE.write_text(json.dumps(payload,indent=2,ensure_ascii=False)+"\n")
    print(json.dumps({"pinned":len(pinned),"discovered":len(selected),"candidate_total":len(new_models),"target":TARGET},indent=2))

if __name__=="__main__":
    main()
