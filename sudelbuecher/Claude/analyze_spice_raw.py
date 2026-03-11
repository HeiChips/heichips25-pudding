#!/usr/bin/env python3
"""
IHP 130nm ngspice .raw File Analyzer
=====================================
Liest ngspice Binary RAW files, exportiert CSV-Daten und erstellt Grafiken.
Unterstützt: Operating Point, DC-Sweep (1D und 2D/parametric), AC, Transient.

Verwendung:
    python3 analyze_spice_raw.py <file.raw> [optionen]
    python3 analyze_spice_raw.py test_nmirror.raw
    python3 analyze_spice_raw.py test_ncmirror.raw --plot-type mirror
    python3 analyze_spice_raw.py test_nmirror.raw --list-vars
    python3 analyze_spice_raw.py test_nmirror.raw --vars "i(vd),v(vg)" --out myplot
"""

import argparse
import os
import re
import struct
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import numpy as np
import pandas as pd

# ─── Matplotlib Style ────────────────────────────────────────────────────────
plt.rcParams.update({
    "figure.facecolor": "#0d1117",
    "axes.facecolor": "#161b22",
    "axes.edgecolor": "#30363d",
    "axes.labelcolor": "#e6edf3",
    "axes.titlecolor": "#e6edf3",
    "xtick.color": "#8b949e",
    "ytick.color": "#8b949e",
    "grid.color": "#21262d",
    "grid.linewidth": 0.8,
    "text.color": "#e6edf3",
    "legend.facecolor": "#161b22",
    "legend.edgecolor": "#30363d",
    "legend.labelcolor": "#e6edf3",
    "font.family": "monospace",
    "font.size": 10,
    "axes.titlesize": 13,
    "axes.labelsize": 11,
    "figure.titlesize": 15,
})

PALETTE = ["#58a6ff", "#3fb950", "#ff7b72", "#d2a8ff", "#ffa657",
           "#79c0ff", "#56d364", "#ff9492", "#bc8cff", "#ffb86c"]


# ─── RAW File Parser ──────────────────────────────────────────────────────────

def parse_raw(filepath: str) -> list[dict]:
    """
    Parst eine ngspice Binary RAW Datei.
    Gibt eine Liste von Plot-Dicts zurück:
        {plotname, flags, nvars, npoints, variables: [{idx,name,type}], data: np.ndarray}
    Mehrere Plots (parametric sweeps, OP + DC) werden alle zurückgegeben.
    """
    with open(filepath, "rb") as f:
        raw = f.read()

    plots = []
    pos = 0

    while pos < len(raw):
        bm = raw.find(b"Binary:\n", pos)
        if bm == -1:
            break

        header = raw[pos:bm].decode("utf-8", errors="replace")
        meta = {}
        variables = []

        for line in header.split("\n"):
            line = line.strip()
            if line.startswith("Title:"):
                meta["title"] = line[6:].strip()
            elif line.startswith("Date:"):
                meta["date"] = line[5:].strip()
            elif line.startswith("Plotname:"):
                meta["plotname"] = line[9:].strip()
            elif line.startswith("Flags:"):
                meta["flags"] = line[6:].strip()
            elif line.startswith("No. Variables:"):
                meta["nvars"] = int(line[14:].strip())
            elif line.startswith("No. Points:"):
                meta["npoints"] = int(line[11:].strip())
            elif re.match(r"\s*\d+\s", line):
                parts = line.split("\t")
                if len(parts) >= 3:
                    variables.append({
                        "idx": int(parts[0]),
                        "name": parts[1].strip(),
                        "type": parts[2].strip()
                    })

        nvars = meta.get("nvars", 0)
        npoints = meta.get("npoints", 0)
        is_complex = "complex" in meta.get("flags", "")
        ds = bm + len(b"Binary:\n")

        if nvars > 0 and npoints > 0:
            if is_complex:
                dtype = np.complex128
                bpv = 16
            else:
                dtype = np.float64
                bpv = 8

            nb = nvars * npoints * bpv
            arr = np.frombuffer(raw[ds:ds + nb], dtype=dtype).reshape(npoints, nvars)
            meta.update({
                "data": arr,
                "variables": variables,
                "filepath": filepath
            })
            plots.append(meta)
            pos = ds + nb
        else:
            pos = ds + 1

    return plots


def get_col(plot: dict, name: str) -> np.ndarray | None:
    """Findet eine Spalte per Name (case-insensitiv, partial match)."""
    vnames = [v["name"].lower() for v in plot["variables"]]
    name_l = name.lower()
    # Exact match first
    for i, n in enumerate(vnames):
        if n == name_l:
            return plot["data"][:, i]
    # Partial match
    for i, n in enumerate(vnames):
        if name_l in n:
            return plot["data"][:, i]
    return None


def list_variables(plots: list[dict]):
    """Gibt alle Variablen aller Plots aus."""
    for pi, p in enumerate(plots):
        pn = p.get("plotname", f"Plot {pi}")
        npts = p.get("npoints", "?")
        print(f"\n{'─'*60}")
        print(f"  Plot [{pi}]: {pn}  ({npts} Punkte)")
        print(f"{'─'*60}")
        print(f"  {'#':>4}  {'Name':<50}  {'Typ'}")
        print(f"  {'─'*4}  {'─'*50}  {'─'*15}")
        for v in p["variables"]:
            print(f"  {v['idx']:>4}  {v['name']:<50}  {v['type']}")


def detect_sweep_structure(plot: dict):
    """
    Erkennt die Sweep-Struktur eines DC-Plots.
    Gibt (n_inner, n_outer, sweep_axis) zurück.
    """
    sweep_col = plot["data"][:, 0]
    resets = np.where(np.diff(sweep_col) < -0.05)[0]
    if len(resets) == 0:
        return len(sweep_col), 1, sweep_col
    n_inner = resets[0] + 1
    n_outer = len(resets) + 1
    return n_inner, n_outer, sweep_col[:n_inner]


# ─── Export ───────────────────────────────────────────────────────────────────

def export_csv(plots: list[dict], out_prefix: str):
    """Exportiert alle Plots als CSV-Dateien."""
    csv_files = []
    for pi, p in enumerate(plots):
        pname = re.sub(r"[^\w]", "_", p.get("plotname", f"plot_{pi}")).lower()
        fname = f"{out_prefix}_{pname}.csv"

        # Flatten bei parametric sweeps mit Sweep-Index
        n_inner, n_outer, _ = detect_sweep_structure(p)
        data = p["data"]
        vnames = [v["name"] for v in p["variables"]]

        rows = []
        for i_out in range(n_outer):
            seg = data[i_out * n_inner:(i_out + 1) * n_inner, :]
            df_seg = pd.DataFrame(seg.real, columns=vnames)
            df_seg.insert(0, "sweep_idx", i_out)
            rows.append(df_seg)

        df = pd.concat(rows, ignore_index=True)
        df.to_csv(fname, index=False, float_format="%.6e")
        print(f"  CSV: {fname}  ({len(df)} Zeilen, {len(df.columns)} Spalten)")
        csv_files.append(fname)

    return csv_files


# ─── Plots ────────────────────────────────────────────────────────────────────

def si_formatter(unit="A"):
    """Gibt einen Matplotlib FuncFormatter für SI-Präfixe zurück."""
    prefixes = [(1e-15, "f"), (1e-12, "p"), (1e-9, "n"),
                (1e-6, "µ"), (1e-3, "m"), (1, ""), (1e3, "k")]

    def fmt(x, pos):
        for val, pref in reversed(prefixes):
            if abs(x) >= val * 0.99:
                return f"{x/val:.3g} {pref}{unit}"
        return f"{x:.3g} {unit}"

    return ticker.FuncFormatter(fmt)


def plot_dc_sweep(plots: list[dict], out_prefix: str, extra_vars: list[str] = None):
    """
    Plottet DC-Sweep Plots (IDs vs VDS für verschiedene IRef Kurven).
    Für Current Mirror: Mirror Current + Mirror Ratio.
    """
    dc_plots = [p for p in plots if "dc" in p.get("plotname", "").lower()
                or "transfer" in p.get("plotname", "").lower()]

    if not dc_plots:
        print("  Keine DC-Sweep Plots gefunden.")
        return []

    figs = []

    for pi, p in enumerate(dc_plots):
        vnames = [v["name"] for v in p["variables"]]
        n_inner, n_outer, vd_axis = detect_sweep_structure(p)

        # Schätze äußere Sweep-Werte (VlogI: -8 to -6)
        # Suche in v-sweep ob es resets gibt
        outer_vals = np.linspace(-8, -6, n_outer)  # Default
        logi_col = get_col(p, "logi")
        if logi_col is not None:
            outer_vals = [logi_col[i * n_inner] for i in range(n_outer)]

        # Finde relevante Ströme
        iout_col = None
        iref_col = None
        for name in ["i(vd)", "vd#branch"]:
            c = get_col(p, name)
            if c is not None:
                iout_col = c
                break
        for name in ["i(vprobe)", "vprobe#branch"]:
            c = get_col(p, name)
            if c is not None:
                iref_col = c
                break

        if iout_col is None:
            print(f"  [Plot {pi}] Kein Ausgangsstrom gefunden, überspringe.")
            continue

        # ── Figure Layout ────────────────────────────────────────────────
        has_mirror = iref_col is not None
        n_rows = 3 if has_mirror else 1
        fig, axes = plt.subplots(n_rows, 1, figsize=(10, 4 * n_rows),
                                 facecolor="#0d1117", sharex=True)
        if n_rows == 1:
            axes = [axes]

        fig.suptitle(
            f"{Path(p['filepath']).stem}  —  {p['plotname']} (Run {pi + 1})",
            fontsize=14, fontweight="bold", color="#e6edf3", y=0.98
        )

        ax_ids = axes[0]
        ax_ids.set_title("Ausgangsstrom I_out vs V_DS", pad=8)
        ax_ids.set_ylabel("I_out")
        ax_ids.yaxis.set_major_formatter(si_formatter("A"))
        ax_ids.grid(True, alpha=0.4)

        for i_out in range(n_outer):
            seg_ids = -iout_col[i_out * n_inner:(i_out + 1) * n_inner]
            I_ref = 10 ** outer_vals[i_out]
            label = f"I_ref = {I_ref*1e9:.0f} nA" if I_ref < 1e-6 else \
                    f"I_ref = {I_ref*1e6:.3f} µA"
            ax_ids.plot(vd_axis, seg_ids, color=PALETTE[i_out % len(PALETTE)],
                        linewidth=1.8, label=label)

        ax_ids.axvline(0.1, color="#8b949e", linestyle="--", linewidth=0.8, alpha=0.6,
                       label="V_DS = 100mV")
        ax_ids.legend(fontsize=8, loc="lower right")

        if has_mirror:
            ax_ratio = axes[1]
            ax_ratio.set_title("Mirror Ratio I_out / I_ref", pad=8)
            ax_ratio.set_ylabel("Ratio")
            ax_ratio.axhline(1.0, color="#8b949e", linestyle="--", linewidth=0.8, alpha=0.7)
            ax_ratio.grid(True, alpha=0.4)

            ax_ro = axes[2]
            ax_ro.set_title("Ausgangsimpedanz r_o = ΔV_DS / ΔI_out", pad=8)
            ax_ro.set_ylabel("r_o")
            ax_ro.yaxis.set_major_formatter(si_formatter("Ω"))
            ax_ro.grid(True, alpha=0.4)
            ax_ro.set_xlabel("V_DS  [V]")

            for i_out in range(n_outer):
                seg_ids = -iout_col[i_out * n_inner:(i_out + 1) * n_inner]
                seg_iref = -iref_col[i_out * n_inner:(i_out + 1) * n_inner]
                I_ref = 10 ** outer_vals[i_out]

                ratio = seg_ids / (seg_iref + 1e-20)
                # Nur für VDS > 0.05V sinnvoll
                mask = vd_axis > 0.05
                ax_ratio.plot(vd_axis[mask], ratio[mask],
                              color=PALETTE[i_out % len(PALETTE)],
                              linewidth=1.8,
                              label=f"I_ref = {I_ref*1e6:.3f} µA")

                # r_o via Ableitung (smoothed)
                dV = np.diff(vd_axis)
                dI = np.diff(seg_ids)
                ro = dV / (dI + 1e-25)
                ro_x = (vd_axis[:-1] + vd_axis[1:]) / 2
                mask2 = (ro_x > 0.1) & (np.abs(ro) < 1e12)
                if mask2.sum() > 2:
                    ax_ro.semilogy(ro_x[mask2], np.abs(ro[mask2]),
                                   color=PALETTE[i_out % len(PALETTE)],
                                   linewidth=1.5, alpha=0.85)

            ax_ratio.legend(fontsize=8)
            axes[-1].set_xlabel("V_DS  [V]")

        plt.tight_layout(rect=[0, 0, 1, 0.97])
        fname = f"{out_prefix}_dc_run{pi+1}.png"
        fig.savefig(fname, dpi=150, bbox_inches="tight",
                    facecolor=fig.get_facecolor())
        print(f"  Plot: {fname}")
        figs.append(fname)
        plt.close(fig)

    return figs


def plot_mirror_comparison(plots: list[dict], out_prefix: str):
    """
    Vergleichs-Plot für mehrere parametrische DC-Runs (z.B. verschiedene W/L).
    Zeigt I_out@VDS=0.6V und Mirror Ratio als Funktion von I_ref.
    """
    dc_plots = [p for p in plots if "dc" in p.get("plotname", "").lower()
                or "transfer" in p.get("plotname", "").lower()]
    if len(dc_plots) < 2:
        return []

    fig, axes = plt.subplots(1, 2, figsize=(14, 5), facecolor="#0d1117")
    fig.suptitle(f"{Path(dc_plots[0]['filepath']).stem}  —  Parametric Comparison",
                 fontsize=14, fontweight="bold", color="#e6edf3")

    ax_l = axes[0]
    ax_r = axes[1]
    ax_l.set_title("I_out @ V_DS = 0.6 V  vs  I_ref")
    ax_l.set_xlabel("I_ref  [A]")
    ax_l.set_ylabel("I_out  [A]")
    ax_l.set_xscale("log")
    ax_l.set_yscale("log")
    ax_l.grid(True, alpha=0.4, which="both")

    ax_r.set_title("Mirror Ratio @ V_DS = 0.6 V  vs  I_ref")
    ax_r.set_xlabel("I_ref  [A]")
    ax_r.set_ylabel("I_out / I_ref")
    ax_r.set_xscale("log")
    ax_r.grid(True, alpha=0.4)
    ax_r.axhline(1.0, color="#8b949e", linestyle="--", linewidth=1, alpha=0.7)

    # Ideale Linie
    i_range = np.logspace(-8, -6, 100)
    ax_l.plot(i_range, i_range, color="#8b949e", linestyle="--",
              linewidth=1.2, alpha=0.7, label="ideal (ratio=1)")

    vds_target = 0.6
    run_labels = [f"Run {i+1}" for i in range(len(dc_plots))]

    for pi, p in enumerate(dc_plots):
        n_inner, n_outer, vd_axis = detect_sweep_structure(p)
        outer_vals = np.linspace(-8, -6, n_outer)

        iout_col = get_col(p, "i(vd)")
        iref_col = get_col(p, "i(vprobe)")

        if iout_col is None:
            continue

        i_ref_vals, i_out_vals, ratio_vals = [], [], []
        vds_idx = np.argmin(np.abs(vd_axis - vds_target))

        for i_out_idx in range(n_outer):
            i_ref = 10 ** outer_vals[i_out_idx]
            seg_ids = -iout_col[i_out_idx * n_inner:(i_out_idx + 1) * n_inner]
            i_out_at_vds = seg_ids[vds_idx]
            i_ref_vals.append(i_ref)
            i_out_vals.append(i_out_at_vds)
            if iref_col is not None:
                seg_iref = -iref_col[i_out_idx * n_inner:(i_out_idx + 1) * n_inner]
                ratio_vals.append(i_out_at_vds / (seg_iref[vds_idx] + 1e-20))
            else:
                ratio_vals.append(i_out_at_vds / (i_ref + 1e-20))

        col = PALETTE[pi % len(PALETTE)]
        ax_l.plot(i_ref_vals, i_out_vals, "o-", color=col,
                  linewidth=1.8, markersize=6, label=run_labels[pi])
        ax_r.plot(i_ref_vals, ratio_vals, "o-", color=col,
                  linewidth=1.8, markersize=6, label=run_labels[pi])

    ax_l.legend()
    ax_r.legend()
    plt.tight_layout(rect=[0, 0, 1, 0.95])

    fname = f"{out_prefix}_comparison.png"
    fig.savefig(fname, dpi=150, bbox_inches="tight",
                facecolor=fig.get_facecolor())
    print(f"  Plot: {fname}")
    plt.close(fig)
    return [fname]


def plot_op_summary(plots: list[dict], out_prefix: str):
    """Gibt Operating Point Daten als formatierte Tabelle aus und als PNG."""
    op_plots = [p for p in plots if "operating" in p.get("plotname", "").lower()
                or "op" == p.get("plotname", "").lower().strip()]
    if not op_plots:
        return []

    figs = []
    for pi, p in enumerate(op_plots):
        vnames = [v["name"] for v in p["variables"]]
        vals = p["data"][0, :]  # 1 Punkt

        # Nur interessante Größen
        interesting = {
            "ids": "µA", "gm": "mS", "gds": "µS",
            "vth": "V", "vgs": "V", "vds": "V",
            "cgg": "fF", "cgsol": "fF", "cgdol": "fF"
        }
        scale = {
            "µA": 1e6, "mS": 1e3, "µS": 1e6,
            "V": 1, "fF": 1e15, "mA": 1e3
        }

        rows = []
        for i, name in enumerate(vnames):
            nl = name.lower()
            for key, unit in interesting.items():
                if key in nl:
                    s = scale.get(unit, 1)
                    rows.append((name, vals[i].real * s, unit))
                    break

        if not rows:
            continue

        # Tabellen-Plot
        fig, ax = plt.subplots(figsize=(10, max(4, len(rows) * 0.4 + 1.5)),
                               facecolor="#0d1117")
        ax.set_facecolor("#0d1117")
        ax.axis("off")
        fig.suptitle(f"Operating Point — {Path(p['filepath']).stem}",
                     fontsize=13, fontweight="bold", color="#e6edf3")

        col_labels = ["Variable", "Wert", "Einheit"]
        table_data = [[r[0], f"{r[1]:.4g}", r[2]] for r in rows]

        tbl = ax.table(
            cellText=table_data,
            colLabels=col_labels,
            cellLoc="left",
            loc="center",
            colWidths=[0.6, 0.2, 0.2]
        )
        tbl.auto_set_font_size(False)
        tbl.set_fontsize(9)

        for (row, col), cell in tbl.get_celld().items():
            cell.set_edgecolor("#30363d")
            if row == 0:
                cell.set_facecolor("#21262d")
                cell.set_text_props(color="#58a6ff", fontweight="bold")
            else:
                cell.set_facecolor("#161b22" if row % 2 == 0 else "#0d1117")
                cell.set_text_props(color="#e6edf3")

        plt.tight_layout()
        fname = f"{out_prefix}_op_run{pi+1}.png"
        fig.savefig(fname, dpi=150, bbox_inches="tight",
                    facecolor=fig.get_facecolor())
        print(f"  Plot: {fname}")
        figs.append(fname)
        plt.close(fig)

    return figs


def plot_custom_vars(plots: list[dict], var_list: list[str], out_prefix: str):
    """Plottet beliebige Variablen aus allen DC-Plots."""
    dc_plots = [p for p in plots if "dc" in p.get("plotname", "").lower()
                or "transfer" in p.get("plotname", "").lower()]
    if not dc_plots:
        return []

    fig, ax = plt.subplots(figsize=(10, 5), facecolor="#0d1117")
    ax.set_title(f"Custom Variables: {', '.join(var_list)}")
    ax.set_xlabel("V_DS  [V]")
    ax.set_ylabel("Wert")
    ax.grid(True, alpha=0.4)

    color_idx = 0
    for pi, p in enumerate(dc_plots):
        n_inner, n_outer, vd_axis = detect_sweep_structure(p)
        for var in var_list:
            col = get_col(p, var)
            if col is None:
                print(f"  Warnung: Variable '{var}' nicht in Plot {pi} gefunden.")
                continue
            for i_out in range(n_outer):
                seg = col[i_out * n_inner:(i_out + 1) * n_inner]
                label = f"Run{pi+1} {var} [sweep{i_out}]" if n_outer > 1 else f"Run{pi+1} {var}"
                ax.plot(vd_axis, seg.real, color=PALETTE[color_idx % len(PALETTE)],
                        linewidth=1.6, label=label)
                color_idx += 1

    ax.legend(fontsize=8)
    plt.tight_layout()
    fname = f"{out_prefix}_custom.png"
    fig.savefig(fname, dpi=150, bbox_inches="tight",
                facecolor=fig.get_facecolor())
    print(f"  Plot: {fname}")
    plt.close(fig)
    return [fname]


# ─── Summary Stats ────────────────────────────────────────────────────────────

def print_summary(plots: list[dict]):
    """Gibt eine Zusammenfassung der wichtigsten Kennwerte aus."""
    print("\n" + "═" * 65)
    print("  SIMULATION SUMMARY")
    print("═" * 65)

    for pi, p in enumerate(plots):
        pname = p.get("plotname", "?")
        npts = p.get("npoints", "?")
        nvars = p.get("nvars", "?")
        print(f"\n  [{pi}] {pname}  |  {npts} Punkte  |  {nvars} Variablen")

        if "dc" in pname.lower() or "transfer" in pname.lower():
            n_inner, n_outer, vd_axis = detect_sweep_structure(p)
            outer_vals = np.linspace(-8, -6, n_outer)

            iout_col = get_col(p, "i(vd)")
            iref_col = get_col(p, "i(vprobe)")

            if iout_col is not None:
                vds_idx = np.argmin(np.abs(vd_axis - 0.6))
                print(f"      Sweep: {n_outer} IRef-Kurven × {n_inner} VDS-Punkte")
                print(f"      {'IRef':>10}  {'Iout@0.6V':>12}  {'Ratio':>8}  {'ro@0.6V':>12}")
                print(f"      {'─'*10}  {'─'*12}  {'─'*8}  {'─'*12}")

                for i_out in range(n_outer):
                    i_ref = 10 ** outer_vals[i_out]
                    seg_ids = -iout_col[i_out * n_inner:(i_out + 1) * n_inner]
                    i_at_vds = seg_ids[vds_idx]

                    # r_o Schätzung
                    dV = np.diff(vd_axis)
                    dI = np.diff(seg_ids)
                    mask = (vd_axis[:-1] > 0.4) & (vd_axis[:-1] < 0.8)
                    ro = np.median(np.abs(dV[mask] / (dI[mask] + 1e-25))) if mask.sum() > 0 else float("nan")

                    ratio = i_at_vds / (i_ref + 1e-20)
                    print(f"      {i_ref*1e6:>8.3f}µA  {i_at_vds*1e6:>10.4f}µA  {ratio:>8.4f}  {ro:>10.2e}Ω")

        elif "operating" in pname.lower():
            # Zeige wichtige OP-Parameter
            for v in p["variables"]:
                if any(k in v["name"].lower() for k in ["ids", "gm", "vth"]):
                    val = p["data"][0, v["idx"]]
                    print(f"      {v['name']:<45}  {val:.4e}  {v['type']}")


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="IHP 130nm ngspice .raw Analyzer",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument("rawfile", help="Pfad zur .raw Datei")
    parser.add_argument("--out", default=None,
                        help="Ausgabe-Präfix (Default: Dateiname ohne Erweiterung)")
    parser.add_argument("--list-vars", action="store_true",
                        help="Alle Variablen auflisten und beenden")
    parser.add_argument("--no-csv", action="store_true",
                        help="Kein CSV-Export")
    parser.add_argument("--no-plot", action="store_true",
                        help="Keine Grafiken")
    parser.add_argument("--vars", default=None,
                        help="Komma-getrennte Variablen für Custom-Plot, z.B. 'i(vd),v(vg)'")
    parser.add_argument("--plot-type", default="auto",
                        choices=["auto", "mirror", "basic"],
                        help="Plot-Typ: auto, mirror (Current Mirror Analyse), basic")
    parser.add_argument("--outdir", default=".",
                        help="Ausgabe-Verzeichnis")

    args = parser.parse_args()

    rawfile = args.rawfile
    if not os.path.exists(rawfile):
        print(f"Fehler: Datei '{rawfile}' nicht gefunden.")
        sys.exit(1)

    out_prefix = args.out or Path(rawfile).stem
    out_prefix = os.path.join(args.outdir, out_prefix)
    os.makedirs(args.outdir, exist_ok=True)

    print(f"\n{'═'*65}")
    print(f"  IHP 130nm ngspice RAW Analyzer")
    print(f"  Datei: {rawfile}")
    print(f"{'═'*65}")

    # Parse
    print("\n  Parsing RAW file...")
    plots = parse_raw(rawfile)
    print(f"  → {len(plots)} Plot(s) gefunden.")

    if args.list_vars:
        list_variables(plots)
        return

    # Summary
    print_summary(plots)

    all_outputs = []

    # CSV Export
    if not args.no_csv:
        print("\n  CSV-Export:")
        csv_files = export_csv(plots, out_prefix)
        all_outputs.extend(csv_files)

    # Plots
    if not args.no_plot:
        print("\n  Grafiken:")

        # OP Summary
        op_figs = plot_op_summary(plots, out_prefix)
        all_outputs.extend(op_figs)

        # DC Sweeps
        dc_figs = plot_dc_sweep(plots, out_prefix)
        all_outputs.extend(dc_figs)

        # Mirror Comparison (wenn mehrere DC-Runs vorhanden)
        dc_count = sum(1 for p in plots if "dc" in p.get("plotname", "").lower()
                       or "transfer" in p.get("plotname", "").lower())
        if dc_count >= 2 and args.plot_type in ("auto", "mirror"):
            comp_figs = plot_mirror_comparison(plots, out_prefix)
            all_outputs.extend(comp_figs)

        # Custom Vars
        if args.vars:
            var_list = [v.strip() for v in args.vars.split(",")]
            custom_figs = plot_custom_vars(plots, var_list, out_prefix)
            all_outputs.extend(custom_figs)

    print(f"\n{'═'*65}")
    print(f"  Fertig! {len(all_outputs)} Dateien erstellt:")
    for f in all_outputs:
        print(f"    {f}")
    print(f"{'═'*65}\n")


if __name__ == "__main__":
    main()
