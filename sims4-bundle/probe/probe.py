#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Sonda rápida (roda no GitHub Actions): salva HTML/respostas de alguns hosts para
desenvolver o parser offline. Saída em sims4-bundle/probe/out/."""
import json
import pathlib
import re
import time
import urllib.parse

from curl_cffi import requests as creq
import requests as preq

OUT = pathlib.Path(__file__).resolve().parent / "out"
OUT.mkdir(parents=True, exist_ok=True)
LOG = []


def log(m):
    print(m, flush=True)
    LOG.append(m)


def sess():
    s = creq.Session(impersonate="chrome", timeout=60)
    s.headers.update({"Accept-Language": "en-US,en;q=0.9"})
    return s


def save(name, data):
    p = OUT / name
    if isinstance(data, str):
        data = data.encode("utf-8", "replace")
    full = len(data)
    if name.endswith(".bin"):
        data = data[:64]
    else:
        data = data[:600_000]
    p.write_bytes(data)
    log(f"  salvo {name} ({len(data)} de {full} bytes)")
    if not name.endswith(".bin"):
        txt = data.decode("utf-8", "replace")
        for pat in ("seoul-soul.com", "simfileshare.net/download", "drive.google.com", "__NEXT_DATA__",
                    "patreon.bootstrap", '"content":', "download_url", "mediafire.com/file", "kakaocdn.net",
                    "data-scrambled-url", "downloadButton", "/file/d/", "flip-entry", "mega.nz"):
            n = txt.count(pat)
            if n:
                i = txt.find(pat)
                log(f"    '{pat}' x{n}  ex: {txt[max(0,i-120):i+160]!r}")


def get(s, url, name=None, headers=None, stream_head=False, **kw):
    t0 = time.time()
    try:
        r = s.get(url, headers=headers or {}, allow_redirects=True, **kw)
        ct = r.headers.get("content-type", "")
        body = r.content
        log(f"GET {url}\n  -> {r.status_code} {ct} {len(body)} bytes em {time.time()-t0:.1f}s final={r.url}")
        log(f"  head={body[:24]!r}")
        if name:
            save(name, body)
        return r
    except Exception as e:  # noqa
        log(f"GET {url}\n  -> ERRO {type(e).__name__}: {e}")
        return None


def main():
    s = sess()

    # 1) Patreon: página HTML do post (image_file) e API com campos do web client
    for pid in ("157807075", "54872952", "119339172"):
        get(s, f"https://www.patreon.com/posts/{pid}", f"patreon_{pid}.html")
    fields = ("change_visibility_at,comment_count,content,created_at,current_user_can_view,embed,image,"
              "is_paid,like_count,post_file,post_metadata,published_at,patreon_url,post_type,teaser_text,title,url")
    api = ("https://www.patreon.com/api/posts/157807075?include=attachments_media,media,attachments,campaign"
           f"&fields[post]={fields}&fields[media]=id,download_url,file_name,image_urls,mimetype,size_bytes"
           "&json-api-version=1.0&json-api-use-default-includes=false")
    get(s, api, "patreon_api_157807075.json", headers={"Accept": "application/json",
                                                      "Referer": "https://www.patreon.com/posts/157807075"})

    # 2) Google Drive: listagem de pasta pública + download direto de um arquivo
    get(s, "https://drive.google.com/embeddedfolderview?id=1bHnBzR6rKq_vs3CM6fcX_5YuCcMRIGwk", "gdrive_folder.html")
    get(s, "https://drive.google.com/drive/folders/1bHnBzR6rKq_vs3CM6fcX_5YuCcMRIGwk", "gdrive_folder_full.html")
    get(s, "https://drive.usercontent.google.com/download?id=14FF7u81DPpITQtsfKDAo5ROJM4b0Vm7b&export=download&confirm=t",
        "gdrive_file.bin")

    # 3) SimFileShare: pasta e download
    get(s, "https://simfileshare.net/folder/149886/", "sfs_folder.html")
    get(s, "https://simfileshare.net/download/2803274/?dl", "sfs_file.bin", headers={"Referer": "https://simfileshare.net/download/2803274/"})

    # 4) tistory / kakaocdn
    r = get(s, "https://eunosims.tistory.com/entry/sims4-eye-preset-download", "tistory.html")
    if r is not None:
        m = re.search(r'href="(https://blog\.kakaocdn\.net/[^"]+\.package[^"]*)"', r.text)
        if m:
            import html as h
            get(s, h.unescape(m.group(1)), "kakao_file.bin", headers={"Referer": "https://eunosims.tistory.com/"})
        else:
            log("  kakaocdn link não encontrado no HTML")

    # 5) seoul-soul.com
    get(s, "https://seoul-soul.com/5711-2/", "seoulsoul.html")

    # 6) kijiko com curl_cffi e com requests puro
    get(s, "https://kijiko-catfood.com/3d-lashes-uncurl-makeup/", "kijiko_cffi.html", timeout=60)
    try:
        t0 = time.time()
        r = preq.get("https://kijiko-catfood.com/3d-lashes-uncurl-makeup/", timeout=60,
                     headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/128.0 Safari/537.36"})
        log(f"requests kijiko -> {r.status_code} {len(r.content)} bytes em {time.time()-t0:.1f}s")
        save("kijiko_requests.html", r.content)
    except Exception as e:  # noqa
        log(f"requests kijiko -> ERRO {e}")

    # 7) bit.ly redirect
    try:
        r = s.get("https://bit.ly/3wPXOBr", allow_redirects=False)
        log(f"bit.ly -> {r.status_code} Location={r.headers.get('location')}")
    except Exception as e:  # noqa
        log(f"bit.ly -> ERRO {e}")

    # 8) mediafire
    get(s, "https://www.mediafire.com/file/9ox73a0npssvxtg/GPME-GOLD+Eyeshadow+CC+47.package/file", "mediafire.html")

    # 9) modcollective
    get(s, "https://www.modcollective.gg/sims4/details/collection/298", "modcollective.html")

    # 10) tumblr (KIKIW) e simsfinds
    get(s, "https://simfileshare.net/folder/188255/", "sfs_folder_kikiw.html")

    (OUT / "probe_log.txt").write_text("\n".join(LOG), encoding="utf-8")


if __name__ == "__main__":
    main()
