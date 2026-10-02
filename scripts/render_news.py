#!/usr/bin/env python3
from __future__ import annotations
import datetime as dt
import email.utils
import html
import json
import re
from collections import defaultdict
from pathlib import Path
from xml.sax.saxutils import escape as xml_escape

ROOT=Path(__file__).resolve().parents[1]
PUBLIC=ROOT/"public"
DATA=ROOT/"data"/"news.json"
SITE="https://openmodelweights.com"

def esc(v):
    return html.escape(str(v if v is not None else ""),quote=True)

def slug_date(v):
    return str(v or "")[:10]

def pretty_date(v):
    try:
        d=dt.datetime.fromisoformat(str(v).replace("Z","+00:00"))
        return f"{d.day} {d.strftime('%b %Y')}"
    except Exception:
        return slug_date(v)

def head(title,desc,canonical,extra="",article=None):
    social=f'<meta property="og:site_name" content="Open Model Weights"><meta property="og:type" content="article" if article else "website">'
    social=social.replace('content="article" if article else "website"',f'content="{"article" if article else "website"}"')
    social+=f'<meta property="og:title" content="{esc(title)}"><meta property="og:description" content="{esc(desc)}"><meta property="og:url" content="{esc(canonical)}"><meta name="twitter:card" content="summary"><meta name="twitter:title" content="{esc(title)}"><meta name="twitter:description" content="{esc(desc)}">'
    if article:
        social+=f'<meta property="article:published_time" content="{esc(article["published_at"])}"><meta property="article:modified_time" content="{esc(article["modified_at"])}"><meta property="article:section" content="{esc(article["category"])}">'
    return f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="theme-color" content="#f7f7f4"><title>{esc(title)}</title><meta name="description" content="{esc(desc)}"><link rel="canonical" href="{esc(canonical)}"><meta name="robots" content="index,follow,max-snippet:-1,max-image-preview:large">{social}<link rel="alternate" type="application/rss+xml" title="Open Weight Intelligence" href="/news/feed.xml"><link rel="stylesheet" href="/styles.css">{extra}</head>'

def header(active="news"):
    links=[("models","/models/","Models"),("explore","/explore/","Explore"),("news","/news/","News"),("developers","/developers/","Developers"),("changes","/changes/","Changes"),("sources","/sources/","Sources")]
    out=[]
    for key,url,label in links:
        cur=' aria-current="page"' if active==key else ""
        out.append(f'<a class="nav-link" href="{url}"{cur}>{label}</a>')
    out.append('<a class="nav-link nav-compare" href="/compare/">Compare <span aria-hidden="true">→</span></a>')
    mark='<span class="brand-mark" aria-hidden="true"><i></i><i></i><i></i></span>'
    return '<a class="skip-link" href="#main-content">Skip to content</a><header class="site-header"><a class="brand" href="/" aria-label="Open Model Weights home">'+mark+'<span class="brand-wordmark">Open Model Weights</span></a><nav aria-label="Primary navigation">'+''.join(out)+'</nav></header>'

def footer():
    return '<footer class="site-footer site-footer-v2"><div class="footer-brand"><div class="footer-brand-line"><span class="brand-mark brand-mark-small" aria-hidden="true"><i></i><i></i><i></i></span><strong>Open Model Weights</strong></div><p>Field-verified intelligence for open-weight AI.</p></div><div class="footer-nav"><div class="footer-group"><span>Registry</span><a href="/models/">Models</a><a href="/news/">News</a><a href="/compare/">Compare</a><a href="/changes/">Changes</a></div><div class="footer-group"><span>Evidence</span><a href="/sources/">Sources</a><a href="/verification/">Verification</a><a href="/methodology/">Methodology</a><a href="/history/">History</a></div><div class="footer-group"><span>Machine</span><a href="/api/">API / JSON</a><a href="/mcp/">MCP</a><a href="/registry.json">Registry JSON</a><a href="/benchmarks/">Benchmarks</a></div><div class="footer-group"><span>Project</span><a href="https://github.com/openmodelweights/openmodelweights" rel="noopener">GitHub ↗</a><a href="https://huggingface.co/openmodelweights" rel="noopener">Hugging Face ↗</a></div></div></footer>'

def graph_script(nodes):
    raw=json.dumps({"@context":"https://schema.org","@graph":nodes},ensure_ascii=False,separators=(",",":")).replace("</","<\\/")
    return f'<script type="application/ld+json">{raw}</script>'

def org_node():
    return {"@type":"Organization","@id":SITE+"/#organization","name":"Open Model Weights","url":SITE+"/"}

def breadcrumb(items,canonical):
    return {"@type":"BreadcrumbList","@id":canonical+"#breadcrumb","itemListElement":[{"@type":"ListItem","position":i+1,"name":n,"item":u} for i,(n,u) in enumerate(items)]}

def article_schema(a):
    canonical=SITE+"/news/"+a["slug"]+"/"
    bc=breadcrumb([("Home",SITE+"/"),("News",SITE+"/news/"),(a["title"],canonical)],canonical)
    article={"@type":"NewsArticle","@id":canonical+"#article","headline":a["title"],"description":a["dek"],"url":canonical,"mainEntityOfPage":{"@id":canonical+"#webpage"},"datePublished":a["published_at"],"dateModified":a["modified_at"],"articleSection":a["category"],"keywords":a.get("tags",[]),"author":{"@id":SITE+"/#organization"},"publisher":{"@id":SITE+"/#organization"},"isBasedOn":a["source_url"],"citation":[a["source_url"]],"inLanguage":"en"}
    page={"@type":"WebPage","@id":canonical+"#webpage","url":canonical,"name":a["title"],"description":a["dek"],"isPartOf":{"@id":SITE+"/#website"},"breadcrumb":{"@id":bc["@id"]},"primaryImageOfPage":None}
    page.pop("primaryImageOfPage",None)
    website={"@type":"WebSite","@id":SITE+"/#website","url":SITE+"/","name":"Open Model Weights","publisher":{"@id":SITE+"/#organization"}}
    return [org_node(),website,page,bc,article]

def card(a,featured=False):
    cls="news-card news-card-featured" if featured else "news-card"
    return f'<article class="{cls}"><div class="news-card-meta"><span>{esc(a["category"])}</span><time datetime="{esc(a["published_at"])}">{esc(pretty_date(a["published_at"]))}</time></div><h2><a href="/news/{esc(a["slug"])}/">{esc(a["title"])}</a></h2><p>{esc(a["dek"])}</p><div class="news-card-source"><span>Primary source</span><strong>{esc(a["source_name"])}</strong><small>Source published {esc(pretty_date(a["source_published"]))}</small></div><a class="news-read-link" href="/news/{esc(a["slug"])}/">Read evidence brief →</a></article>'

def render_index(articles):
    latest=articles[0] if articles else None
    edition=articles[0]["edition_date"] if articles else dt.date.today().isoformat()
    canonical=SITE+"/news/"
    desc="Daily source-first intelligence on open-weight AI models, releases, licenses, runtimes, training systems and ecosystem changes."
    items=[{"@type":"ListItem","position":i+1,"url":SITE+"/news/"+a["slug"]+"/","name":a["title"]} for i,a in enumerate(articles[:30])]
    bc=breadcrumb([("Home",SITE+"/"),("News",canonical)],canonical)
    graph=[org_node(),{"@type":"CollectionPage","@id":canonical+"#webpage","url":canonical,"name":"Open Weight Intelligence","description":desc,"breadcrumb":{"@id":bc["@id"]},"mainEntity":{"@id":canonical+"#list"}},bc,{"@type":"ItemList","@id":canonical+"#list","itemListElement":items}]
    featured=card(latest,True) if latest else '<p class="note">No published intelligence yet.</p>'
    rest="".join(card(a) for a in articles[1:10])
    return f'{head("Open Weight Intelligence — daily open-weight AI news | Open Model Weights",desc,canonical,graph_script(graph))}<body class="news-page">{header()}<main id="main-content"><section class="page-hero news-hero"><div class="breadcrumbs"><a href="/">Home</a> / News</div><p class="eyebrow">OPEN MODEL WEIGHTS · DAILY INTELLIGENCE</p><h1>What changed in open-weight AI.</h1><p class="lead">Source-first briefs on model releases, weights, licenses, runtimes, training infrastructure and ecosystem shifts — tied back to the evidence standards of the registry.</p><div class="page-hero-chips"><span>Up to 10 daily</span><span>Primary sources first</span><span>200–500 word briefs</span><span>No quality ranking</span></div></section><section class="section news-edition"><div class="news-edition-head"><div><p class="eyebrow">LATEST EDITION · {esc(edition)}</p><h2>Open Weight Intelligence</h2></div><div class="news-edition-actions"><a href="/news/{esc(edition)}/">Open daily digest →</a><a href="/news/feed.xml">RSS feed →</a></div></div><div class="news-featured">{featured}</div><div class="news-grid">{rest}</div></section><section class="section news-standard"><div><p class="eyebrow">EDITORIAL STANDARD</p><h2>News should add evidence, not noise.</h2></div><div class="news-standard-grid"><div><strong>Primary-source bias</strong><p>Publisher blogs, model cards, release notes and repositories are preferred over second-hand coverage.</p></div><div><strong>Claims stay attributed</strong><p>Benchmark, speed and performance claims remain publisher claims unless Open Model Weights independently measures them.</p></div><div><strong>No quota pressure</strong><p>The system can publish up to ten briefs per day, but fewer are published when there are fewer meaningful developments.</p></div><div><strong>Registry context</strong><p>Each brief distinguishes a model-record candidate from runtime, compatibility, infrastructure or ecosystem news.</p></div></div><p class="news-disclosure">Open Weight Intelligence is produced with automated research assistance and source-first editorial rules. Every brief links to its primary source, and unsupported details should remain absent rather than inferred.</p></section></main>{footer()}</body></html>'

def render_article(a,related):
    canonical=SITE+"/news/"+a["slug"]+"/"
    body="".join(f"<p>{esc(p)}</p>" for p in a.get("body",[]))
    points="".join(f"<li>{esc(x)}</li>" for x in a.get("key_points",[]))
    related_html="".join(card(x) for x in related[:3])
    schema=graph_script(article_schema(a))
    return f'{head(a["title"]+" | Open Weight Intelligence",a["dek"],canonical,schema,article=a)}<body class="news-article-page">{header()}<main id="main-content"><article class="news-article"><header class="news-article-hero"><div class="breadcrumbs"><a href="/">Home</a> / <a href="/news/">News</a> / {esc(a["title"])}</div><div class="news-article-kicker"><span>{esc(a["category"])}</span><time datetime="{esc(a["published_at"])}">{esc(pretty_date(a["published_at"]))}</time></div><h1>{esc(a["title"])}</h1><p class="lead">{esc(a["dek"])}</p><div class="news-article-sourcebar"><div><small>Open Model Weights published</small><strong>{esc(pretty_date(a["published_at"]))}</strong></div><div><small>Primary source</small><strong>{esc(a["source_name"])}</strong></div><div><small>Source published</small><strong>{esc(pretty_date(a["source_published"]))}</strong></div></div></header><div class="news-article-layout"><div class="news-article-body">{body}<section class="news-registry-watch"><span>OMW REGISTRY WATCH</span><h2>What this changes for the evidence layer</h2><p>{esc(a["registry_watch"])}</p></section><section class="news-source-box"><span>PRIMARY SOURCE</span><h2>{esc(a["source_name"])}</h2><p>This brief is based on the cited primary source. Performance, benchmark and comparative claims remain attributed unless Open Model Weights publishes an independent measurement.</p><a href="{esc(a["source_url"])}" rel="noopener">Open source article ↗</a></section></div><aside class="news-keyfacts"><span>KEY FACTS</span><ul>{points}</ul><div class="news-tags">{"".join(f"<b>{esc(t)}</b>" for t in a.get("tags",[]))}</div></aside></div></article><section class="section news-related"><div class="section-head"><div><p class="eyebrow">RELATED INTELLIGENCE</p><h2>More from the evidence feed.</h2></div><a class="text-link" href="/news/">All news →</a></div><div class="news-grid">{related_html}</div></section></main>{footer()}</body></html>'

def render_digest(day,articles):
    canonical=SITE+f"/news/{day}/"
    desc=f"Open Weight Intelligence daily digest for {day}: source-first developments across open-weight models, runtimes, licenses and infrastructure."
    bc=breadcrumb([("Home",SITE+"/"),("News",SITE+"/news/"),(day,canonical)],canonical)
    graph=[org_node(),{"@type":"CollectionPage","@id":canonical+"#webpage","url":canonical,"name":f"Open Weight Intelligence — {day}","description":desc,"breadcrumb":{"@id":bc["@id"]}},bc,{"@type":"ItemList","itemListElement":[{"@type":"ListItem","position":i+1,"url":SITE+"/news/"+a["slug"]+"/","name":a["title"]} for i,a in enumerate(articles)]}]
    cards="".join(card(a,i==0) for i,a in enumerate(articles))
    return f'{head("Open Weight Intelligence — "+day+" | Open Model Weights",desc,canonical,graph_script(graph))}<body class="news-page news-digest-page">{header()}<main id="main-content"><section class="page-hero news-hero"><div class="breadcrumbs"><a href="/">Home</a> / <a href="/news/">News</a> / {esc(day)}</div><p class="eyebrow">DAILY DIGEST · {esc(day)}</p><h1>{len(articles)} developments worth tracking.</h1><p class="lead">A source-first daily record of meaningful changes across the open-weight ecosystem. Fewer than ten are published when the evidence does not justify ten.</p></section><section class="section news-edition"><div class="news-grid news-digest-grid">{cards}</div></section></main>{footer()}</body></html>'

def patch_sitemap(articles):
    p=PUBLIC/"sitemap.xml"
    if not p.exists(): return
    text=p.read_text()
    urls=[("/news/",articles[0]["edition_date"] if articles else dt.date.today().isoformat())]
    for a in articles:
        urls.append((f'/news/{a["slug"]}/',slug_date(a["modified_at"])))
    for day in sorted({a["edition_date"] for a in articles}):
        urls.append((f"/news/{day}/",day))
    for path,lastmod in urls:
        full=SITE+path
        if full not in text:
            text=text.replace("</urlset>",f'<url><loc>{full}</loc><lastmod>{lastmod}</lastmod></url>\n</urlset>')
    p.write_text(text)

def write_news_sitemap(articles):
    if not articles: return
    newest=max(a["edition_date"] for a in articles)
    cutoff=dt.date.fromisoformat(newest)-dt.timedelta(days=1)
    recent=[a for a in articles if dt.date.fromisoformat(a["edition_date"])>=cutoff]
    rows=[]
    for a in recent[:1000]:
        url=SITE+"/news/"+a["slug"]+"/"
        rows.append(f'<url><loc>{xml_escape(url)}</loc><news:news><news:publication><news:name>Open Model Weights</news:name><news:language>en</news:language></news:publication><news:publication_date>{xml_escape(a["published_at"])}</news:publication_date><news:title>{xml_escape(a["title"])}</news:title></news:news></url>')
    xml='<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:news="http://www.google.com/schemas/sitemap-news/0.9">\n'+"\n".join(rows)+"\n</urlset>\n"
    (PUBLIC/"news-sitemap.xml").write_text(xml)

def write_rss(articles):
    items=[]
    for a in articles[:30]:
        url=SITE+"/news/"+a["slug"]+"/"
        try:
            dtv=dt.datetime.fromisoformat(a["published_at"].replace("Z","+00:00"))
            pub=email.utils.format_datetime(dtv)
        except Exception:
            pub=a["published_at"]
        items.append(f'<item><title>{xml_escape(a["title"])}</title><link>{xml_escape(url)}</link><guid isPermaLink="true">{xml_escape(url)}</guid><pubDate>{xml_escape(pub)}</pubDate><category>{xml_escape(a["category"])}</category><description>{xml_escape(a["dek"])}</description><source url="{xml_escape(a["source_url"])}">{xml_escape(a["source_name"])}</source></item>')
    rss='<?xml version="1.0" encoding="UTF-8"?>\n<rss version="2.0"><channel><title>Open Weight Intelligence</title><link>'+SITE+'/news/</link><description>Daily source-first intelligence on open-weight AI.</description><language>en</language>'+"".join(items)+'</channel></rss>\n'
    (PUBLIC/"news"/"feed.xml").write_text(rss)

def patch_llms(articles):
    p=PUBLIC/"llms.txt"
    text=p.read_text() if p.exists() else "# Open Model Weights\n"
    block="\n## Open Weight Intelligence\n- https://openmodelweights.com/news/ — daily source-first open-weight AI intelligence\n- https://openmodelweights.com/news/feed.xml — RSS feed\n- https://openmodelweights.com/api/v1/news.json — machine-readable news index\n"
    if "## Open Weight Intelligence" not in text:
        text+=block
    p.write_text(text)

def patch_home(articles):
    if not articles: return
    p=PUBLIC/"index.html"
    if not p.exists(): return
    text=p.read_text()
    text=re.sub(r'<section class="section home-news-section">.*?</section>','',text,flags=re.S)
    latest=articles[:3]
    cards="".join(f'<a class="home-news-card" href="/news/{esc(a["slug"])}/"><span>{esc(a["category"])} · {esc(pretty_date(a["published_at"]))}</span><strong>{esc(a["title"])}</strong><p>{esc(a["dek"])}</p><b>Read brief →</b></a>' for a in latest)
    section=f'<section class="section home-news-section"><div class="section-head"><div><p class="eyebrow">OPEN WEIGHT INTELLIGENCE</p><h2>What changed today.</h2></div><p class="section-kicker">Daily source-first developments tied back to the evidence layer. <a href="/news/">Open all news →</a></p></div><div class="home-news-grid">{cards}</div></section>'
    m=re.search(r'<section class="[^"]*home-source-section',text)
    if m:
        text=text[:m.start()]+section+text[m.start():]
    else:
        text=text.replace("</main>",section+"</main>",1)
    p.write_text(text)

def main():
    payload=json.loads(DATA.read_text()) if DATA.exists() else {"articles":[]}
    articles=sorted(payload.get("articles",[]),key=lambda a:a.get("published_at",""),reverse=True)
    news_dir=PUBLIC/"news";news_dir.mkdir(parents=True,exist_ok=True)
    (news_dir/"index.html").write_text(render_index(articles))
    by_day=defaultdict(list)
    for a in articles:
        d=news_dir/a["slug"];d.mkdir(parents=True,exist_ok=True)
        related=[x for x in articles if x["slug"]!=a["slug"] and (x["category"]==a["category"] or set(x.get("tags",[])) & set(a.get("tags",[])))]
        if len(related)<3:
            related += [x for x in articles if x["slug"]!=a["slug"] and x not in related]
        (d/"index.html").write_text(render_article(a,related))
        by_day[a["edition_date"]].append(a)
    for day,items in by_day.items():
        d=news_dir/day;d.mkdir(parents=True,exist_ok=True)
        (d/"index.html").write_text(render_digest(day,items))
    write_rss(articles)
    write_news_sitemap(articles)
    patch_sitemap(articles)
    patch_llms(articles)
    patch_home(articles)
    api=PUBLIC/"api"/"v1";api.mkdir(parents=True,exist_ok=True)
    compact=[{k:a.get(k) for k in ("slug","title","dek","published_at","modified_at","edition_date","source_published","category","importance","source_name","source_url","tags","registry_watch")} for a in articles]
    (api/"news.json").write_text(json.dumps({"generated_at":dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),"article_count":len(compact),"articles":compact},indent=2,ensure_ascii=False)+"\n")
    print(json.dumps({"news_articles":len(articles),"editions":len(by_day)},indent=2))

if __name__=="__main__":
    main()
