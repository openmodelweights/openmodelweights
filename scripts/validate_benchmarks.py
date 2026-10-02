#!/usr/bin/env python3
from __future__ import annotations
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
RESULTS=ROOT/"data"/"benchmark-results.json"
REGISTRY=ROOT/"public"/"registry.json"
EVIDENCE=ROOT/"data"/"benchmark-evidence"
LEDGERS=ROOT/"data"/"evidence-ledger"

def fail(msg):
    raise SystemExit("Benchmark validation failed: "+msg)

def main():
    if not RESULTS.exists():
        print("No benchmark result file yet; nothing to validate.")
        return
    payload=json.loads(RESULTS.read_text())
    results=payload.get("results")
    if not isinstance(results,list):fail("results must be an array")
    models={m["id"]:m for m in json.loads(REGISTRY.read_text()).get("models",[])}
    seen=set()
    for i,r in enumerate(results):
        rid=r.get("result_id")
        if not rid or rid in seen:fail(f"result {i}: missing/duplicate result_id")
        seen.add(rid)
        if r.get("model_id") not in models:fail(f"{rid}: unknown current model_id {r.get('model_id')}")
        sha=str(r.get("source_repository_sha") or "")
        if len(sha)<7:fail(f"{rid}: source_repository_sha required")
        model_id=r.get("model_id")
        accepted_shas={str(((models[model_id].get("hub") or {}).get("sha") or ""))}
        lp=LEDGERS/f"{model_id}.json"
        if lp.exists():
            try:
                ledger=json.loads(lp.read_text())
                accepted_shas.update(str(x.get("repository_sha") or "") for x in ledger.get("snapshots",[]))
            except Exception:pass
        if sha not in accepted_shas:fail(f"{rid}: source_repository_sha is not present in the observed evidence ledger")
        ev=EVIDENCE/f"{rid}.json"
        if not ev.exists():fail(f"{rid}: matching raw evidence file is required")
        try:evidence=json.loads(ev.read_text())
        except Exception:fail(f"{rid}: raw evidence is not valid JSON")
        if (evidence.get("result") or {}).get("result_id")!=rid:fail(f"{rid}: raw evidence/result id mismatch")
        if (evidence.get("result") or {}).get("source_repository_sha")!=sha:fail(f"{rid}: raw evidence/source SHA mismatch")
        if int(r.get("measured_runs") or 0)<3:fail(f"{rid}: at least 3 measured runs required")
        if not str(r.get("evidence_url") or "").startswith("https://"):fail(f"{rid}: public https evidence_url required")
        rt=r.get("runtime") or {}
        if not rt.get("name") or not rt.get("version"):fail(f"{rid}: runtime name/version required")
        hw=r.get("hardware") or {}
        if not hw.get("vendor") or not hw.get("model") or float(hw.get("device_memory_gb") or 0)<=0:fail(f"{rid}: complete hardware identity required")
        metrics=r.get("metrics") or {}
        for key in ("time_to_first_token_ms","output_tokens_per_second","peak_device_memory_gb"):
            try:v=float(metrics.get(key))
            except Exception:fail(f"{rid}: numeric {key} required")
            if v<=0:fail(f"{rid}: {key} must be > 0")
    print(json.dumps({"validated_benchmark_results":len(results)},indent=2))

if __name__=="__main__":
    main()
