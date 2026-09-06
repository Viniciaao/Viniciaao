#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Baixa os 5 sims mais recentes do CurseForge (Sims / Households) + TODOS os CCs
listados na descrição de cada um, extrai tudo e monta um pacote único
(TUDO_JUNTO_Sims4) pronto para copiar em Documents/Electronic Arts/The Sims 4.

Executado pelo GitHub Actions (.github/workflows/sims4-download.yml), porque o
sandbox do agente não alcança CurseForge / TSR / Patreon.
"""
import concurrent.futures as cf
import html
import json
import pathlib
import re
import shutil
import subprocess
import sys
import threading
import time
import traceback
import urllib.parse
import zipfile

try:
    from curl_cffi import requests as creq          # TLS "de navegador" (passa pelo Cloudflare)
    HAVE_CFFI = True
except Exception:                                    # noqa
    creq = None
    HAVE_CFFI = False
import requests as preq

ROOT = pathlib.Path(__file__).resolve().parents[1]          # sims4-bundle/
WORK = ROOT / "work"                                         # (gitignored)
ORIG = WORK / "originais"                                    # arquivos como baixados
EXTR = WORK / "extraido"                                     # extração temporária
BUNDLE = WORK / "TUDO_JUNTO_Sims4"                           # pacote final (antes de zipar)
RELEASE = ROOT / "release"                                   # zip completo p/ GitHub Release (gitignored)
OUT = ROOT / "pacote"                                        # o que é commitado no repo

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36")
HEADERS = {"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9,pt-BR;q=0.8",
           "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"}

# Os 5 sims mais recentes de
# https://www.curseforge.com/sims4/search?class=sims-households&sortBy=creation+date (06/09/2026)
SIMS = [
    {"n": 1, "slug": "edith-medina", "name": "Edith Medina", "author": "miwisimsie",
     "file_id": 8821547, "file_name": "Miwisimsie_Edith Medina.zip"},
    {"n": 2, "slug": "luciana-neal", "name": "Luciana Neal", "author": "miwisimsie",
     "file_id": 8821529, "file_name": "Miwisimsie_Luciana Neal.zip"},
    {"n": 3, "slug": "serena-slade", "name": "Serena Slade", "author": "miwisimsie",
     "file_id": 8821492, "file_name": "Miwisimsie_Serena Slade.zip"},
    {"n": 4, "slug": "uminunu-f12-the-sweet-streamer", "name": "Uminunu-F12 The Sweet Streamer",
     "author": "Uminunu", "file_id": 8821024, "file_name": "Uminunu-F12-The Sweet Streamer.zip"},
    {"n": 5, "slug": "rosemary-haney", "name": "Rosemary Haney", "author": "daboosims",
     "file_id": 8819867, "file_name": "Daboosims Rosemary Haney.zip"},
]

# fallback (id de arquivo + nome exato) para CCs do CurseForge, caso a API cfwidget falhe
CF_KNOWN_FILES = {
    "create-a-sim/luna-halter-dress": (6706145, "BackTrack_Luna_Halter_Dress.zip"),
    "create-a-sim/maeve-buckled-heels": (4972335, "BackTrack_Maeve_Buckled_Heels.zip"),
    "create-a-sim/steh-bikini": (6656651, "BackTrack_Steh_Bikini.zip"),
    "create-a-sim/eyebrow-slider-02": (3963688, "miiko-eyebrow-slider-02.zip"),
    "create-a-sim/simpliciatys-alana-hair": (7605509, "Simpliciaty_AlanaHair.zip"),
}

TRAY_EXT = {".trayitem", ".householdbinary", ".hhi", ".sgi", ".bpi", ".blueprint", ".rmi", ".room", ".midi"}
MOD_EXT = {".package", ".ts4script"}
ARCHIVE_EXT = {".zip", ".rar", ".7z"}
IMG_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".txt", ".pdf", ".url", ".html"}

LOG_LINES = []
LOG_LOCK = threading.Lock()


def log(msg):
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    with LOG_LOCK:
        print(line, flush=True)
        LOG_LINES.append(line)


def new_session():
    if HAVE_CFFI:
        s = creq.Session(impersonate="chrome", timeout=120)
        s.headers.update({"Accept-Language": HEADERS["Accept-Language"]})
        return s
    s = preq.Session()
    s.headers.update(HEADERS)
    return s


def safe_name(s, maxlen=80):
    s = html.unescape(s or "").strip()
    s = re.sub(r"[\\/:*?\"<>|\r\n\t]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip(" .")
    return (s[:maxlen] or "item").strip()


def human(n):
    n = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


class PaywallError(Exception):
    pass


class SkipItem(Exception):
    pass


# --------------------------------------------------------------------------- download genérico
def is_real_file(head, content_type=""):
    if head.startswith((b"PK\x03\x04", b"Rar!", b"7z\xbc\xaf", b"DBPF")):
        return True
    ct = (content_type or "").lower()
    if "text/html" in ct or "application/json" in ct or "text/plain" in ct:
        return False
    if head.lstrip().lower().startswith((b"<!doctype", b"<html", b"<?xml", b"{", b"[")):
        return False
    return True


def filename_from_response(r, fallback):
    cd = r.headers.get("Content-Disposition", "") or r.headers.get("content-disposition", "") or ""
    m = re.search(r"filename\*=UTF-8''([^;]+)", cd, re.I)
    if m:
        return safe_name(urllib.parse.unquote(m.group(1)), 150)
    m = re.search(r'filename="?([^";]+)"?', cd, re.I)
    if m:
        return safe_name(m.group(1), 150)
    path = urllib.parse.urlparse(str(r.url)).path
    base = urllib.parse.unquote(path.rsplit("/", 1)[-1])
    if base and "." in base and len(base) < 150:
        return safe_name(base, 150)
    return safe_name(fallback, 150)


def stream_download(url, dest_dir, fallback_name="arquivo.zip", session=None, headers=None, timeout=300):
    sess = session or new_session()
    h = dict(headers or {})
    r = sess.get(url, headers=h, stream=True, timeout=timeout, allow_redirects=True)
    try:
        if r.status_code >= 400:
            raise RuntimeError(f"HTTP {r.status_code} em {url}")
        it = r.iter_content(chunk_size=1 << 16)
        first = b""
        for chunk in it:
            if chunk:
                first = chunk
                break
        ctype = r.headers.get("Content-Type", "") or r.headers.get("content-type", "")
        if not is_real_file(first[:64], ctype):
            raise RuntimeError(f"resposta não é arquivo (Content-Type={ctype}) url={r.url}")
        name = filename_from_response(r, fallback_name)
        if "." not in name:
            name += ".zip" if first.startswith(b"PK") else (".rar" if first.startswith(b"Rar!") else ".package")
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / name
        i = 1
        while dest.exists():
            dest = dest_dir / f"{dest.stem}_{i}{dest.suffix}"
            i += 1
        with open(dest, "wb") as f:
            f.write(first)
            for chunk in it:
                if chunk:
                    f.write(chunk)
    finally:
        try:
            r.close()
        except Exception:  # noqa
            pass
    size = dest.stat().st_size
    if size < 200:
        dest.unlink(missing_ok=True)
        raise RuntimeError(f"arquivo muito pequeno ({size} bytes) url={url}")
    log(f"    OK  {dest.name} ({human(size)})")
    return dest


# --------------------------------------------------------------------------- CurseForge
def cfwidget(path):
    url = f"https://api.cfwidget.com/{path}"
    last = None
    s = new_session()
    for attempt in range(8):
        try:
            r = s.get(url, timeout=60, headers={"Accept": "application/json"})
            if r.status_code == 200:
                return r.json()
            last = f"HTTP {r.status_code}: {r.text[:200]}"
            if r.status_code in (202, 429, 500, 502, 503):
                time.sleep(6)
                continue
            break
        except Exception as e:  # noqa
            last = str(e)
            time.sleep(5)
    raise RuntimeError(f"cfwidget falhou para {path}: {last}")


def cf_download_file(file_id, file_name, dest_dir, project_id=None):
    a, b = file_id // 1000, file_id % 1000
    q = urllib.parse.quote(file_name)
    candidates = [
        f"https://mediafilez.forgecdn.net/files/{a}/{b}/{q}",
        f"https://edge.forgecdn.net/files/{a}/{b}/{q}",
        f"https://media.forgecdn.net/files/{a}/{b}/{q}",
    ]
    if project_id:
        candidates.append(f"https://www.curseforge.com/api/v1/mods/{project_id}/files/{file_id}/download")
    errors = []
    for u in candidates:
        try:
            log(f"    tentando {u}")
            return stream_download(u, dest_dir, file_name)
        except Exception as e:  # noqa
            errors.append(f"{u} -> {e}")
    raise RuntimeError("; ".join(errors))


def cf_project_download(class_slug, dest_dir):
    pid, fid, fname = None, None, None
    try:
        data = cfwidget(f"sims4/{class_slug}")
        pid = data.get("id")
        d = data.get("download") or (data.get("files") or [None])[-1]
        if d:
            fid, fname = d["id"], d["name"]
    except Exception as e:  # noqa
        log(f"    cfwidget: {e}")
    if not fid and class_slug in CF_KNOWN_FILES:
        fid, fname = CF_KNOWN_FILES[class_slug]
    if not fid:
        raise RuntimeError("não consegui descobrir o arquivo do projeto CurseForge")
    return [cf_download_file(fid, fname, dest_dir, pid)]


# --------------------------------------------------------------------------- The Sims Resource
def tsr_download(item_id, dest_dir):
    base = "https://www.thesimsresource.com"
    s = new_session()
    ajax_h = {"X-Requested-With": "XMLHttpRequest", "Accept": "application/json, text/javascript, */*; q=0.01",
              "Referer": f"{base}/downloads/details/id/{item_id}/"}
    # página do item (VIP exclusive?)
    try:
        rp = s.get(f"{base}/downloads/{item_id}", timeout=90)
        if rp.status_code == 200 and "VIP Exclusive" in rp.text and "Early Access" in rp.text:
            raise PaywallError("TSR: item em acesso antecipado exclusivo para VIP")
    except PaywallError:
        raise
    except Exception as e:  # noqa
        log(f"    TSR página do item: {e}")
    # 1) ticket
    r = s.get(f"{base}/ajax.php?c=downloads&a=initDownload&itemid={item_id}&format=zip", headers=ajax_h, timeout=90)
    log(f"    TSR initDownload {r.status_code}: {r.text[:200]!r}")
    try:
        ticket = r.json()["ticket"]
    except Exception:
        raise RuntimeError(f"TSR initDownload sem ticket (HTTP {r.status_code}): {r.text[:120]!r}")
    t0 = time.time()
    # 2) página de download com o ticket -> cookie tsrdlsession
    r2 = s.get(f"{base}/downloads/download/itemId/{item_id}/ticket/{ticket}", timeout=90)
    log(f"    TSR download page {r2.status_code} -> {r2.url}")
    if "captcha" in str(r2.url).lower() or "/downloads/session/" in str(r2.url):
        raise RuntimeError("TSR pediu captcha (sessão não liberada)")
    # 3) espera o contador
    wait = 16 - (time.time() - t0)
    if wait > 0:
        time.sleep(wait)
    # 4) URL final
    url = None
    last = None
    for attempt in range(6):
        r3 = s.get(f"{base}/ajax.php?c=downloads&a=getdownloadurl&ajax=1&itemid={item_id}&mid=0&lk=0&ticket={ticket}",
                   headers=ajax_h, timeout=90)
        last = r3.text[:200]
        try:
            j = r3.json()
        except Exception:
            time.sleep(5)
            continue
        if j.get("url") and not j.get("error"):
            url = j["url"]
            break
        if j.get("error"):
            last = j["error"]
            if "ticket" in j["error"].lower():
                break
        time.sleep(5)
    if not url:
        raise RuntimeError(f"TSR não liberou a URL: {last!r}")
    return [stream_download(url, dest_dir, f"tsr_{item_id}.zip", session=s, headers={"Referer": f"{base}/"})]


# --------------------------------------------------------------------------- Patreon
def patreon_download(post_id, dest_dir, depth=0):
    s = new_session()
    api = f"https://www.patreon.com/api/posts/{post_id}"
    params = {
        "include": "attachments_media,media,attachments",
        "fields[post]": "title,content,current_user_can_view,url,post_file,post_type,published_at",
        "fields[media]": "id,download_url,file_name,image_urls,mimetype,size_bytes",
        "json-api-version": "1.0",
        "json-api-use-default-includes": "false",
    }
    r = s.get(api, params=params, timeout=90,
              headers={"Accept": "application/json", "Referer": f"https://www.patreon.com/posts/{post_id}"})
    log(f"    Patreon API {r.status_code}")
    if r.status_code != 200:
        raise RuntimeError(f"Patreon API HTTP {r.status_code}: {r.text[:160]!r}")
    data = r.json()
    attrs = data.get("data", {}).get("attributes", {}) or {}
    can_view = attrs.get("current_user_can_view")
    title = attrs.get("title")
    files, seen = [], set()
    for inc in data.get("included", []) or []:
        t, a = inc.get("type"), inc.get("attributes", {}) or {}
        if t == "media" and a.get("download_url"):
            u = a["download_url"]
            if u not in seen:
                seen.add(u)
                files.append((a.get("file_name") or f"patreon_{post_id}", u))
        elif t == "attachment" and a.get("url"):
            u = a["url"]
            if u not in seen:
                seen.add(u)
                files.append((a.get("name") or f"patreon_{post_id}", u))
    pf = attrs.get("post_file") or {}
    if pf.get("url") and pf["url"] not in seen:
        files.append((pf.get("name") or f"patreon_{post_id}", pf["url"]))
    content = attrs.get("content") or ""
    ext_links = extract_links(content, base_url=f"https://www.patreon.com/posts/{post_id}")

    if can_view is False and not files and not ext_links:
        raise PaywallError(f"post exclusivo para assinantes ({title})")

    got, errs = [], []
    for name, u in files:
        if pathlib.Path(name).suffix.lower() in IMG_EXT:
            continue
        try:
            got.append(stream_download(u, dest_dir, name, session=s))
        except Exception as e:  # noqa
            errs.append(f"{name}: {e}")
    if not got:
        for u in ext_links[:10]:
            try:
                got += download_by_url(u, dest_dir, depth + 1)
                if got:
                    break
            except Exception as e:  # noqa
                errs.append(f"{u}: {e}")
    if not got:
        if can_view is False:
            raise PaywallError(f"post exclusivo para assinantes ({title})")
        raise RuntimeError("Patreon: nenhum arquivo baixável no post" + (f" ({'; '.join(errs[:3])})" if errs else ""))
    return got


# --------------------------------------------------------------------------- outros hosts
HREF_RE = re.compile(r"""(?:href|src|data-href|data-url)=["']([^"']+)["']""", re.I)
RAW_URL_RE = re.compile(r"https?://[^\s\"'<>\\)]+", re.I)
FILE_HOST_RE = re.compile(
    r"https?://(?:www\.)?(?:simfileshare\.net|(?:[a-z0-9-]+\.)?sfs\.[a-z]+|drive\.google\.com|docs\.google\.com|"
    r"(?:www\.)?dropbox\.com|(?:www\.)?mediafire\.com|mega\.nz|mega\.co\.nz|patreon\.com/file\?|"
    r"[^\s\"'<>]+\.(?:zip|rar|7z|package)(?:\?|$))", re.I)
DL_HINT_RE = re.compile(r"(download|attach|getfile|\bdl\b|dl=|/file/|uploads/)", re.I)


def unwrap_redirect(u):
    """t.umblr.com/redirect?z=..., href.li/?..., curseforge linkout, etc."""
    u = html.unescape(u.strip())
    low = u.lower()
    if "t.umblr.com/redirect" in low:
        z = urllib.parse.parse_qs(urllib.parse.urlparse(u).query).get("z", [""])[0]
        if z:
            u = z
    if low.startswith("https://href.li/?") or low.startswith("http://href.li/?"):
        u = u.split("?", 1)[1]
    if "curseforge.com/linkout" in low:
        remote = urllib.parse.parse_qs(urllib.parse.urlparse(u).query).get("remoteUrl", [""])[0]
        remote = urllib.parse.unquote(remote)
        if "%" in remote:
            remote = urllib.parse.unquote(remote)
        if remote:
            u = remote
    if "google.com/url?" in low:
        q = urllib.parse.parse_qs(urllib.parse.urlparse(u).query).get("q", [""])[0]
        if q:
            u = q
    u = u.replace("http://thesimsresource.com", "https://www.thesimsresource.com")
    u = u.replace("http://www.thesimsresource.com", "https://www.thesimsresource.com")
    return u.strip().rstrip(").,;")


def extract_links(html_text, base_url=None):
    """Links candidatos a arquivo dentro de um HTML (hosts de arquivo, extensões, hints de download, patreon/tsr/cf)."""
    text = html_text or ""
    cands = []
    for m in HREF_RE.finditer(text):
        cands.append(m.group(1))
    for m in RAW_URL_RE.finditer(html.unescape(text)):
        cands.append(m.group(0))
    out, seen = [], set()
    for c in cands:
        u = unwrap_redirect(c)
        if base_url and not u.lower().startswith(("http://", "https://")):
            if u.startswith("#") or u.lower().startswith(("mailto:", "javascript:")):
                continue
            u = urllib.parse.urljoin(base_url, u)
        low = u.lower()
        ok = bool(FILE_HOST_RE.match(u)) or classify(u) in ("tsr", "curseforge", "patreon") \
            or bool(DL_HINT_RE.search(low))
        if not ok:
            continue
        if base_url and u.split("#")[0] == base_url.split("#")[0]:
            continue
        if re.search(r"\.(png|jpe?g|gif|webp|svg|css|js|ico|woff2?)(\?|$)", low):
            continue
        if u not in seen:
            seen.add(u)
            out.append(u)
    # prioridade: hosts de arquivo / extensões primeiro
    out.sort(key=lambda u: 0 if FILE_HOST_RE.match(u) else (1 if classify(u) in ("patreon", "tsr", "curseforge") else 2))
    return out


def gdrive_download(url, dest_dir):
    m = re.search(r"/d/([A-Za-z0-9_-]{20,})", url) or re.search(r"[?&]id=([A-Za-z0-9_-]{20,})", url)
    if not m:
        if "/folders/" in url:
            raise RuntimeError("Google Drive: é uma PASTA – baixe manualmente")
        raise RuntimeError("Google Drive: id não encontrado")
    fid = m.group(1)
    last = None
    for u in (f"https://drive.usercontent.google.com/download?id={fid}&export=download&confirm=t",
              f"https://drive.google.com/uc?export=download&id={fid}&confirm=t"):
        try:
            return [stream_download(u, dest_dir, f"gdrive_{fid}.zip")]
        except Exception as e:  # noqa
            last = e
    raise RuntimeError(f"Google Drive: {last}")


def simfileshare_download(url, dest_dir):
    m = re.search(r"simfileshare\.net/download/(\d+)", url)
    if not m:
        m = re.search(r"simfileshare\.net/folder/(\d+)", url)
        if m:
            raise RuntimeError("SimFileShare: é uma PASTA – baixe manualmente")
        raise RuntimeError("SimFileShare: id não encontrado")
    sid = m.group(1)
    s = new_session()
    page = f"https://simfileshare.net/download/{sid}/"
    try:
        s.get(page, timeout=90)
    except Exception:  # noqa
        pass
    return [stream_download(f"https://simfileshare.net/download/{sid}/?dl", dest_dir, f"sfs_{sid}.zip",
                            session=s, headers={"Referer": page})]


def mediafire_download(url, dest_dir):
    s = new_session()
    r = s.get(url, timeout=90)
    m = re.search(r'href="(https?://download[^"]+)"[^>]*id="downloadButton"', r.text) or \
        re.search(r'id="downloadButton"[^>]*href="(https?://download[^"]+)"', r.text) or \
        re.search(r'(https?://download\d+\.mediafire\.com/[^"\']+)', r.text)
    if not m:
        raise RuntimeError("MediaFire: botão de download não encontrado")
    return [stream_download(html.unescape(m.group(1)), dest_dir, "mediafire.zip", session=s)]


def classify(u):
    low = u.lower()
    if "thesimsresource.com" in low:
        return "tsr"
    if "curseforge.com/sims4/" in low:
        return "curseforge"
    if "patreon.com" in low:
        if re.search(r"patreon\.com/(?:[^/]+/)?posts/", low):
            return "patreon"
        if "patreon.com/file?" in low:
            return "other"
        return "skip"          # página de criador
    if "curseforge.com/members" in low or "media.forgecdn.net" in low or low.startswith("mailto:"):
        return "skip"
    return "other"


def download_by_url(url, dest_dir, depth=0):
    """Baixa a partir de qualquer URL conhecida. Retorna lista de Paths ou levanta exceção."""
    u = unwrap_redirect(url)
    low = u.lower()
    kind = classify(u)
    if kind == "skip":
        raise RuntimeError("link não é de arquivo")
    if kind == "curseforge":
        m = re.search(r"curseforge\.com/sims4/([^/?#]+/[^/?#]+)", u)
        if not m:
            raise RuntimeError("URL CurseForge não reconhecida")
        return cf_project_download(m.group(1), dest_dir)
    if kind == "tsr":
        m = re.search(r"/id/(\d+)", u) or re.search(r"/itemId/(\d+)", u) or re.search(r"/downloads/(\d+)", u)
        if not m:
            raise RuntimeError("TSR: id não encontrado na URL")
        return tsr_download(int(m.group(1)), dest_dir)
    if kind == "patreon":
        if depth >= 2:
            raise RuntimeError("profundidade máxima")
        m = re.search(r"patreon\.com/(?:[^/]+/)?posts/(?:[^/?#]*?-)?(\d+)(?=[/?#]|$)", u)
        if not m:
            raise RuntimeError("Patreon: id do post não encontrado")
        return patreon_download(m.group(1), dest_dir, depth)
    if "drive.google.com" in low or "docs.google.com" in low:
        return gdrive_download(u, dest_dir)
    if "simfileshare.net" in low:
        return simfileshare_download(u, dest_dir)
    if "dropbox.com" in low:
        u2 = re.sub(r"([?&])dl=0", r"\1dl=1", u)
        if "dl=1" not in u2:
            u2 += ("&" if "?" in u2 else "?") + "dl=1"
        return [stream_download(u2, dest_dir, "dropbox.zip")]
    if "mediafire.com" in low:
        return mediafire_download(u, dest_dir)
    if "mega.nz" in low or "mega.co.nz" in low:
        raise RuntimeError("MEGA exige cliente próprio – baixe manualmente")
    if "patreon.com/file?" in low or re.search(r"\.(zip|rar|7z|package)(\?|$)", low) or "patreonusercontent" in low:
        return [stream_download(u, dest_dir, u.split("?")[0].rsplit("/", 1)[-1] or "arquivo.zip")]
    if "modthesims.info" in low:
        s = new_session()
        r = s.get(u, timeout=90)
        ids = list(dict.fromkeys(re.findall(r"getfile\.php\?file=(\d+)", r.text)))
        got = []
        for gid in ids:
            try:
                got.append(stream_download(f"https://modthesims.info/getfile.php?file={gid}", dest_dir,
                                           f"mts_{gid}.zip", session=s, headers={"Referer": u}))
            except Exception as e:  # noqa
                log(f"    MTS getfile {gid}: {e}")
        if got:
            return got
        raise RuntimeError("ModTheSims: nenhum arquivo encontrado")
    if depth >= 2:
        raise RuntimeError("página sem link de arquivo reconhecível")
    # página genérica (tumblr, blog, site do criador, simsfinds...): procura links
    s = new_session()
    r = s.get(u, timeout=90)
    log(f"    página genérica {r.status_code} ({len(r.text)} bytes) {u}")
    if r.status_code >= 400:
        raise RuntimeError(f"HTTP {r.status_code}")
    links = extract_links(r.text, base_url=u)
    errs = []
    for l in links[:15]:
        if l.split("#")[0] == u.split("#")[0]:
            continue
        try:
            got = download_by_url(l, dest_dir, depth + 1)
            if got:
                return got
        except PaywallError:
            raise
        except Exception as e:  # noqa
            errs.append(f"{l[:90]}: {str(e)[:80]}")
    raise RuntimeError("nenhum link baixável na página" + (f" ({' | '.join(errs[:4])})" if errs else ""))


# --------------------------------------------------------------------------- descrição -> lista de CC
A_RE = re.compile(r"<a\b[^>]*href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>", re.I | re.S)


def cc_items_from_description(desc_html):
    items, seen = [], set()
    for m in A_RE.finditer(desc_html or ""):
        url = unwrap_redirect(m.group(1))
        label = safe_name(re.sub(r"<[^>]+>", "", m.group(2)), 120)
        kind = classify(url)
        if kind == "skip" or not label:
            continue
        if "gshade" in url.lower() or "gshade" in label.lower() or "reshade" in label.lower():
            kind = "optional"
        key = url
        if key in seen:
            continue
        seen.add(key)
        items.append({"label": label, "url": url, "kind": kind})
    return items


def get_sim_info(sim):
    info = {"project_id": None, "file_id": sim["file_id"], "file_name": sim["file_name"], "description": ""}
    try:
        data = cfwidget(f"sims4/sims-households/{sim['slug']}")
        info["project_id"] = data.get("id")
        d = data.get("download") or (data.get("files") or [None])[-1]
        if d:
            info["file_id"], info["file_name"] = d["id"], d["name"]
        info["description"] = data.get("description") or ""
        info["title"] = data.get("title")
    except Exception as e:  # noqa
        log(f"  cfwidget falhou ({e}); tentando página do CurseForge")
        try:
            r = new_session().get(f"https://www.curseforge.com/sims4/sims-households/{sim['slug']}", timeout=90)
            log(f"  página CurseForge {r.status_code}")
            info["description"] = r.text
        except Exception as e2:  # noqa
            log(f"  página CurseForge falhou: {e2}")
    return info


# --------------------------------------------------------------------------- extração / organização
def run_7z(archive, outdir):
    outdir.mkdir(parents=True, exist_ok=True)
    for exe in ("7z", "7zz", "7za"):
        if shutil.which(exe):
            p = subprocess.run([exe, "x", "-y", f"-o{outdir}", str(archive)], capture_output=True, text=True)
            if p.returncode == 0:
                return True
            log(f"    {exe} falhou ({p.returncode}): {p.stderr[-200:]}")
    if shutil.which("unrar"):
        p = subprocess.run(["unrar", "x", "-y", str(archive), str(outdir) + "/"], capture_output=True, text=True)
        return p.returncode == 0
    return False


def extract_archive(archive, outdir, depth=0):
    outdir.mkdir(parents=True, exist_ok=True)
    ok = False
    head = open(archive, "rb").read(4)
    if head == b"PK\x03\x04":
        try:
            with zipfile.ZipFile(archive) as z:
                z.extractall(outdir)
            ok = True
        except Exception as e:  # noqa
            log(f"    zipfile falhou ({e}); tentando 7z")
    if not ok:
        ok = run_7z(archive, outdir)
    if not ok:
        return False
    if depth < 3:
        for p in list(outdir.rglob("*")):
            if p.is_file() and (p.suffix.lower() in ARCHIVE_EXT or open(p, "rb").read(4) in (b"PK\x03\x04", b"Rar!")):
                if p.suffix.lower() in MOD_EXT:
                    continue
                sub = p.parent / (p.stem + "_extraido")
                if extract_archive(p, sub, depth + 1):
                    p.unlink(missing_ok=True)
    return True


def collect_files(src_dir):
    mods, tray = [], []
    for p in src_dir.rglob("*"):
        if not p.is_file() or "__MACOSX" in p.parts or p.name.startswith("._"):
            continue
        ext = p.suffix.lower()
        if ext in MOD_EXT:
            mods.append(p)
        elif ext in TRAY_EXT:
            tray.append(p)
    return mods, tray


def copy_unique(src, dest_dir):
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / src.name
    if dest.exists():
        if dest.stat().st_size == src.stat().st_size:
            return dest
        i = 1
        while dest.exists():
            dest = dest_dir / f"{src.stem}_{i}{src.suffix}"
            i += 1
    shutil.copy2(src, dest)
    return dest


def place_files(downloaded, folder_name):
    """Extrai e coloca .package em Mods/<folder>/ e arquivos de tray em Tray/."""
    placed = {"mods": [], "tray": [], "outros": []}
    for f in downloaded:
        ext = f.suffix.lower()
        head = open(f, "rb").read(4)
        if ext in MOD_EXT or head == b"DBPF":
            d = copy_unique(f, BUNDLE / "Mods" / folder_name)
            placed["mods"].append(str(d.relative_to(BUNDLE)))
        elif ext in TRAY_EXT:
            d = copy_unique(f, BUNDLE / "Tray")
            placed["tray"].append(str(d.relative_to(BUNDLE)))
        elif ext in ARCHIVE_EXT or head in (b"PK\x03\x04", b"Rar!") or head.startswith(b"7z"):
            tmp = EXTR / safe_name(folder_name + "_" + f.stem, 90)
            if tmp.exists():
                shutil.rmtree(tmp)
            if not extract_archive(f, tmp):
                log(f"    não consegui extrair {f.name}")
                d = copy_unique(f, BUNDLE / "_nao_extraidos" / folder_name)
                placed["outros"].append(str(d.relative_to(BUNDLE)))
                continue
            mods, tray = collect_files(tmp)
            for m in mods:
                rel = m.relative_to(tmp)
                # ignora pastas do tipo "xxx_extraido" no caminho para não ficar feio
                parts = [p for p in rel.parts[:-1] if not p.endswith("_extraido")]
                sub = BUNDLE / "Mods" / folder_name
                for p in parts:
                    sub = sub / p
                d = copy_unique(m, sub)
                placed["mods"].append(str(d.relative_to(BUNDLE)))
            for t in tray:
                d = copy_unique(t, BUNDLE / "Tray")
                placed["tray"].append(str(d.relative_to(BUNDLE)))
            if not mods and not tray:
                d = copy_unique(f, BUNDLE / "_nao_extraidos" / folder_name)
                placed["outros"].append(str(d.relative_to(BUNDLE)))
            shutil.rmtree(tmp, ignore_errors=True)
        else:
            d = copy_unique(f, BUNDLE / "_nao_extraidos" / folder_name)
            placed["outros"].append(str(d.relative_to(BUNDLE)))
    return placed


# --------------------------------------------------------------------------- principal
def download_cc(item):
    """Baixa um CC único. Retorna dict de resultado (nunca levanta)."""
    url, kind, label = item["url"], item["kind"], item["label"]
    folder = safe_name(label, 70)
    dest = ORIG / "CC" / folder
    res = {"nome": label, "fonte": kind, "url": url, "pasta": folder, "status": "falhou",
           "arquivos": [], "detalhe": None, "usado_por": item["usado_por"], "_paths": []}
    log(f"  >> [{kind}] {label}  <{url}>")
    try:
        if kind == "optional":
            raise SkipItem("preset gráfico (GShade/ReShade) – não é CC do jogo; opcional")
        files = download_by_url(url, dest)
        res.update({"status": "ok", "arquivos": [f.name for f in files],
                    "tamanho": sum(f.stat().st_size for f in files), "_paths": files})
    except PaywallError as e:
        res.update({"status": "pago/assinantes", "detalhe": str(e)})
        log(f"    PAGO: {label}: {e}")
    except SkipItem as e:
        res.update({"status": "opcional (não baixado)", "detalhe": str(e)})
    except Exception as e:  # noqa
        res.update({"status": "falhou", "detalhe": str(e)[:600]})
        log(f"    FALHOU: {label}: {str(e)[:300]}")
    return res


def main():
    if WORK.exists():
        shutil.rmtree(WORK)
    if OUT.exists():
        shutil.rmtree(OUT)
    if RELEASE.exists():
        shutil.rmtree(RELEASE)
    for d in (ORIG, EXTR, BUNDLE / "Mods", BUNDLE / "Tray", OUT, RELEASE):
        d.mkdir(parents=True, exist_ok=True)
    log(f"curl_cffi disponível: {HAVE_CFFI}")

    report = {"gerado_em": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
              "fonte": "https://www.curseforge.com/sims4/search?class=sims-households&page=1&pageSize=20&sortBy=creation+date",
              "sims": [], "cc_unicos": {}}
    unique = {}   # url -> item (com usado_por)

    # 1) sims + listas de CC
    for sim in SIMS:
        log(f"=== SIM {sim['n']}/5: {sim['name']} ({sim['author']}) ===")
        entry = {"n": sim["n"], "nome": sim["name"], "autor": sim["author"],
                 "pagina": f"https://www.curseforge.com/sims4/sims-households/{sim['slug']}",
                 "arquivo_sim": None, "status_sim": None, "cc_urls": []}
        info = get_sim_info(sim)
        sim_dir = ORIG / f"{sim['n']:02d} - {safe_name(sim['name'])}"
        try:
            f = cf_download_file(info["file_id"], info["file_name"], sim_dir, info.get("project_id"))
            placed = place_files([f], f"_sim_{sim['n']:02d}")
            entry.update({"arquivo_sim": f.name, "tamanho_sim": f.stat().st_size, "status_sim": "ok",
                          "tray": placed["tray"], "mods_incluidos_no_sim": placed["mods"]})
        except Exception as e:  # noqa
            log(f"  FALHA ao baixar o sim: {e}")
            entry["status_sim"] = f"falhou: {e}"
        items = cc_items_from_description(info["description"])
        log(f"  {len(items)} links de CC na descrição")
        for it in items:
            entry["cc_urls"].append(it["url"])
            if it["url"] not in unique:
                unique[it["url"]] = dict(it, usado_por=[])
            if sim["name"] not in unique[it["url"]]["usado_por"]:
                unique[it["url"]]["usado_por"].append(sim["name"])
        report["sims"].append(entry)

    # 2) download paralelo dos CCs únicos
    log(f"=== {len(unique)} CCs únicos para baixar ===")
    results = {}
    with cf.ThreadPoolExecutor(max_workers=4) as ex:
        futs = {ex.submit(download_cc, it): url for url, it in unique.items()}
        for fut in cf.as_completed(futs):
            url = futs[fut]
            try:
                results[url] = fut.result()
            except Exception as e:  # noqa
                results[url] = {"nome": unique[url]["label"], "fonte": unique[url]["kind"], "url": url,
                                "status": "falhou", "detalhe": f"erro interno: {e}", "arquivos": [],
                                "usado_por": unique[url]["usado_por"], "_paths": []}

    # 3) organização (sequencial)
    log("=== Organizando pacote ===")
    for url, it in unique.items():
        res = results[url]
        if res["_paths"]:
            placed = place_files(res["_paths"], res["pasta"])
            res.update({"mods": placed["mods"], "tray": placed["tray"], "outros": placed["outros"]})
            if not placed["mods"] and not placed["tray"]:
                res["detalhe"] = "baixado, mas nenhum .package reconhecido (veja _nao_extraidos)"
        res.pop("_paths", None)
        report["cc_unicos"][url] = res

    for s in report["sims"]:
        s["cc"] = []
        for url in s.pop("cc_urls"):
            r = report["cc_unicos"][url]
            s["cc"].append({k: r.get(k) for k in ("nome", "fonte", "url", "status", "arquivos", "detalhe")})

    cache = report["cc_unicos"]
    tot = len(cache)
    ok = sum(1 for c in cache.values() if c["status"] == "ok")
    pago = sum(1 for c in cache.values() if c["status"].startswith("pago"))
    falh = sum(1 for c in cache.values() if c["status"] == "falhou")
    report["resumo"] = {"cc_unicos": tot, "ok": ok, "pago_assinantes": pago, "falhou": falh,
                        "opcional": tot - ok - pago - falh,
                        "sims_ok": sum(1 for s in report["sims"] if s["status_sim"] == "ok")}
    log(f"=== RESUMO: {ok}/{tot} CCs baixados; {pago} exclusivos de assinantes; {falh} falharam ===")

    write_reports(report)
    make_bundle(report)


def write_reports(report):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "relatorio.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md = []
    r = report["resumo"]
    md.append("# The Sims 4 – 5 sims mais recentes do CurseForge + todos os CCs\n")
    md.append(f"Gerado em {report['gerado_em']} a partir de <{report['fonte']}>\n")
    md.append(f"**Resumo:** {r['sims_ok']}/5 sims baixados · **{r['ok']}/{r['cc_unicos']} CCs únicos baixados** · "
              f"{r['pago_assinantes']} exclusivos de assinantes (Patreon pago / TSR VIP) · {r['falhou']} falharam · "
              f"{r['opcional']} opcionais\n")
    md.append("## Como instalar\n")
    md.append("1. Extraia `TUDO_JUNTO_Sims4.zip` (ou todas as partes `TUDO_JUNTO_Sims4_parteNN.zip` na mesma pasta).\n"
              "2. Copie o conteúdo de `Tray/` para `Documentos\\Electronic Arts\\The Sims 4\\Tray`.\n"
              "3. Copie o conteúdo de `Mods/` para `Documentos\\Electronic Arts\\The Sims 4\\Mods`.\n"
              "4. No jogo: Opções > Outros > ative *Conteúdo personalizado e mods* e reinicie. "
              "Os sims aparecem na Galeria > *Minha Biblioteca* (marque *Incluir conteúdo personalizado*).\n")
    for s in report["sims"]:
        md.append(f"\n## {s['n']}. {s['nome']} — por {s['autor']}\n")
        md.append(f"Página: <{s['pagina']}>  \nArquivo do sim: `{s.get('arquivo_sim')}` — status: **{s['status_sim']}**  \n"
                  f"Tray: {', '.join(s.get('tray') or []) or '—'}\n")
        okc = sum(1 for c in s["cc"] if c["status"] == "ok")
        md.append(f"\nCC necessário: {okc}/{len(s['cc'])} baixados\n")
        md.append("| # | CC | Fonte | Status | Arquivo(s) |\n|---|----|-------|--------|-----------|")
        for i, c in enumerate(s["cc"], 1):
            arqs = ", ".join(c.get("arquivos") or []) or "—"
            det = f" – {c['detalhe']}" if c.get("detalhe") and c.get("status") != "ok" else ""
            md.append(f"| {i} | [{c['nome']}]({c['url']}) | {c['fonte']} | {c['status']}{det} | {arqs} |")
    md.append("\n## CCs que NÃO puderam ser baixados automaticamente\n")
    miss = [c for c in report["cc_unicos"].values() if c["status"] != "ok"]
    if not miss:
        md.append("Nenhum – tudo foi baixado.\n")
    for c in miss:
        md.append(f"- **{c['nome']}** — {c['status']} — <{c['url']}>  \n  usado por: {', '.join(c['usado_por'])}"
                  + (f"  \n  motivo: {c['detalhe']}" if c.get("detalhe") else ""))
    (OUT / "relatorio.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    (OUT / "log.txt").write_text("\n".join(LOG_LINES), encoding="utf-8")


def make_bundle(report):
    r = report["resumo"]
    leia = ["TUDO JUNTO – The Sims 4: 5 sims mais recentes do CurseForge + CCs necessários", "",
            f"Gerado em {report['gerado_em']}", "",
            "COMO INSTALAR",
            "1) Copie TODO o conteúdo da pasta Tray/ para: Documentos\\Electronic Arts\\The Sims 4\\Tray",
            "2) Copie TODO o conteúdo da pasta Mods/ para: Documentos\\Electronic Arts\\The Sims 4\\Mods",
            "3) Abra o jogo > Opções > Outros > marque 'Ativar conteúdo personalizado e mods' e reinicie.",
            "4) Galeria > Minha Biblioteca (marque 'Incluir conteúdo personalizado') e procure pelo nome do sim.", "",
            "SIMS INCLUÍDOS"]
    for s in report["sims"]:
        leia.append(f"  {s['n']}. {s['nome']} (por {s['autor']}) – {s['status_sim']} – {s['pagina']}")
    leia += ["", f"CCs: {r['ok']}/{r['cc_unicos']} baixados. {r['pago_assinantes']} são exclusivos de assinantes "
             f"(Patreon pago / TSR VIP) e {r['falhou']} falharam – veja relatorio.md para os links e baixe manualmente.", "",
             "Os .package ficam em Mods/<nome do CC>/ – o jogo lê subpastas normalmente (até 5 níveis).",
             "Pasta _nao_extraidos/ (se existir) = arquivos que não pude abrir automaticamente; extraia à mão.", ""]
    (BUNDLE / "LEIA-ME.txt").write_text("\n".join(leia), encoding="utf-8")
    shutil.copy2(OUT / "relatorio.md", BUNDLE / "relatorio.md")

    files = [p for p in sorted(BUNDLE.rglob("*")) if p.is_file()]
    total = sum(p.stat().st_size for p in files)
    log(f"Conteúdo do pacote: {len(files)} arquivos, {human(total)} sem compressão")

    full = RELEASE / "TUDO_JUNTO_Sims4.zip"
    with zipfile.ZipFile(full, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for p in files:
            z.write(p, p.relative_to(BUNDLE.parent))
    size = full.stat().st_size
    log(f"Pacote final: {full.name} ({human(size)})")

    limit_commit = 95 * 1024 * 1024
    part_limit = 85 * 1024 * 1024
    info_lines = [f"TUDO_JUNTO_Sims4.zip = {size} bytes ({human(size)})"]
    if size <= limit_commit:
        shutil.copy2(full, OUT / "TUDO_JUNTO_Sims4.zip")
    else:
        parts_dir = OUT / "partes"
        parts_dir.mkdir()
        # primeiro LEIA-ME/relatorio/Tray, depois Mods; cada parte extrai sozinha
        files.sort(key=lambda p: (0 if (p.name in ("LEIA-ME.txt", "relatorio.md") or "Tray" in p.parts) else 1, str(p)))
        part, cur, n = None, 0, 0
        for p in files:
            sz = p.stat().st_size
            if part is None or (cur + sz > part_limit and cur > 0):
                if part:
                    part.close()
                n += 1
                part = zipfile.ZipFile(parts_dir / f"TUDO_JUNTO_Sims4_parte{n:02d}.zip", "w",
                                       zipfile.ZIP_DEFLATED, compresslevel=6)
                cur = 0
            part.write(p, p.relative_to(BUNDLE.parent))
            cur += sz
        if part:
            part.close()
        for p in sorted(parts_dir.iterdir()):
            info_lines.append(f"partes/{p.name} = {p.stat().st_size} bytes ({human(p.stat().st_size)})")
        log(f"Pacote dividido em {n} partes em {parts_dir} (cada parte extrai sozinha)")
    (OUT / "TAMANHO.txt").write_text("\n".join(info_lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / "log.txt").write_text("\n".join(LOG_LINES) + "\n" + traceback.format_exc(), encoding="utf-8")
        sys.exit(1)
