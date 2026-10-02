#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import statistics
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import requests
from huggingface_hub import HfApi
from transformers import AutoTokenizer

DEFAULT_PROMPT = """You are benchmarking deterministic text generation. In concise technical prose, explain why exact model revision, runtime version, hardware identity, and raw measurement evidence are required for reproducible AI deployment benchmarks. Do not use bullet points."""
WARMUPS = 2
MEASURED = 5
MAX_NEW_TOKENS = 128

def sh(cmd):
    return subprocess.check_output(cmd, text=True, stderr=subprocess.STDOUT).strip()

def gpu_inventory():
    if not shutil.which("nvidia-smi"):
        raise SystemExit("nvidia-smi not found. This runner requires a real NVIDIA GPU host.")
    raw=sh(["nvidia-smi","--query-gpu=index,name,memory.total,driver_version","--format=csv,noheader,nounits"])
    rows=[]
    for line in raw.splitlines():
        idx,name,mem,driver=[x.strip() for x in line.split(",",3)]
        rows.append({"index":int(idx),"name":name,"memory_total_mib":float(mem),"driver_version":driver})
    if not rows:
        raise SystemExit("No NVIDIA GPUs detected.")
    return rows

def sample_gpu_memory(stop, samples):
    while not stop.is_set():
        try:
            raw=sh(["nvidia-smi","--query-gpu=memory.used","--format=csv,noheader,nounits"])
            vals=[float(x.strip()) for x in raw.splitlines() if x.strip()]
            if vals:samples.append({"at":time.time(),"used_mib":vals,"sum_mib":sum(vals)})
        except Exception:
            pass
        stop.wait(0.08)

def resolve_model(model_id, repository=None):
    if repository:
        repo=repository.replace("https://huggingface.co/","").strip("/")
        return {"id":model_id,"weights":{"repository":"https://huggingface.co/"+repo}}
    url=f"https://openmodelweights.com/api/v1/models/{model_id}.json"
    r=requests.get(url,timeout=30)
    r.raise_for_status()
    return r.json()

def wait_server(base_url, proc, timeout=1200):
    deadline=time.time()+timeout
    while time.time()<deadline:
        if proc.poll() is not None:
            raise RuntimeError(f"vLLM server exited with code {proc.returncode}")
        try:
            r=requests.get(base_url+"/v1/models",timeout=3)
            if r.ok:return
        except Exception:
            pass
        time.sleep(2)
    raise TimeoutError("vLLM server did not become ready within timeout")

def stream_once(base_url, served_name, tokenizer, prompt):
    payload={
      "model":served_name,
      "messages":[{"role":"user","content":prompt}],
      "temperature":0,
      "max_tokens":MAX_NEW_TOKENS,
      "stream":True,
      "seed":42,
    }
    started=time.perf_counter()
    first=None
    pieces=[]
    with requests.post(base_url+"/v1/chat/completions",json=payload,stream=True,timeout=600) as r:
        r.raise_for_status()
        for line in r.iter_lines(decode_unicode=True):
            if not line or not line.startswith("data:"):continue
            data=line[5:].strip()
            if data=="[DONE]":break
            try:obj=json.loads(data)
            except Exception:continue
            delta=((obj.get("choices") or [{}])[0].get("delta") or {}).get("content")
            if delta:
                if first is None:first=time.perf_counter()
                pieces.append(delta)
    ended=time.perf_counter()
    text="".join(pieces)
    if first is None:
        raise RuntimeError("No generated token/content received from vLLM.")
    input_tokens=len(tokenizer.encode(prompt,add_special_tokens=False))
    output_tokens=len(tokenizer.encode(text,add_special_tokens=False))
    ttft_ms=(first-started)*1000
    generation_s=max(ended-first,1e-6)
    return {
      "input_tokens":input_tokens,
      "output_tokens":output_tokens,
      "time_to_first_token_ms":ttft_ms,
      "output_tokens_per_second":output_tokens/generation_s,
      "total_seconds":ended-started,
      "generated_text_sha256":__import__("hashlib").sha256(text.encode()).hexdigest(),
    }

def main():
    ap=argparse.ArgumentParser(description="Open Model Weights reproducible vLLM deployment benchmark")
    ap.add_argument("--model-id",required=True,help="Open Model Weights model id")
    ap.add_argument("--repository",help="Optional Hugging Face repo override (owner/name)")
    ap.add_argument("--dtype",default="auto")
    ap.add_argument("--tensor-parallel-size",type=int,default=1)
    ap.add_argument("--gpu-memory-utilization",type=float,default=0.90)
    ap.add_argument("--port",type=int,default=18080)
    ap.add_argument("--output-dir",default="benchmark-output")
    ap.add_argument("--write-repo",action="store_true",help="Also append accepted-shape result/evidence to data/ in this checkout")
    args=ap.parse_args()

    gpus=gpu_inventory()
    if args.tensor_parallel_size>len(gpus):
        raise SystemExit("tensor-parallel-size exceeds detected GPU count.")

    model=resolve_model(args.model_id,args.repository)
    repo=(model.get("weights") or {}).get("repository","").replace("https://huggingface.co/","").strip("/")
    if not repo:raise SystemExit("Could not resolve Hugging Face source repository.")
    info=HfApi().model_info(repo)
    revision=info.sha
    served="omw-benchmark"
    base=f"http://127.0.0.1:{args.port}"

    try:
        import vllm
        vllm_version=vllm.__version__
    except Exception as e:
        raise SystemExit("vLLM is not installed in this environment. Install vllm first.") from e

    tokenizer=AutoTokenizer.from_pretrained(repo,revision=revision,trust_remote_code=True)
    result_id=f"omw-{args.model_id}-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"
    out=Path(args.output_dir)/result_id
    out.mkdir(parents=True,exist_ok=True)
    log_path=out/"vllm-server.log"

    command=[
      sys.executable,"-m","vllm.entrypoints.openai.api_server",
      "--model",repo,"--revision",revision,"--served-model-name",served,
      "--port",str(args.port),"--dtype",args.dtype,
      "--tensor-parallel-size",str(args.tensor_parallel_size),
      "--gpu-memory-utilization",str(args.gpu_memory_utilization),
    ]

    with log_path.open("w") as log:
        proc=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT,text=True)
    samples=[]
    stop=threading.Event()
    sampler=threading.Thread(target=sample_gpu_memory,args=(stop,samples),daemon=True)
    try:
        wait_server(base,proc)
        sampler.start()
        warmups=[]
        for _ in range(WARMUPS):
            warmups.append(stream_once(base,served,tokenizer,DEFAULT_PROMPT))
        runs=[]
        for _ in range(MEASURED):
            runs.append(stream_once(base,served,tokenizer,DEFAULT_PROMPT))
    finally:
        stop.set()
        if sampler.is_alive():sampler.join(timeout=2)
        proc.terminate()
        try:proc.wait(timeout=20)
        except subprocess.TimeoutExpired:
            proc.kill();proc.wait(timeout=5)

    peak_mib=max((x["sum_mib"] for x in samples),default=0)
    ttft=statistics.median(x["time_to_first_token_ms"] for x in runs)
    tps=statistics.median(x["output_tokens_per_second"] for x in runs)

    try:cuda_version=sh(["nvidia-smi"]).split("CUDA Version:")[1].split()[0]
    except Exception:cuda_version=None
    try:torch_version=__import__("torch").__version__
    except Exception:torch_version=None

    now=datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    public_evidence=f"https://openmodelweights.com/benchmark-evidence/{result_id}.json"
    result={
      "result_id":result_id,
      "model_id":args.model_id,
      "source_repository_sha":revision,
      "date_utc":now,
      "runtime":{"name":"vLLM","version":vllm_version,"command_or_config":" ".join(command)},
      "hardware":{
        "vendor":"NVIDIA","model":gpus[0]["name"],"device_count":args.tensor_parallel_size,
        "device_memory_gb":round(gpus[0]["memory_total_mib"]/1024,3)
      },
      "artifact":{"precision_or_quantization":args.dtype,"weight_file_or_variant":repo},
      "metrics":{
        "time_to_first_token_ms":round(ttft,3),
        "output_tokens_per_second":round(tps,3),
        "peak_device_memory_gb":round(peak_mib/1024,3)
      },
      "measured_runs":MEASURED,
      "evidence_url":public_evidence
    }
    evidence={
      "evidence_version":"1.0.0",
      "result":result,
      "protocol":{"warmup_runs":WARMUPS,"measured_runs":MEASURED,"max_new_tokens":MAX_NEW_TOKENS,"temperature":0,"seed":42,"aggregation":"median"},
      "model":{"omw_model_id":args.model_id,"repository":repo,"repository_sha":revision},
      "prompt":{"text":DEFAULT_PROMPT,"input_tokens":runs[0]["input_tokens"] if runs else None},
      "environment":{
        "hostname":platform.node(),"platform":platform.platform(),"python":platform.python_version(),
        "vllm":vllm_version,"torch":torch_version,"driver":gpus[0]["driver_version"],"cuda_reported":cuda_version,
        "gpus":gpus
      },
      "warmup_runs":warmups,
      "measured_runs":runs,
      "gpu_memory_samples":samples,
      "server_log_file":"vllm-server.log"
    }

    (out/"result.json").write_text(json.dumps(result,indent=2)+"\n")
    (out/"evidence.json").write_text(json.dumps(evidence,indent=2)+"\n")

    if args.write_repo:
        root=Path(__file__).resolve().parents[2]
        ev=root/"data"/"benchmark-evidence";ev.mkdir(parents=True,exist_ok=True)
        (ev/f"{result_id}.json").write_text(json.dumps(evidence,indent=2)+"\n")
        rp=root/"data"/"benchmark-results.json"
        payload=json.loads(rp.read_text()) if rp.exists() else {"schema_version":"1.0.0","protocol_version":"1.0.0","results":[]}
        if not any(x.get("result_id")==result_id for x in payload.get("results",[])):
            payload.setdefault("results",[]).append(result)
        rp.write_text(json.dumps(payload,indent=2)+"\n")

    print(json.dumps({"result_id":result_id,"result":result,"output_dir":str(out),"written_to_repo":args.write_repo},indent=2))

if __name__=="__main__":
    main()
