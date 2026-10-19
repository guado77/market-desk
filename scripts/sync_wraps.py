#!/usr/bin/env python3
"""Market Desk - sincronizzazione degli output dei wrap.

Copia SOLO gli ultimi file di output (png / pdf / xlsx) dai repo privati dei wrap
in assets/<sezione>/ e rigenera manifest.json. Non copia mai codice, stato,
configurazioni, log o testo delle chat.

Token: legge WRAPS_READ_TOKEN (o GH_TOKEN). Se manca esce con codice 0 e un
messaggio chiaro, senza toccare nulla. Il token non viene mai scritto su disco.
"""
import datetime as dt
import hashlib, io, json, os, re, sys, time, unicodedata, urllib.error, urllib.parse, urllib.request, zipfile
from zoneinfo import ZoneInfo

OWNER = os.environ.get("WRAPS_OWNER", "guado77")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(ROOT, "assets")
MANIFEST = os.path.join(ROOT, "manifest.json")
ROME = ZoneInfo("Europe/Rome")
ALLOWED = (".png", ".pdf", ".xlsx")
MAX_BYTES = 25 * 1024 * 1024        # file piu' grandi: non copiati (resta il link alla fonte se c'e')

# ---------------------------------------------------------------------------
# Sezioni. kind: "wrap" = output prodotti dai wrap; "papers" = PDF di fonti
# istituzionali con titolo, credito e link originale.
#   tree:      file committati nel repo (prefissi + regex sul nome)
#   artifacts: artifact di GitHub Actions (prefisso del nome artifact)
#   keep:      quanti file tenere per estensione
# ---------------------------------------------------------------------------
SECTIONS = [
    dict(id="market-wrap", title="Market Wrap", repo="market-wrap",
         desc="Wrap cross-asset del mattino e della sera.",
         artifacts=["market-wrap-evening", "market-wrap-morning"],
         include=r"^(wrap_.*\.png|market-wrap-.*\.pdf)$",
         keep={".png": 5, ".pdf": 5}, hero=r"^wrap_"),
    dict(id="headline-wrap", title="Headline Wrap", repo="market-wrap",
         desc="Digest delle headline (08/13/18, giorni feriali).",
         tree=["uscite/headline/"], include=r"^headline_.*\.png$", keep={".png": 5}),
    dict(id="desk", title="Desk · Liquidità, flussi, vol", repo="desk",
         desc="Card giornaliera del desk (canale pubblico).",
         tree=["out/"], include=r"^card-.*\.png$",
         keep={".png": 5}),
    dict(id="tvol-wrap", title="Vol Treasury & Eurex (TVOL)", repo="tvol-wrap",
         desc="Volatilità implicita Treasury, smile, flussi Eurex.",
         tree=["data/", "data/commento/"], include=r"^(last_card|last_chart|multi_card|eurex_card|flussi_card|smile_[A-Z]+|tvol_card)\.png$",
         keep={".png": 12}, hero=r"^(tvol_card|last_card)"),
    dict(id="fi-wrap", title="Fixed Income", repo="fi-wrap",
         desc="Fixed Income Wrap (workflow principale).",
         artifacts=["fixed-income-wrap"],
         keep={".png": 5, ".pdf": 5, ".xlsx": 3}),
    dict(id="fi-giornaliero", title="Fixed Income · giornaliero", repo="fi-wrap",
         desc="Pagina giornaliera Fixed Income (workflow 'Fixed Income giornaliero').",
         artifacts=["prova-fixed-income-giornaliero", "fixed-income-giornaliero"],
         keep={".png": 5, ".pdf": 5, ".xlsx": 3}),
    dict(id="ice-evening-wrap", title="ICE Evening (energia)", repo="ice-evening-wrap",
         desc="Chiusure ICE energia: curve e card serale.",
         tree=["Claude outputs/", "data/commento/"], include=r"^(wrap_.*\.png|curve_.*\.png|anteprima\.(png|xlsx)|ice_card\.png)$",
         keep={".png": 6, ".xlsx": 2}, hero=r"^(ice_card|wrap_)"),
    dict(id="pun-wrap", title="PUN & Power Italia", repo="pun-wrap",
         desc="PUN, GME, fondamentali e bolletta.",
         artifacts=["pun-wrap-immagini"], include=r"^market_wrap_.*\.png$",
         keep={".png": 4}, hero=r"analisi"),
    dict(id="pun-diagnosi", title="PUN · quadro MGP (diagnosi)", repo="pun-wrap",
         desc="Pannello GME del workflow 'PUN diagnosi fonti'.",
         artifacts=["pannello-gme"], include=r"\.png$", keep={".png": 3}),
    dict(id="basis-trade-wrap", title="Basis Trade", repo="basis-trade-wrap",
         desc="Basis trade Treasury (oggi pubblica solo testo).",
         tree=["data/", "out/"], keep={".png": 5, ".pdf": 5}),
    dict(id="macro-wrap-bot", title="Macro Wrap", repo="macro-wrap-bot",
         desc="Wrap macro giornaliero.",
         tree=["reports/"], include=r"-macro\.pdf$", keep={".pdf": 5}),
    dict(id="macro-settimanale", title="Macro Wrap Settimanale", repo="macro-wrap-bot",
         desc="Wrap macro settimanale.",
         tree=["reports/"], include=r"(sett|week).*\.pdf$", keep={".pdf": 5}),
    dict(id="oil-wrap", title="Oil Wrap", repo="oil-wrap",
         desc="Petrolio: prezzi, spread, card di commento.",
         tree=["data/commento/"], artifacts=["oil-wrap-"], include=r"\.png$",
         keep={".png": 5}, hero=r"oil_card|wrap"),
    dict(id="spr-monitor", title="EIA Weekly (WPSR)", repo="spr-monitor",
         desc="Report settimanale EIA (WPSR) e riserva strategica.",
         artifacts=["inventories"], keep={".png": 6, ".pdf": 3}, hero=r"scorte"),
    dict(id="spr-doe", title="SPR DOE monitor", repo="spr-monitor",
         desc="Monitor riserva strategica DOE (oggi solo avvisi Telegram, nessun file salvato).",
         artifacts=["spr-doe"], keep={".png": 3}),
    dict(id="hicp-wrap", title="HICP / Inflazione", repo="hicp-wrap",
         desc="Inflazione area euro: uscita PDF e tabelle Excel.",
         artifacts=["uscita"], keep={".pdf": 3, ".xlsx": 3}),
    dict(id="blas-weekly", title="Blas Weekly", repo="Blas-Weekly-Wrap",
         desc="Scheda operativa settimanale e thesis tracker.",
         tree=["weekly/"], keep={".png": 3, ".pdf": 3, ".xlsx": 2}),
    dict(id="wrap-monitor", title="Wrap Monitor", repo="wrap-monitor",
         desc="Monitor delle pipeline (oggi solo report testuali, non pubblicati).",
         tree=["out/"], keep={".png": 3, ".pdf": 3}),
    dict(id="gmail-wrap", title="Gmail Wrap", repo="gmail-wrap", kind="private",
         desc="Riassunto della posta: generato da email personali, quindi non pubblicato.",
         private_reason="Non pubblicato (contenuto privato)"),
    dict(id="bloomberg", title="Bloomberg · ultimi titoli", repo="bloomberg-wrap", kind="headlines",
         credit="Bloomberg", desc="Solo i titoli degli ultimi articoli letti: nessun PDF ne' testo (copyright Bloomberg).",
         headlines=["articoli/"], headlines_keep=20, mirror=True),
    dict(id="spg", title="S&P Global · ultimi titoli", repo="imf-spglobal-wrap_", kind="headlines",
         credit="S&P Global", desc="Solo titoli e date: i PDF S&P Global (copyright) sono nel repo privato.",
         headlines=["articoli/spg/"], headlines_keep=20, mirror=True),
    # ---- imf-spglobal-wrap_: wrap non-PDF (S&P Global escluso) ----
    dict(id="analysis-corner", title="Analysis Corner", repo="imf-spglobal-wrap_",
         desc="Analysis Corner (Commissione UE).",
         artifacts=["analysis-corner"], include=r"\.(png|pdf|xlsx)$", keep={".png": 5, ".pdf": 3, ".xlsx": 2}),
    dict(id="cbo", title="CBO Alert", repo="imf-spglobal-wrap_",
         desc="Avvisi CBO (oggi solo testo, nessun file).",
         artifacts=["cbo-wrap"], include=r"\.(png|pdf|xlsx)$", keep={".png": 5, ".pdf": 3, ".xlsx": 2}),
    dict(id="cftc", title="CFTC Wrap", repo="imf-spglobal-wrap_",
         desc="Posizionamento CFTC (COT).",
         artifacts=["cftc-wrap"], include=r"\.(png|pdf|xlsx)$", keep={".png": 5, ".pdf": 3, ".xlsx": 2}),
    dict(id="fiscal-flows", title="Fiscal Flows Wrap", repo="imf-spglobal-wrap_",
         desc="Flussi fiscali Tesoro USA (Daily Treasury Statement).",
         artifacts=["fiscal-flows-wrap"], include=r"\.(png|pdf|xlsx)$", keep={".png": 5, ".pdf": 3, ".xlsx": 2}),
    dict(id="ecb", title="ECB Wrap", repo="imf-spglobal-wrap_",
         desc="Discorsi, blog e comunicati BCE.",
         artifacts=["ecb-wrap"], include=r"\.(png|pdf|xlsx)$", keep={".png": 5, ".pdf": 3, ".xlsx": 2}),
    dict(id="ep-think-tank", title="EP Think Tank Wrap", repo="imf-spglobal-wrap_",
         desc="Pubblicazioni del Think Tank del Parlamento europeo.",
         artifacts=["ep-wrap"], include=r"\.(png|pdf|xlsx)$", keep={".png": 5, ".pdf": 3, ".xlsx": 2}),
    dict(id="eurostat", title="Eurostat Wrap", repo="imf-spglobal-wrap_",
         desc="Uscite Eurostat.",
         artifacts=["estat-wrap"], include=r"\.(png|pdf|xlsx)$", keep={".png": 5, ".pdf": 3, ".xlsx": 2}),
    dict(id="istat", title="Istat Wrap", repo="imf-spglobal-wrap_",
         desc="Uscite Istat.",
         artifacts=["istat-wrap"], include=r"\.(png|pdf|xlsx)$", keep={".png": 5, ".pdf": 3, ".xlsx": 2}),
    dict(id="press-corner", title="Press corner Wrap", repo="imf-spglobal-wrap_",
         desc="Press corner della Commissione UE.",
         artifacts=["pc-wrap"], include=r"\.(png|pdf|xlsx)$", keep={".png": 5, ".pdf": 3, ".xlsx": 2}),
    dict(id="zerohedge", title="ZeroHedge Wrap", repo="imf-spglobal-wrap_",
         desc="Wrap ZeroHedge.",
         artifacts=["zh-wrap"], include=r"\.(png|pdf|xlsx)$", keep={".png": 5, ".pdf": 3, ".xlsx": 2}),
    # ---- fonti istituzionali -------------------------------------------------
    dict(id="fed", title="Federal Reserve", repo="FED-Wrap", kind="papers",
         credit="Federal Reserve", desc="Ultime pubblicazioni Fed (Board e distretti) e wrap Fed.",
         papers=["dati/pdf/ingresso/", "dati/pdf/elaborati/"], meta="fedbis",
         artifacts=["fed-wrap-quotidiano", "fed-wrap-settimanale", "fed-wrap-mensile"],
         include=r"\.pdf$", keep={".pdf": 3}, papers_keep=20),
    dict(id="bis", title="BIS", repo="Bis-Wrap", kind="papers",
         credit="BIS", desc="Ultime pubblicazioni BIS (Quarterly Review, Bulletin, WP, discorsi) e wrap BIS.",
         papers=["dati/pdf/ingresso/", "dati/pdf/elaborati/"], meta="fedbis",
         artifacts=["bis-wrap-quotidiano", "bis-wrap-settimanale", "bis-wrap-mensile"],
         include=r"\.pdf$", keep={".pdf": 3}, papers_keep=20),
    dict(id="imf", title="IMF", repo="imf-spglobal-wrap_", kind="papers",
         credit="IMF", desc="Ultime pubblicazioni IMF (WEO, GFSR, Working Paper) e wrap IMF.",
         papers=["articoli/imf/"], meta="imf",           # solo IMF: articoli/spg/ NON va pubblicato
         artifacts=["imf-wrap"], include=r"^imf-.*\.pdf$", keep={".pdf": 3}, papers_keep=20),
]

# Mai pubblicati, anche se un giorno contenessero png/pdf/xlsx.
EXCLUDED = {
    "chat-wrap": "riassunti di conversazioni private di un gruppo Telegram",
    "gmail-wrap": "contenuto di email private",
    "bloomberg-wrap (PDF)": "articoli di terzi protetti da copyright: si pubblicano solo titolo, data e link",
    "imf-spglobal-wrap_/articoli/spg (PDF)": "articoli S&P Global protetti da copyright: PDF solo nel repo privato",
}
DENY_PATH = re.compile(r"(^|/)(\.|state/|archive/|examples/|inbox|fonts/|samples/|articoli/spg|saltati/)|\.env|secret|token|credential|session|password", re.I)

# Repo PRIVATO per i PDF Bloomberg / S&P: se MIRROR_DIR punta a un suo checkout,
# lo script vi copia gli ultimi PDF e il sito pubblico mostra solo titolo, data e link.
MIRROR_DIR = os.environ.get("MIRROR_DIR") or ""
MIRROR_REPO = os.environ.get("MIRROR_REPO", "guado77/market-desk-private")
MIRROR_BRANCH = os.environ.get("MIRROR_BRANCH", "main")
TOKEN = os.environ.get("WRAPS_READ_TOKEN") or os.environ.get("GH_TOKEN") or ""
API = "https://api.github.com"
CALLS = 0


def log(*a):
    print(*a, flush=True)


class _NoAuthOnRedirect(urllib.request.HTTPRedirectHandler):
    """Gli zip degli artifact rimandano a uno storage esterno: li' il token NON va inviato."""
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        new = super().redirect_request(req, fp, code, msg, headers, newurl)
        if new is not None and urllib.parse.urlparse(newurl).hostname != "api.github.com":
            new.headers = {k: v for k, v in new.headers.items() if k.lower() != "authorization"}
            new.unredirected_hdrs = {}
        return new


OPENER = urllib.request.build_opener(_NoAuthOnRedirect)


def api(path, raw=False, accept=None, tries=3):
    global CALLS
    url = path if path.startswith("http") else API + path
    hdr = {"Authorization": "Bearer " + TOKEN, "X-GitHub-Api-Version": "2022-11-28",
           "Accept": accept or "application/vnd.github+json", "User-Agent": "market-desk-sync"}
    for i in range(tries):
        CALLS += 1
        try:
            with OPENER.open(urllib.request.Request(url, headers=hdr), timeout=180) as r:
                data = r.read()
                return data if raw else json.loads(data)
        except urllib.error.HTTPError as e:
            if e.code in (404, 410, 451):
                return None
            if e.code in (401, 403) and i == tries - 1:
                raise
            if i == tries - 1:
                raise
        except urllib.error.URLError:
            if i == tries - 1:
                raise
        time.sleep(3 * (i + 1))


# ---------------------------------------------------------------- date utility
MESI = {"gen": 1, "feb": 2, "mar": 3, "apr": 4, "mag": 5, "giu": 6, "lug": 7, "ago": 8, "set": 9, "ott": 10, "nov": 11, "dic": 12}


def name_date(name):
    """Data (e ora, se c'e') ricavata dal nome del file. Restituisce datetime UTC o None."""
    m = re.search(r"(20\d\d)[-_]?(\d\d)[-_]?(\d\d)(?:[-_T](\d\d)(\d\d)(Z)?)?", name)
    try:
        if m:
            y, mo, d = int(m[1]), int(m[2]), int(m[3])
            if m[4]:
                t = dt.datetime(y, mo, d, int(m[4]), int(m[5]))
                return t.replace(tzinfo=dt.timezone.utc) if m[6] else t.replace(tzinfo=ROME).astimezone(dt.timezone.utc)
            return dt.datetime(y, mo, d, 12, tzinfo=ROME).astimezone(dt.timezone.utc)
        m = re.search(r"(\d\d)-(\d\d)-(20\d\d)", name)
        if m:
            return dt.datetime(int(m[3]), int(m[2]), int(m[1]), 12, tzinfo=ROME).astimezone(dt.timezone.utc)
        m = re.search(r"(\d{1,2})(gen|feb|mar|apr|mag|giu|lug|ago|set|ott|nov|dic)(20\d\d|\d\d)", name, re.I)
        if m:
            y = int(m[3]) + (2000 if len(m[3]) == 2 else 0)
            return dt.datetime(y, MESI[m[2].lower()], int(m[1]), 12, tzinfo=ROME).astimezone(dt.timezone.utc)
    except ValueError:
        pass
    return None


def iso_parse(s):
    if not s:
        return None
    try:
        if len(s) == 10:
            return dt.datetime.fromisoformat(s).replace(hour=12, tzinfo=ROME).astimezone(dt.timezone.utc)
        return dt.datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(dt.timezone.utc)
    except ValueError:
        return None


def best_date(fname, ts):
    """Data del nome se presente (piu' affidabile per artifact che ricaricano file vecchi), altrimenti ts."""
    nd = name_date(fname)
    if nd and ts and abs((ts - nd).total_seconds()) < 36 * 3600:
        return ts
    return nd or ts


def commit_date(repo, path, cache={}):
    k = (repo, path)
    if k not in cache:
        c = api(f"/repos/{OWNER}/{repo}/commits?per_page=1&path=" + urllib.parse.quote(path))
        cache[k] = iso_parse(c[0]["commit"]["committer"]["date"]) if c else None
    return cache[k]


# ---------------------------------------------------------------- nomi sicuri
def safe_name(name):
    base, ext = os.path.splitext(name)
    base = unicodedata.normalize("NFKD", base).encode("ascii", "ignore").decode()
    base = re.sub(r"[^A-Za-z0-9._-]+", "_", base).strip("._ ")[: 140 - len(ext)] or "file"
    return base + ext.lower()


def git_blob_sha(data):
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


# ---------------------------------------------------------------- raccolta candidati
def tree_files(repo, cache={}):
    if repo not in cache:
        info = api(f"/repos/{OWNER}/{repo}")
        if not info:
            cache[repo] = None
        else:
            t = api(f"/repos/{OWNER}/{repo}/git/trees/{info['default_branch']}?recursive=1")
            cache[repo] = [x for x in t["tree"] if x["type"] == "blob"]
    return cache[repo]


def allowed(path, sec):
    name = path.rsplit("/", 1)[-1]
    if not name.lower().endswith(ALLOWED) or DENY_PATH.search(path):
        return False
    return not sec.get("include") or re.search(sec["include"], name, re.I)


def from_tree(sec):
    out = []
    files = tree_files(sec["repo"]) or []
    for f in files:
        d, _, name = f["path"].rpartition("/")
        if (d + "/") not in sec.get("tree", []) or not allowed(f["path"], sec):
            continue
        if f.get("size", 0) > MAX_BYTES:
            continue
        out.append(dict(name=name, path=f["path"], sha=f["sha"], size=f["size"], origin="repo", nd=name_date(name)))
    # data: dal nome; se manca, dall'ultimo commit (solo per i candidati)
    for c in out:
        c["date"] = c["nd"] or commit_date(sec["repo"], c["path"])
    return out


def list_artifacts(repo, cache={}):
    if repo not in cache:
        res, page = [], 1
        while page <= 3:
            j = api(f"/repos/{OWNER}/{repo}/actions/artifacts?per_page=100&page={page}")
            if not j or not j.get("artifacts"):
                break
            res += j["artifacts"]
            if len(j["artifacts"]) < 100:
                break
            page += 1
        cache[repo] = [a for a in res if not a.get("expired")]
    return cache[repo]


def from_artifacts(sec, prev_by_artifact):
    """Scarica gli artifact piu' recenti (max 6 per nome) ed estrae solo png/pdf/xlsx ammessi."""
    out = []
    arts = [a for a in list_artifacts(sec["repo"]) if any(a["name"].startswith(p) for p in sec.get("artifacts", []))]
    arts.sort(key=lambda a: a["created_at"], reverse=True)
    per_name = {}
    for a in arts:
        per_name.setdefault(a["name"], []).append(a)
    chosen = sorted([a for v in per_name.values() for a in v[:6]], key=lambda a: a["created_at"], reverse=True)
    need = sum(sec.get("keep", {}).values()) or 5
    for a in chosen:
        ts = iso_parse(a["created_at"])
        if a["size_in_bytes"] > 200 * 1024 * 1024:
            continue
        cached = prev_by_artifact.get(str(a["id"]))
        if cached is not None:           # gia' visto: riusa l'elenco, niente download
            for c in cached:
                out.append(dict(c, date=iso_parse(c["date"]), artifact=a["id"], data=None))
            continue
        blob = api(f"/repos/{OWNER}/{sec['repo']}/actions/artifacts/{a['id']}/zip", raw=True)
        if not blob:
            continue
        with zipfile.ZipFile(io.BytesIO(blob)) as z:
            for zi in z.infolist():
                if zi.is_dir() or zi.file_size > MAX_BYTES or not allowed(zi.filename, sec):
                    continue
                data = z.read(zi)
                name = zi.filename.rsplit("/", 1)[-1]
                out.append(dict(name=name, path=f"artifact:{a['name']}/{zi.filename}", sha=git_blob_sha(data),
                                size=len(data), origin="artifact", artifact=a["id"], data=data,
                                date=best_date(name, ts)))
        if all(len({c["name"] for c in out if c["name"].lower().endswith(e)}) >= n for e, n in sec.get("keep", {}).items()):
            break
    return out


def paper_meta(sec):
    """Titolo, link, fonte e data dai metadati del repo (schede/stato), se ci sono."""
    repo, files = sec["repo"], tree_files(sec["repo"]) or []
    raw = lambda p: api(f"/repos/{OWNER}/{repo}/contents/" + urllib.parse.quote(p), raw=True, accept="application/vnd.github.raw")
    schede = {}
    for f in files:
        if re.match(r"^dati/schede/.*\.json$", f["path"]) and (sec["meta"] != "imf" or "/imf-" in f["path"]):
            try:
                schede.update(json.loads(raw(f["path"]) or b"{}"))
            except ValueError:
                pass
    meta = {}
    if sec["meta"] == "fedbis":
        try:
            pe = json.loads(raw("state/pdf_elaborati.json") or b"{}")
        except ValueError:
            pe = {}
        for v in pe.get("hash", {}).values():
            s = schede.get(v.get("id"), {})
            meta[v["file"]] = dict(title=s.get("titolo"), url=s.get("link"), fonte=s.get("fonte"),
                                   authors=s.get("autori"), date=s.get("data") or v.get("quando"), quando=v.get("quando"))
    else:  # imf: abbina per titolo normalizzato
        norm = lambda s: re.sub(r"[^a-z0-9]+", "", (s or "").lower())
        by_title = {norm(s.get("titolo")): s for s in schede.values() if s.get("titolo")}
        for f in files:
            if f["path"].startswith("articoli/imf/") and f["path"].endswith(".pdf"):
                stem = f["path"].rsplit("/", 1)[-1][:-4]
                s = by_title.get(norm(stem)) or next((v for k, v in by_title.items() if k and len(k) > 25 and (k.startswith(norm(stem)[:60]) or norm(stem).startswith(k[:60]))), {})
                meta[f["path"].rsplit("/", 1)[-1]] = dict(title=s.get("titolo"), url=s.get("link"), fonte=s.get("serie") or s.get("tipo"),
                                                         date=s.get("data"))
    return meta


def from_headlines(sec, prev_links):
    """Solo titoli (dal nome del PDF) e data nel sito pubblico. I PDF vanno, se c'e'
    MIRROR_DIR, SOLO nel repo privato; nel sito pubblico c'e' il link a quel repo."""
    out = []
    for f in tree_files(sec["repo"]) or []:
        p = f["path"]
        if not p.lower().endswith(".pdf") or not any(p.startswith(d) for d in sec["headlines"]):
            continue
        name = p.rsplit("/", 1)[-1][:-4]
        title = re.sub(r"\s*[-|]\s*Bloomberg(\s*(\(\d+\))?)?$", "", name).strip()
        arch = re.search(r"archivio/(20\d\d-\d\d-\d\d)/", p)
        d = iso_parse(arch[1]) if arch else None
        slug = re.match(r"^(20\d\d-\d\d-\d\d)-([a-z0-9-]+)$", title)
        if slug:   # nome tipo 2026-10-17-ecb-leans-toward-... -> titolo leggibile
            d = d or iso_parse(slug[1])
            t = re.sub(r"-s-", "'s ", slug[2]).replace("-", " ")
            t = re.sub(r"\bt\b", "t", re.sub(r"\bcan t\b", "can't", t))
            title = t[:1].upper() + t[1:]
        out.append(dict(title=title, path=p, sha=f["sha"], size=f["size"], date=d))
    for c in out:
        if c["date"] is None:
            c["date"] = commit_date(sec["repo"], c["path"])
    seen, res = set(), []
    for c in sorted(out, key=lambda c: c["date"] or dt.datetime.min.replace(tzinfo=dt.timezone.utc), reverse=True):
        k = c["title"].lower()
        if k in seen:
            continue
        seen.add(k)
        h = dict(title=c["title"], date=iso(c["date"]), url=None, credit=sec["credit"], private=None,
                 _c=c)
        if sec["credit"] == "Bloomberg":
            h["search"] = "https://www.bloomberg.com/search?query=" + urllib.parse.quote(c["title"])
        res.append(h)
    res = res[: sec.get("headlines_keep", 20)]
    if sec.get("mirror") and MIRROR_DIR:
        folder = os.path.join(MIRROR_DIR, sec["id"])
        os.makedirs(folder, exist_ok=True)
        keep, used = set(), set()
        for h in res:
            c = h["_c"]
            if c["size"] > 95 * 1024 * 1024:
                continue
            fn = safe_name(c["path"].rsplit("/", 1)[-1])
            stem, ext = os.path.splitext(fn); k = 2
            while fn in used:
                fn = f"{stem}_{k}{ext}"; k += 1
            used.add(fn); keep.add(fn)
            dest = os.path.join(folder, fn)
            same = False
            if os.path.exists(dest):
                with open(dest, "rb") as fh:
                    same = git_blob_sha(fh.read()) == c["sha"]
            if not same:
                data = api(f"/repos/{OWNER}/{sec['repo']}/git/blobs/{c['sha']}", raw=True, accept="application/vnd.github.raw")
                if data is None:
                    continue
                with open(dest, "wb") as fh:
                    fh.write(data)
            h["private"] = f"https://github.com/{MIRROR_REPO}/blob/{MIRROR_BRANCH}/{sec['id']}/" + urllib.parse.quote(fn)
        for fn in os.listdir(folder):
            if fn not in keep:
                os.remove(os.path.join(folder, fn))
    elif sec.get("mirror"):
        for h in res:   # senza repo privato a disposizione: conserva i link gia' noti
            h["private"] = prev_links.get((sec["id"], h["title"]))
    for h in res:
        h.pop("_c", None)
    return res


def from_papers(sec):
    files = tree_files(sec["repo"]) or []
    meta = paper_meta(sec)
    out = []
    for f in files:
        p = f["path"]
        if not p.lower().endswith(".pdf") or not any(p.startswith(d) for d in sec["papers"]):
            continue
        if "articoli/spg" in p or "/saltati/" in p:
            continue
        name = p.rsplit("/", 1)[-1]
        m = meta.get(name, {})
        arch = re.search(r"archivio/(20\d\d-\d\d-\d\d)/", p)
        d = iso_parse(m.get("quando")) or iso_parse(m.get("date")) or name_date(name) or (iso_parse(arch[1]) if arch else None)
        url = m.get("url") if re.match(r"^https?://", m.get("url") or "") else None   # mai file:// del runner
        fonte = m.get("fonte") if m.get("fonte") and not re.search(r"PDF (locale|salvato)", m.get("fonte")) else None
        out.append(dict(name=name, path=p, sha=f["sha"], size=f["size"], origin="repo", date=d,
                        title=m.get("title") or re.sub(r"^20\d\d-\d\d-\d\d-", "", name[:-4]).replace("-", " "),
                        url=url, fonte=fonte, authors=m.get("authors"),
                        pubdate=m.get("date"), too_big=f["size"] > MAX_BYTES))
    # senza data: data dell'ultimo commit (ultimi arrivati, es. articoli/imf/ in attesa)
    for c in out:
        if c["date"] is None:
            c["date"] = commit_date(sec["repo"], c["path"])
    out.sort(key=lambda c: (c["date"] or dt.datetime.min.replace(tzinfo=dt.timezone.utc)), reverse=True)
    seen, res = set(), []
    for c in out:   # stesso documento salvato due volte: tieni il piu' recente
        k = re.sub(r"[^a-z0-9]+", "", c["title"].lower())
        if k not in seen:
            seen.add(k); res.append(c)
    return res[: sec.get("papers_keep", 20)]


# ---------------------------------------------------------------- scrittura
def materialize(sec, c, used):
    """Scrive il file in assets/<sezione>/ (salta se identico). Ritorna il path relativo."""
    folder = os.path.join(ASSETS, sec["id"])
    os.makedirs(folder, exist_ok=True)
    fn = safe_name(c["name"])
    stem, ext = os.path.splitext(fn)
    k = 2
    while fn in used:
        fn = f"{stem}_{k}{ext}"; k += 1
    used.add(fn)
    dest = os.path.join(folder, fn)
    if os.path.exists(dest):
        with open(dest, "rb") as fh:
            if git_blob_sha(fh.read()) == c["sha"]:
                return f"assets/{sec['id']}/{fn}"
    data = c.get("data")
    if data is None:
        if c["origin"] == "repo":
            data = api(f"/repos/{OWNER}/{sec['repo']}/git/blobs/{c['sha']}", raw=True, accept="application/vnd.github.raw")
        if data is None:   # artifact gia' visto ma file locale mancante: riscarica
            blob = api(f"/repos/{OWNER}/{sec['repo']}/actions/artifacts/{c['artifact']}/zip", raw=True)
            if blob:
                with zipfile.ZipFile(io.BytesIO(blob)) as z:
                    data = z.read(c["path"].split("/", 1)[1])
    if data is None:
        raise RuntimeError("download fallito: " + c["path"])
    with open(dest, "wb") as fh:
        fh.write(data)
    return f"assets/{sec['id']}/{fn}"


def iso(d):
    return d.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if d else None


def main():
    if not TOKEN:
        log("::warning::WRAPS_READ_TOKEN non impostato: sincronizzazione saltata. "
            "Crea il token fine-grained (vedi README, sezione 'Token') e aggiungilo come secret del repo.")
        return 0
    prev = {}
    if os.path.exists(MANIFEST):
        with open(MANIFEST) as fh:
            prev = json.load(fh)
    prev_by_artifact = {}
    for s in prev.get("sections", []):
        for f in s.get("files", []) + s.get("papers", []):
            if f.get("artifact"):
                prev_by_artifact.setdefault(str(f["artifact"]), []).append(
                    dict(name=f["name_orig"], path=f["source"], sha=f["sha"], size=f["size"], origin="artifact", date=f["date"]))
    # gli artifact visti ma senza file selezionati vanno comunque ricordati
    for aid in prev.get("artifacts_seen", {}).get("empty", []):
        prev_by_artifact.setdefault(str(aid), [])

    prev_links = {(s["id"], h["title"]): h.get("private") for s in prev.get("sections", []) for h in s.get("headlines", []) if h.get("private")}
    sections, keep_paths, seen_empty = [], set(), []
    for sec in SECTIONS:
        log(f"== {sec['id']} ({sec['repo']})")
        entry = dict(id=sec["id"], title=sec["title"], repo=sec["repo"], kind=sec.get("kind", "wrap"),
                     desc=sec["desc"], credit=sec.get("credit"), files=[], papers=[], headlines=[], error=None)
        if sec.get("kind") == "private":
            entry.update(private=sec["private_reason"], updated=None, hero=None)
            sections.append(entry)
            log("   non pubblicato (contenuto privato)")
            continue
        try:
            if sec.get("kind") == "headlines":
                entry["headlines"] = from_headlines(sec, prev_links)

            cands = []
            if sec.get("tree"):
                cands += from_tree(sec)
            if sec.get("artifacts"):
                arts = from_artifacts(sec, prev_by_artifact)
                ids_with = {c["artifact"] for c in arts}
                for a in list_artifacts(sec["repo"]):
                    if any(a["name"].startswith(p) for p in sec["artifacts"]) and a["id"] not in ids_with:
                        seen_empty.append(a["id"])
                cands += arts
            # dedup per nome: tieni il piu' recente
            best = {}
            for c in cands:
                if c["date"] is None:
                    continue
                if c["name"] not in best or c["date"] > best[c["name"]]["date"]:
                    best[c["name"]] = c
            cands = sorted(best.values(), key=lambda c: c["date"], reverse=True)
            used = set()
            for ext, n in sec.get("keep", {}).items():
                for c in [c for c in cands if c["name"].lower().endswith(ext)][:n]:
                    rel = materialize(sec, c, used)
                    keep_paths.add(rel)
                    entry["files"].append(dict(name=os.path.basename(rel), name_orig=c["name"], path=rel, type=ext[1:],
                                               date=iso(c["date"]), size=c["size"], sha=c["sha"], source=c["path"],
                                               artifact=c.get("artifact")))
            hero = sec.get("hero")
            pngs = [f for f in entry["files"] if f["type"] == "png"]
            # immagine principale: solo fra le piu' recenti (entro 36 ore dall'ultima),
            # cosi' una card vecchia o vuota (es. oil_card.png di settembre) non
            # copre l'output nuovo; fra queste vince il nome indicato in "hero"
            ts = lambda f: dt.datetime.fromisoformat(f["date"][:-1]).timestamp()        # noqa: E731
            if pngs:
                ultimo = max(ts(f) for f in pngs)
                for f in entry["files"]:
                    if ultimo - ts(f) > 7 * 86400:
                        f["vecchio"] = True
                pngs = [f for f in pngs if ultimo - ts(f) <= 36 * 3600]
            if hero:
                pngs.sort(key=lambda f: (not re.search(hero, f["name_orig"], re.I), -ts(f)))
            else:
                pngs.sort(key=lambda f: -ts(f))
            entry["hero"] = pngs[0]["path"] if pngs else None
            if sec.get("kind") == "papers":
                for c in from_papers(sec):
                    rel = None if c["too_big"] else materialize(sec, c, used)
                    if rel:
                        keep_paths.add(rel)
                    entry["papers"].append(dict(title=c["title"], path=rel, url=c["url"], fonte=c["fonte"],
                                                authors=c["authors"], pubdate=c["pubdate"], date=iso(c["date"]),
                                                size=c["size"], sha=c["sha"], source=c["path"], name_orig=c["name"],
                                                credit=sec["credit"]))
            dates = [f["date"] for f in entry["files"] + entry["papers"] + entry["headlines"] if f.get("date")]
            entry["updated"] = max(dates) if dates else None
            log(f"   file: {len(entry['files'])}  pubblicazioni: {len(entry['papers'])}  titoli: {len(entry['headlines'])}  ultimo: {entry['updated']}")
        except Exception as e:  # una sezione rotta non blocca le altre: tiene i file precedenti
            log(f"::warning::{sec['id']}: {e}")
            old = next((s for s in prev.get("sections", []) if s["id"] == sec["id"]), None)
            if old:
                entry = dict(old, error="ultimo aggiornamento non riuscito")
                for f in old.get("files", []) + old.get("papers", []):
                    if f.get("path"):
                        keep_paths.add(f["path"])
            else:
                entry["error"] = "non raggiungibile"
        sections.append(entry)

    # rimuovi i file non piu' nel manifest (si tengono solo gli ultimi)
    for dirpath, _, fns in os.walk(ASSETS):
        for fn in fns:
            rel = os.path.relpath(os.path.join(dirpath, fn), ROOT).replace(os.sep, "/")
            if rel not in keep_paths and fn != ".gitkeep":
                os.remove(os.path.join(dirpath, fn))

    # stato delle pipeline dal wrap-monitor (report/stato.json): semafori del sito
    monitor = prev.get("monitor")
    locale = os.environ.get("STATO_MONITOR") or ""
    try:
        if locale and os.path.isfile(locale):              # passato dal Cruscotto del wrap-monitor
            with open(locale, encoding="utf-8") as fh:
                monitor = json.load(fh)
            log(f"stato wrap-monitor (locale): {len(monitor.get('workflow', {}))} workflow")
            raw = None
        else:
            raw = api(f"/repos/{OWNER}/wrap-monitor/contents/report/stato.json", raw=True,
                      accept="application/vnd.github.raw")
        if raw:
            monitor = json.loads(raw)
            log(f"stato wrap-monitor: {len(monitor.get('workflow', {}))} workflow, generato {monitor.get('generato')}")
    except Exception as e:                                            # noqa: BLE001
        log(f"::warning::stato wrap-monitor non letto: {e}")
    manifest = dict(generated_at=prev.get("generated_at"), owner=OWNER, timezone="Europe/Rome",
                    sections=sections, excluded=EXCLUDED, artifacts_seen=dict(empty=sorted(set(seen_empty))),
                    monitor=monitor)
    comparable = lambda m: json.dumps({k: v for k, v in m.items() if k != "generated_at"}, sort_keys=True)
    if comparable(manifest) != comparable(prev):
        manifest["generated_at"] = iso(dt.datetime.now(dt.timezone.utc))
    with open(MANIFEST, "w") as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=1)
    log(f"manifest scritto, chiamate API: {CALLS}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
