#!/usr/bin/env python3
"""Submit meaningful OpenModelWeights URL changes to IndexNow."""
from __future__ import annotations
import argparse
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
PUBLIC=ROOT/"public"
HOST="openmodelweights.com"
BASE="https://openmodelweights.com"
KEY="a909ed84941b4827bebc84e058f4c672"
KEY_LOCATION=f"{BASE}/{KEY}.txt"
ENDPOINT="https://api.indexnow.org/indexnow"
ACCEPTED={200,202}
MAX_BATCH=1000

def public_path_to_url(path: str):
    if not path.startswith("public/") or not path.endswith(".html"):
        return None
    rel=path[len("public/"):]
    if rel=="index.html":
        return BASE+"/"
    if rel.endswith("/index.html"):
        return BASE+"/"+rel[:-len("index.html")]
    return BASE+"/"+rel

def changed_urls(before: str, after: str):
    cmd=["git","diff","--name-status",before,after,"--","public"]
    p=subprocess.run(cmd,capture_output=True,text=True,check=True)
    urls=[]
    for line in p.stdout.splitlines():
        parts=line.split("\t")
        if not parts:
            continue
        status=parts[0]
        paths=parts[1:]
        # For renames, notify both the old and new URL so removals/redirects are recrawled.
        for path in paths:
            u=public_path_to_url(path)
            if u:
                urls.append(u)
    return sorted(set(urls))

def news_urls():
    p=PUBLIC/"news-sitemap.xml"
    urls=[]
    if p.exists():
        root=ET.parse(p).getroot()
        ns={"sm":"http://www.sitemaps.org/schemas/sitemap/0.9"}
        urls=[x.text.strip() for x in root.findall("sm:url/sm:loc",ns) if x.text]
    return urls

def bootstrap_urls():
    hubs=[
        BASE+"/",
        BASE+"/models/",
        BASE+"/news/",
        BASE+"/changes/",
        BASE+"/developers/",
        BASE+"/explore/",
        BASE+"/compare/",
        BASE+"/verification/",
        BASE+"/sources/",
    ]
    # Keep bootstrap deliberately small: hubs plus current Google News-sitemap URLs.
    return sorted(set(hubs+news_urls()))

def verify_key(attempts=12, delay=10):
    last=""
    for i in range(attempts):
        try:
            req=urllib.request.Request(KEY_LOCATION,headers={"User-Agent":"OpenModelWeights-IndexNow/1.0"})
            with urllib.request.urlopen(req,timeout=20) as r:
                body=r.read().decode("utf-8","replace").strip()
                if r.status==200 and body==KEY:
                    print(f"IndexNow key verified live at {KEY_LOCATION}")
                    return
                last=f"HTTP {r.status}, body={body!r}"
        except Exception as e:
            last=str(e)
        if i+1<attempts:
            time.sleep(delay)
    raise RuntimeError(f"IndexNow key not live after retries: {last}")

def submit(urls):
    urls=sorted(set(u for u in urls if u.startswith(BASE+"/")))
    if not urls:
        print("No changed indexable HTML URLs to submit.")
        return
    if len(urls)>10000:
        raise RuntimeError(f"Refusing to submit {len(urls)} URLs; protocol maximum is 10,000 per request set.")
    print(f"Submitting {len(urls)} URL(s) to IndexNow.")
    for start in range(0,len(urls),MAX_BATCH):
        batch=urls[start:start+MAX_BATCH]
        payload={
            "host":HOST,
            "key":KEY,
            "keyLocation":KEY_LOCATION,
            "urlList":batch,
        }
        data=json.dumps(payload,separators=(",",":")).encode("utf-8")
        req=urllib.request.Request(
            ENDPOINT,
            data=data,
            method="POST",
            headers={
                "Content-Type":"application/json; charset=utf-8",
                "User-Agent":"OpenModelWeights-IndexNow/1.0",
            },
        )
        try:
            with urllib.request.urlopen(req,timeout=30) as r:
                code=r.status
                body=r.read().decode("utf-8","replace")
        except urllib.error.HTTPError as e:
            code=e.code
            body=e.read().decode("utf-8","replace")
        print(f"IndexNow batch {start//MAX_BATCH+1}: HTTP {code} ({len(batch)} URLs)")
        if body.strip():
            print(body[:1000])
        if code not in ACCEPTED:
            raise RuntimeError(f"IndexNow submission failed with HTTP {code}")

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--before")
    ap.add_argument("--after")
    ap.add_argument("--bootstrap",action="store_true")
    args=ap.parse_args()
    verify_key()
    if args.bootstrap:
        urls=bootstrap_urls()
    elif args.before and args.after:
        urls=changed_urls(args.before,args.after)
    else:
        ap.error("use --bootstrap or both --before and --after")
    submit(urls)

if __name__=="__main__":
    main()
