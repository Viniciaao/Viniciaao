#!/usr/bin/env python3
"""Teste offline do download.py usando as páginas salvas pela sonda (probe/out) como respostas falsas.
Roda no sandbox (sem rede): python3 sims4-bundle/probe/test_offline.py"""
import json
import pathlib
import re
import shutil
import sys
import tempfile
import urllib.parse

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))
import download as D  # noqa: E402

OUT = HERE / "out"
DBPF = b"DBPF\x02\x00\x00\x00\x01\x00\x00\x00" + b"\x00" * 400
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 400
ZIP_ENC = None
CALLS = []


class FakeResp:
    def __init__(self, url, body=b"", ct="text/html; charset=utf-8", status=200, name=None):
        self.url = url
        self.status_code = status
        self.headers = {"Content-Type": ct}
        if name:
            self.headers["Content-Disposition"] = f'attachment; filename="{name}"'
        self._body = body

    @property
    def text(self):
        return self._body.decode("utf-8", "replace")

    def json(self):
        return json.loads(self._body)

    def iter_content(self, chunk_size=65536):
        for i in range(0, len(self._body), chunk_size):
            yield self._body[i:i + chunk_size]

    def close(self):
        pass


def sfs_page(sid):
    names = {"2676307": "MB_Default_chin_slider_Fixed.package", "2759281": "MB_Default_mouth_slider.package",
             "2716250": "MB_Default_nose_slider_Fixed.package", "5216750": "GPME-GOLD Eyeshadow CC 47.package",
             "508140": "GPME-GOLD High Glossy Eyes.package", "5238413": "[VICE4Simz] - Rick Owens.package",
             "4893177": "[Kijiko]eyelash_Makeup_Uncurled.zip"}
    n = names.get(sid, f"file_{sid}.package")
    return (f'<html><h3>{n} (3.8 MB)</h3><a href="https://cdn.simfileshare.net/download/{sid}/?dl" '
            f'class="btn">Download</a></html>').encode()


def route(url):
    u = url
    p = urllib.parse.urlparse(u)
    host, path, q = p.netloc, p.path, urllib.parse.parse_qs(p.query)
    if host == "drive.google.com" and path == "/embeddedfolderview":
        fid = q["id"][0]
        if fid == "1bHnBzR6rKq_vs3CM6fcX_5YuCcMRIGwk":
            return FakeResp(u, (OUT / "gdrive_folder.html").read_bytes())
        if fid == "1zjDHSvtT2bh_kXIA2rgeXLPvW35J2ldE":      # pasta que só tem subpasta
            return FakeResp(u, b'<div class="flip-entry" id="entry-1LmNoYWy_B7b7mxlrLlMdyQidJHhLFSAd" tabindex="0">'
                               b'<a href="https://drive.google.com/drive/folders/1LmNoYWy_B7b7mxlrLlMdyQidJHhLFSAd">'
                               b'<div class="flip-entry-title">HIGHLIGHT COLLECTION</div></a></div>')
        if fid == "1LmNoYWy_B7b7mxlrLlMdyQidJHhLFSAd":
            return FakeResp(u, b'<div class="flip-entry" id="entry-1aof8rJxq2N742GncNXqi82L7UuiN5c5Q" tabindex="0">'
                               b'<a href="https://drive.google.com/file/d/1aof8rJxq2N742GncNXqi82L7UuiN5c5Q/view">'
                               b'<div class="flip-entry-title">sims3melancholic_highlight #23 MAXIS MATCH.package</div></a></div>'
                               b'<div class="flip-entry" id="entry-1YNZywjvC-2JEd3XGOg6z5dIpO7ks1oji" tabindex="0">'
                               b'<a href="https://drive.google.com/file/d/1YNZywjvC-2JEd3XGOg6z5dIpO7ks1oji/view">'
                               b'<div class="flip-entry-title">sims3melancholic_highlight #23-28 ALL IN 1.package</div></a></div>')
        return FakeResp(u, b"<html></html>")
    if host == "drive.usercontent.google.com":
        return FakeResp(u, DBPF, "application/octet-stream", name=f"gd_{q['id'][0]}.package")
    if host == "simfileshare.net" and path.startswith("/folder/"):
        fid = path.strip("/").split("/")[1]
        f = {"149886": "sfs_folder.html", "188255": "sfs_folder_kikiw.html"}.get(fid)
        if f:
            return FakeResp(u, (OUT / f).read_bytes())
        if fid == "54933":
            return FakeResp(u, b'<table><tr><td><a href="/download/4080450/">obscurus_hairline_N1sd.package</a></td></tr>'
                               b'<tr><td><a href="/download/4080449/">obscurus_hairline_N1t.package</a></td></tr>'
                               b'<tr><td><a href="/download/911599/">obscurus_eyebrows_14.package</a></td></tr></table>')
        return FakeResp(u, b"<html></html>", status=404)
    if host == "simfileshare.net" and path.startswith("/download/"):
        sid = path.strip("/").split("/")[1]
        if "dl" in q:
            return FakeResp(u, b"\n\n\n<!DOCTYPE html>\n<html>interstitial</html>")   # como na sonda
        return FakeResp(u, sfs_page(sid))
    if host == "cdn.simfileshare.net":
        sid = path.strip("/").split("/")[1]
        body = ZIP_OK if sid == "4893177" else DBPF
        return FakeResp(u, body, "application/octet-stream")
    if host.endswith("tistory.com"):
        if "nail" in path:
            return FakeResp(u, b'<a href="https://blog.kakaocdn.net/dna/x/y/euno%20nail%20set.zip?credential=1&attach=1&knm=tfile.zip">zip</a>')
        if "sunberry" in host:
            return FakeResp(u, b'<a href="https://blog.kakaocdn.net/dna/a/%5BSUNBERRY%5DHeart%20Fur%20Boots%2022.73.package?credential=1&attach=1">a</a>'
                               b'<a href="https://blog.kakaocdn.net/dna/b/%5BSUNBERRY%5DPuff%20setup%20mini%20dress%2022.73.package?credential=1&attach=1">b</a>')
        return FakeResp(u, (OUT / "tistory.html").read_bytes())
    if host == "blog.kakaocdn.net":
        if path.endswith(".zip"):
            return FakeResp(u, ZIP_ENC, "application/zip")
        return FakeResp(u, DBPF, "application/octet-stream")
    if host == "seoul-soul.com":
        return FakeResp(u, (OUT / "seoulsoul.html").read_bytes())
    if host == "www.mediafire.com":
        return FakeResp(u, (OUT / "mediafire.html").read_bytes())
    if "mediafire.com" in host:
        return FakeResp(u, DBPF, "application/octet-stream")
    if host == "www.patreon.com" and path.startswith("/api/posts/"):
        pid = path.rsplit("/", 1)[-1]
        if pid in ("64102874", "51786745"):
            return FakeResp(u, b'{"errors":[{"code":4,"title":"post was not found."}]}', "application/json", 404)
        data = json.loads((OUT / "patreon_api_157807075.json").read_text())
        data["data"]["id"] = pid
        return FakeResp(u, json.dumps(data).encode(), "application/vnd.api+json")
    if host == "c10.patreonusercontent.com":
        return FakeResp(u, PNG, "image/png")
    if host == "bit.ly":
        return FakeResp(u, b'<html><a href="https://drive.google.com/drive/u/1/folders/12AlqHAzsek4xQN75Eq14e0mVR-t9Y4Jh?utm_source=x">'
                           b'<span>Continue to destination</span></a></html>')
    if host == "api.cfwidget.com":
        return FakeResp(u, json.dumps({"id": 1402353, "download": {"id": 7320086, "name": "euno eye preset 11-15 [250801].zip"}}).encode(), "application/json")
    if "forgecdn.net" in host:
        return FakeResp(u, ZIP_OK, "application/zip", name="euno eye preset 11-15 [250801].zip")
    return FakeResp(u, b"<html>nada</html>", status=404)


class FakeSession:
    def __init__(self):
        self.headers = {}

    def get(self, url, **kw):
        CALLS.append(url)
        return route(url)


def make_zips(tmp):
    import zipfile
    import subprocess
    p = tmp / "ok.zip"
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("euno eye preset 11-15 [250801].package", DBPF)
    ok = p.read_bytes()
    enc = None
    inner = tmp / "euno 2022 0104 nail (Round shape) HQ.package"
    inner.write_bytes(DBPF)
    if shutil.which("7z") or shutil.which("7za") or shutil.which("zip"):
        pe = tmp / "enc.zip"
        if shutil.which("zip"):
            subprocess.run(["zip", "-q", "-P", "4yODA4MT", str(pe), inner.name], cwd=tmp, check=True)
        else:
            exe = shutil.which("7z") or shutil.which("7za")
            subprocess.run([exe, "a", "-tzip", "-p4yODA4MT", str(pe), inner.name], cwd=tmp, check=True, capture_output=True)
        enc = pe.read_bytes()
    return ok, enc


def main():
    global ZIP_OK, ZIP_ENC
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="s4test_"))
    ZIP_OK, ZIP_ENC = make_zips(tmp)
    D.new_session = lambda: FakeSession()
    D.WORK = tmp / "work"
    D.ORIG = D.WORK / "originais"
    D.EXTR = D.WORK / "extraido"
    D.BUNDLE = D.WORK / "TUDO"
    for d in (D.ORIG, D.EXTR, D.BUNDLE / "Mods", D.BUNDLE / "Tray"):
        d.mkdir(parents=True, exist_ok=True)

    cases = [
        # (label, url, esperado: lista de nomes de arquivo (substring) que devem aparecer)
        ("[SEOULSOUL] 2026_#164_Skirt", "https://www.patreon.com/seoulsoul/posts/ingame-ver-2026-157807075", ["2026_#164_Skirt.package"]),
        ("[SEOULSOUL] 2026_#164_Skirt (site)", "https://seoul-soul.com/5711-2/", ["2026_#164_Skirt.package"]),
        ("sims3melancholic_highlight #23-28 ALL IN 1", "https://drive.google.com/drive/folders/1zjDHSvtT2bh_kXIA2rgeXLPvW35J2ldE", ["ALL IN 1.package"]),
        ("obscurus_eyelids_N3test", "https://obscurus-sims.tumblr.com/post/168617117913/eyelids-n3-24-colors-teen-males-and-females", ["obscurus_eyelids_N3.package"]),
        ("[KIKIW]The perfect doll slider_eyes_Fixed", "https://www.tumblr.com/cocoona-sims/652805006498643968/kikiwthe-perfect-doll-slide-the-slider-can", ["slider_eyes.package"]),
        ("obscurus_hairline_N1sd", "https://www.patreon.com/obscurus_sims/posts/eyebrows-and-23816939", ["obscurus_hairline_N1sd.package"]),
        ("[MB] Default mouth slider", "https://www.patreon.com/magicbot/posts/default-mouth-56990147", ["MB_Default_mouth_slider.package"]),
        ("euno eye preset 1-5 [250220]", "https://www.patreon.com/eunosims/posts/preview-preset-123677619", ["euno eye preset 1-5 [250220].package"]),
        ("euno eye preset 11-15 [250801]", "https://www.patreon.com/eunosims/posts/preview-preset-139371473", ["euno eye preset 11-15 [250801].zip"]),
        ("[SUNBERRY]Heart Fur Boots 22.73", "https://www.patreon.com/posts/sunberry-puff-22-76138099", ["Heart Fur Boots 22.73.package"]),
        ("GPME-GOLD Eyeshadow CC 47", "https://www.patreon.com/goppolsme/posts/gpme-gold-cc-47-119339172", ["GPME-GOLD Eyeshadow CC 47.package"]),
        ("GPME-GOLD Eyeshadow CC 47 (mediafire)", "https://www.mediafire.com/file/9ox73a0npssvxtg/GPME-GOLD+Eyeshadow+CC+47.package/file", ["GPME-GOLD Eyeshadow CC 47.package"]),
        ("[Kijiko] via mediafire", "https://www.mediafire.com/file/ljlqincziwc65rn/%255BKijiko%255Deyelash_Makeup_Uncurled.zip/file", ["GPME-GOLD Eyeshadow CC 47.package"]),
        ("[poyopoyo] Eye Contacts N9", "https://bit.ly/3wPXOBr", None),   # pasta vazia no fake -> falha, só testa o encurtador
        ("[VICE4Simz] - Rick Owens", "https://www.patreon.com/posts/vice-2022-high-c-64102874", ["Rick Owens.package"]),
        ("[Kijiko]eyelash_YF_Mak_ex-natural_Ri", "https://kijiko-catfood.com/3d-lashes-uncurl-makeup/", ["Uncurled.zip"]),
        ("obscurus_nose_highlighter", "https://www.patreon.com/obscurus_sims/posts/maxis-match-set-78704428", "MANUAL"),
        ("astya96_vintage_summer_lila_top", "https://www.patreon.com/astya96/posts/vintage-summer-111339616", "MANUAL"),
        ("LamaLama_Acc_Hair Melyssa", "https://www.simsfinds.com/downloads/361654/melyssa-hair-by-lamalama-sims4", "MANUAL"),
        ("euno 2022 0104 nail (square shape) Solid HQ", "https://eunosims.tistory.com/entry/sims4cc-nail-set", ["euno nail set.zip"]),
    ]
    fails = 0
    for label, url, expect in cases:
        item = {"url": url, "kind": D.classify(url), "label": label, "aliases": [], "usado_por": ["x"]}
        res = D.download_cc(item)
        names = res["arquivos"]
        if expect == "MANUAL":
            ok = res["status"] == "falhou" and "manualmente" in (res["detalhe"] or "")
        elif expect is None:
            ok = res["status"] == "falhou" and any("bit.ly" in c for c in CALLS) and \
                any("embeddedfolderview?id=12AlqHAzsek4xQN75Eq14e0mVR-t9Y4Jh" in c for c in CALLS)
        else:
            ok = res["status"] == "ok" and all(any(e in n for n in names) for e in expect)
        if res["_paths"]:
            placed = D.place_files(res["_paths"], res["pasta"])
            res["mods"] = placed["mods"]
            if expect not in ("MANUAL", None) and not placed["mods"]:
                ok = False
        print(("OK  " if ok else "FAIL"), label, "->", res["status"], names, res.get("detalhe") or "", res.get("mods", ""),
              res.get("link_download", ""))
        fails += not ok

    # imagens de preview: post do Patreon sem alternativa conhecida -> falhou (não "ok")
    D.KNOWN_DIRECT.pop("157807075")
    item = {"url": "https://www.patreon.com/seoulsoul/posts/ingame-ver-2026-157807075", "kind": "patreon",
            "label": "[SEOULSOUL] 2026_#164_Skirt", "aliases": [], "usado_por": ["x"]}
    res = D.download_cc(item)
    ok = res["status"] == "falhou" and "preview" in res["detalhe"]
    print(("OK  " if ok else "FAIL"), "só preview ->", res["status"], res["detalhe"])
    fails += not ok

    # zip protegido sem senha conhecida -> PasswordError
    if ZIP_ENC:
        D.ZIP_PASSWORDS.clear()
        f = tmp / "outro set.zip"
        f.write_bytes(ZIP_ENC)
        placed = D.place_files([f], "outro")
        ok = bool(placed.get("senha")) and not placed["mods"]
        print(("OK  " if ok else "FAIL"), "zip com senha desconhecida ->", placed.get("senha"))
        fails += not ok

    print(f"\n{'TUDO OK' if not fails else str(fails) + ' FALHAS'}  (pacote de teste em {D.BUNDLE})")
    for p in sorted(D.BUNDLE.rglob("*")):
        if p.is_file():
            print("   ", p.relative_to(D.BUNDLE))
    return fails


if __name__ == "__main__":
    sys.exit(1 if main() else 0)
