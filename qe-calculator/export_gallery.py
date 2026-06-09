#!/usr/bin/env python3
"""
QE 結果 → 発表クオリティ図 + 出力ファイル → サイト (gallery.html) 用エクスポート

lab-ubuntu(AiiDAlab / AiiDA + qe-auto)で実行する。完了した計算ノード(PK)から
  - matplotlib で発表クオリティの図 (バンド / DOS・PDOS / 電荷移動 Δρ / 磁気) を PNG+SVG+PDF 生成
  - 主要な出力ファイル (pw.out, *.xml, structure.cif など) を収集
  - これらを research-tools/qe-calculator/data/<id>/ に配置し、data/gallery.json を生成
し、git push すれば公開サイトの gallery.html に発表クオリティで並ぶ。

使い方:
  # 指定 PK を書き出し
  python3 export_gallery.py --pk 1110 --id vse2_emim --title "VSe2 + EMIm+"
  # 完了済み QeFullWorkChain を全部
  python3 export_gallery.py --all-finished
  # 書き出し後そのまま commit & push
  python3 export_gallery.py --all-finished --git-push

依存: aiida-core (lab-ubuntu に導入済), matplotlib, numpy
      (無ければ: pip install matplotlib numpy)

※ ノードの取り出し方 (outputs 名など) は AiiDAlab QE app / qe-auto の WorkChain 構成に
   合わせて FETCHERS の TODO 部分を調整すること。基本は標準の aiida-quantumespresso 準拠。
"""
import os, sys, json, shutil, argparse, datetime, subprocess

# ---- publication-quality matplotlib スタイル ----
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
plt.rcParams.update({
    "figure.dpi": 120, "savefig.dpi": 300, "font.size": 11,
    "font.family": "sans-serif", "axes.linewidth": 1.0,
    "axes.labelsize": 12, "legend.frameon": False,
    "xtick.direction": "in", "ytick.direction": "in",
    "xtick.top": True, "ytick.right": True, "figure.autolayout": True,
})

from aiida import load_profile
from aiida.orm import load_node
load_profile()

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(HERE, "data")
FIG_FORMATS = ["png", "svg", "pdf"]


def savefig(fig, outdir, key):
    """PNG/SVG/PDF で保存し、gallery.json 用の相対パス dict を返す。"""
    rel = {}
    for fmt in FIG_FORMATS:
        fn = f"{key}.{fmt}"
        fig.savefig(os.path.join(outdir, fn), bbox_inches="tight", transparent=False)
        rel[fmt] = os.path.relpath(os.path.join(outdir, fn), DATA_DIR)
    plt.close(fig)
    return rel


# ===== 図ジェネレータ（標準 aiida-quantumespresso 準拠。系に合わせ調整可） =====
def plot_bands(wc, outdir):
    bands = wc.outputs.band_structure  # PwBandsWorkChain の出力 (BandsData)
    arr = bands.get_bands()            # (nkpt, nband) または (2, nkpt, nband)=spin
    try:    fermi = wc.outputs.band_parameters["fermi_energy"]
    except Exception: fermi = 0.0
    labels = dict(bands.labels) if bands.labels else {}
    x = np.arange(arr.shape[-2])
    fig, ax = plt.subplots(figsize=(5.0, 4.2))
    def draw(b2d, **kw):
        for ib in range(b2d.shape[1]):
            ax.plot(x, b2d[:, ib] - fermi, lw=0.9, **kw)
    if arr.ndim == 3:  # spin-polarized
        draw(arr[0], color="#d62728"); draw(arr[1], color="#1f77b4")
        ax.plot([], [], color="#d62728", label="up"); ax.plot([], [], color="#1f77b4", label="down"); ax.legend()
    else:
        draw(arr, color="#222")
    ax.axhline(0, color="#888", ls="--", lw=0.8)
    for pos, lab in labels.items():
        ax.axvline(pos, color="#bbb", lw=0.6)
    if labels:
        ax.set_xticks(list(labels.keys())); ax.set_xticklabels([l.replace("GAMMA", "Γ") for l in labels.values()])
    ax.set_ylabel(r"$E - E_\mathrm{F}$ (eV)"); ax.set_xlim(x.min(), x.max()); ax.set_ylim(-4, 4)
    ax.set_title("Band structure")
    return savefig(fig, outdir, "bands"), "バンド構造（E−E_F 基準、破線=フェルミ準位）"


def plot_dos(wc, outdir):
    dos = wc.outputs.dos.output_dos  # PdosWorkChain (XyData): energy + dos
    E = dos.get_x()[1]; ys = dos.get_y()
    fig, ax = plt.subplots(figsize=(5.0, 4.0))
    for name, _, y in ys:
        ax.plot(E, y, lw=1.0, label=name)
    ax.axvline(0, color="#888", ls="--", lw=0.8)
    ax.set_xlabel(r"$E - E_\mathrm{F}$ (eV)"); ax.set_ylabel("DOS (states/eV)")
    ax.set_xlim(-6, 6); ax.legend(fontsize=8); ax.set_title("Density of states")
    return savefig(fig, outdir, "dos"), "状態密度（必要に応じ PDOS を重ね描き）"


def plot_magnetic(wc, outdir):
    """QE は M–H 曲線は出さない。DFT の磁気＝局所モーメント＋全磁化（+MAE/J/DMI があれば注記）。"""
    p = wc.outputs.output_parameters.get_dict()
    moments = p.get("atomic_magnetic_moments") or p.get("Magnetic moments") or []
    totM = p.get("total_magnetization")
    fig, ax = plt.subplots(figsize=(5.0, 3.8))
    if moments:
        idx = np.arange(len(moments))
        ax.bar(idx, moments, color=["#d62728" if m >= 0 else "#1f77b4" for m in moments])
        ax.set_xlabel("atom index"); ax.set_ylabel(r"local moment ($\mu_B$)")
    else:
        ax.text(0.5, 0.5, "per-atom moments 未取得", ha="center", va="center", transform=ax.transAxes, color="#888")
    ttl = "Magnetic moments"
    if totM is not None: ttl += f"  (total M = {totM:.2f} μB)"
    ax.set_title(ttl)
    return savefig(fig, outdir, "magnetic"), "局所磁気モーメント（DFT。実験 M–H は SQUID 側）"


def plot_deltarho(wc, outdir):
    """電荷移動 Δρ：qe-auto Phase6 の平面平均 Δρ(z) 配列があれば描く。無ければ None。"""
    try:
        d = wc.outputs.charge_transfer  # qe-auto の Δρ 出力 (ArrayData 想定)
        z = d.get_array("z"); drho = d.get_array("delta_rho_planar")
    except Exception:
        return None, None
    fig, ax = plt.subplots(figsize=(5.0, 3.6))
    ax.plot(z, drho, color="#7a3ff2", lw=1.2); ax.fill_between(z, drho, color="#7a3ff2", alpha=0.18)
    ax.axhline(0, color="#888", lw=0.7)
    ax.set_xlabel("z (Å)"); ax.set_ylabel(r"$\Delta\rho$ (planar avg)"); ax.set_title("Charge transfer Δρ")
    return savefig(fig, outdir, "deltarho"), "差電荷密度の平面平均（インターカレーションによる電荷移動）"


FIGURES = [
    ("bands",    "バンド構造",   plot_bands),
    ("dos",      "DOS / PDOS",   plot_dos),
    ("deltarho", "電荷移動 Δρ",  plot_deltarho),
    ("magnetic", "磁気",         plot_magnetic),
]


def summary_of(wc):
    try: p = wc.outputs.output_parameters.get_dict()
    except Exception: p = {}
    s = wc.inputs.structure if "structure" in wc.inputs else getattr(wc.outputs, "output_structure", None)
    return {
        "formula": s.get_formula() if s else p.get("formula"),
        "natoms": len(s.sites) if s else None,
        "total_energy_ev": p.get("energy"),
        "fermi_ev": p.get("fermi_energy"),
        "gap_ev": p.get("band_gap") or p.get("homo_lumo_gap"),
        "is_metallic": p.get("is_metallic") or (p.get("band_gap") in (None, 0)),
        "total_magnetization": p.get("total_magnetization"),
    }, s


def collect_files(wc, outdir):
    """retrieved フォルダから主要出力ファイルをコピー + structure.cif を書き出し。"""
    files = []
    fdir = os.path.join(outdir, "files"); os.makedirs(fdir, exist_ok=True)
    # 構造 CIF
    try:
        _, s = summary_of(wc)
        if s:
            cif = os.path.join(fdir, "structure.cif")
            s._exportcontent("cif")  # noqa
            with open(cif, "w") as f: f.write(s._exportcontent("cif")[0].decode())
            files.append({"name": "structure.cif", "path": os.path.relpath(cif, DATA_DIR), "bytes": os.path.getsize(cif)})
    except Exception as e:
        print("  [warn] cif:", e)
    # retrieved の主要ファイル
    for desc in wc.called_descendants:
        retr = getattr(getattr(desc, "outputs", None), "retrieved", None)
        if not retr: continue
        for name in retr.list_object_names():
            if name.endswith((".out", ".xml")) or name in ("aiida.out", "data-file-schema.xml"):
                dst = os.path.join(fdir, f"pk{desc.pk}_{name}")
                with retr.open(name, "rb") as src, open(dst, "wb") as out: shutil.copyfileobj(src, out)
                files.append({"name": f"pk{desc.pk}_{name}", "path": os.path.relpath(dst, DATA_DIR), "bytes": os.path.getsize(dst)})
    return files


def export_one(pk, sid, title, config=""):
    wc = load_node(pk)
    outdir = os.path.join(DATA_DIR, sid); os.makedirs(outdir, exist_ok=True)
    summ, _ = summary_of(wc)
    figs = []
    for key, ftitle, fn in FIGURES:
        try:
            rel, cap = fn(wc, outdir)
            if rel: figs.append({"key": key, "title": ftitle, "caption": cap, **rel})
        except Exception as e:
            print(f"  [warn] {key}: {e}")
    files = collect_files(wc, outdir)
    print(f"  {sid}: 図 {len(figs)} / ファイル {len(files)}")
    return {
        "id": sid, "title": title, "config": config, "pk": pk,
        "ctime": wc.ctime.isoformat() if wc.ctime else None,
        "summary": summ, "figures": figs, "files": files,
    }


def main():
    ap = argparse.ArgumentParser(description="QE 結果 → 発表用ギャラリー書き出し")
    ap.add_argument("--pk", type=int, help="単一 PK を書き出し")
    ap.add_argument("--id", help="系 ID（フォルダ名。例 vse2_dbpo_cation）")
    ap.add_argument("--title", help="表示タイトル")
    ap.add_argument("--config", default="", help="補足（電荷/配置など）")
    ap.add_argument("--all-finished", action="store_true", help="完了済み QeFullWorkChain を全部")
    ap.add_argument("--git-push", action="store_true", help="書き出し後 git add/commit/push")
    args = ap.parse_args()

    os.makedirs(DATA_DIR, exist_ok=True)
    systems = []

    if args.all_finished:
        from aiida.orm import QueryBuilder, WorkChainNode
        qb = QueryBuilder().append(WorkChainNode, filters={"attributes.process_label": "QeFullWorkChain",
                                                           "attributes.process_state": "finished"})
        for (wc,) in qb.all():
            sid = f"pk{wc.pk}"
            systems.append(export_one(wc.pk, sid, wc.label or sid))
    elif args.pk:
        sid = args.id or f"pk{args.pk}"
        systems.append(export_one(args.pk, sid, args.title or sid, args.config))
    else:
        ap.error("--pk か --all-finished を指定してください")

    gallery = {"generated_at": datetime.datetime.now().isoformat(timespec="seconds"), "systems": systems}
    with open(os.path.join(DATA_DIR, "gallery.json"), "w", encoding="utf-8") as f:
        json.dump(gallery, f, ensure_ascii=False, indent=2)
    print(f"→ data/gallery.json 更新 ({len(systems)} 系)")

    if args.git_push:
        subprocess.run(["git", "-C", HERE, "add", "data"], check=False)
        subprocess.run(["git", "-C", HERE, "commit", "-m", f"qe gallery: {len(systems)} 系を更新"], check=False)
        subprocess.run(["git", "-C", HERE, "push"], check=False)
        print("→ git push 済")


if __name__ == "__main__":
    main()
