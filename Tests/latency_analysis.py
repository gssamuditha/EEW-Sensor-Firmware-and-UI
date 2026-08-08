"""
latency_analysis.py - Offline EEW UDP Latency Analysis Script
==============================================================
Post-process a CSV file produced by udp_latency_analyzer.py.
Generates publication-quality figures and a detailed statistical report.

Usage
-----
  python latency_analysis.py udp_latency_data_20260808_120000.csv

  # Optional: apply clock offset correction
  python latency_analysis.py data.csv --clock-offset 12.5

  # Optional: trim first N seconds (warmup) and last N seconds
  python latency_analysis.py data.csv --trim-start 10 --trim-end 5

Requirements
------------
  pip install pandas numpy matplotlib scipy
"""

import argparse
import os
import sys
from datetime import datetime, timezone

import numpy as np
import pandas as pd

try:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import matplotlib.gridspec as gridspec
    _MPL = True
except ImportError:
    _MPL = False
    print("[WARN] matplotlib not installed -- no figures will be generated.")

try:
    from scipy import stats as _ss
    _SCIPY = True
except ImportError:
    _SCIPY = False

PLOT_STYLE = {
    'figure.facecolor': '#0d1117',
    'axes.facecolor':   '#161b22',
    'axes.edgecolor':   '#30363d',
    'axes.labelcolor':  '#c9d1d9',
    'xtick.color':      '#8b949e',
    'ytick.color':      '#8b949e',
    'text.color':       '#c9d1d9',
    'grid.color':       '#21262d',
    'grid.linestyle':   '--',
    'grid.linewidth':   0.5,
}

ACCENT  = '#58a6ff'
ACCENT2 = '#f0883e'
ACCENT3 = '#3fb950'
RED     = '#f85149'


def load_csv(path, clock_offset_ms, trim_start, trim_end):
    df = pd.read_csv(path)
    required = {'recv_utc', 'packet_ts', 'owd_ms', 'jitter_ms', 'is_loss_gap'}
    missing  = required - set(df.columns)
    if missing:
        print(f"[ERROR] CSV is missing columns: {missing}")
        sys.exit(1)

    df = df[df['is_loss_gap'] == 0].copy()

    if len(df) == 0:
        print("[ERROR] No valid (non-loss) packets in CSV.")
        sys.exit(1)

    t0 = df['recv_utc'].min()
    df['t_rel'] = df['recv_utc'] - t0

    if trim_start:
        df = df[df['t_rel'] >= trim_start]
    if trim_end:
        t_max = df['t_rel'].max()
        df = df[df['t_rel'] <= (t_max - trim_end)]

    if clock_offset_ms != 0.0:
        print(f"  Applying clock offset correction: {clock_offset_ms:+.3f} ms")
        df['owd_ms'] = df['owd_ms'] + clock_offset_ms

    return df


def compute_stats(owd):
    a = np.array(owd, dtype=np.float64)
    stats = {
        'n':    len(a),
        'mean': float(np.mean(a)),
        'std':  float(np.std(a, ddof=1)) if len(a) > 1 else 0.0,
        'min':  float(np.min(a)),
        'max':  float(np.max(a)),
        'p25':  float(np.percentile(a, 25)),
        'p50':  float(np.percentile(a, 50)),
        'p75':  float(np.percentile(a, 75)),
        'p95':  float(np.percentile(a, 95)),
        'p99':  float(np.percentile(a, 99)),
        'p999': float(np.percentile(a, 99.9)),
        'iqr':  float(np.percentile(a, 75) - np.percentile(a, 25)),
    }
    return stats


def print_report(df, stats, args):
    print()
    print("=" * 72)
    print("  EEW UDP LATENCY -- OFFLINE ANALYSIS REPORT")
    print("=" * 72)
    print(f"  Input file   : {args.csv}")
    print(f"  Analysed     : {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print(f"  Clock offset : {args.clock_offset:+.3f} ms (applied to OWD)")
    print(f"  Duration     : {df['t_rel'].max():.1f} s  ({df['t_rel'].max()/60:.2f} min)")
    print()
    print("-" * 72)
    print("  INTERPRETATION:")
    print(f"    True OWD = measured_OWD + {args.clock_offset:.3f} ms")
    print()
    print("-" * 72)
    print("  ONE-WAY DELAY (OWD) STATISTICS")
    print("-" * 72)
    print(f"  N                  : {stats['n']}")
    print(f"  Mean               : {stats['mean']:.3f} ms")
    print(f"  Std Dev            : {stats['std']:.3f} ms")
    print(f"  Min                : {stats['min']:.3f} ms")
    print(f"  Max                : {stats['max']:.3f} ms")
    print(f"  P25                : {stats['p25']:.3f} ms")
    print(f"  P50 (Median)       : {stats['p50']:.3f} ms")
    print(f"  P75                : {stats['p75']:.3f} ms")
    print(f"  P95                : {stats['p95']:.3f} ms")
    print(f"  P99                : {stats['p99']:.3f} ms")
    print(f"  P99.9              : {stats['p999']:.3f} ms")
    print(f"  IQR (P75-P25)      : {stats['iqr']:.3f} ms")
    print()

    if _SCIPY and stats['n'] > 10:
        pos = np.array(df['owd_ms'][df['owd_ms'] > 0], dtype=np.float64)
        if len(pos) > 10:
            try:
                shape, loc, scale = _ss.lognorm.fit(pos, floc=0)
                ks, p = _ss.kstest(pos, 'lognorm', args=(shape, loc, scale))
                print("-" * 72)
                print("  LOG-NORMAL DISTRIBUTION FIT")
                print("-" * 72)
                print(f"  Shape (sigma)      : {shape:.4f}")
                print(f"  Scale (exp(mu))    : {scale:.4f} ms")
                print(f"  KS statistic       : {ks:.4f}")
                print(f"  KS p-value         : {p:.4f}  "
                      f"({'good fit' if p > 0.05 else 'poor fit'})")
                print()
            except Exception:
                pass


def generate_figures(df, stats, prefix):
    if not _MPL:
        return

    for k, v in PLOT_STYLE.items():
        plt.rcParams[k] = v

    owd   = np.array(df['owd_ms'],   dtype=np.float64)
    jit   = np.array(df['jitter_ms'], dtype=np.float64)
    t_rel = np.array(df['t_rel'],     dtype=np.float64)

    # 1. OWD time series
    fig, ax = plt.subplots(figsize=(14, 4), dpi=120)
    ax.scatter(t_rel, owd, s=1.5, alpha=0.4, color=ACCENT, rasterized=True, label='OWD')
    if len(owd) >= 50:
        k     = np.ones(50) / 50
        rm    = np.convolve(owd, k, mode='valid')
        ax.plot(t_rel[49:], rm, color=ACCENT2, lw=1.5, label='50-packet rolling mean')
    for pct, lbl, clr in [(50, 'P50', ACCENT3), (95, 'P95', ACCENT2), (99, 'P99', RED)]:
        v = np.percentile(owd, pct)
        ax.axhline(v, color=clr, ls=':', lw=1.0, label=f'{lbl}={v:.1f}ms')
    ax.set_xlabel('Time since capture start (s)')
    ax.set_ylabel('OWD (ms)')
    ax.set_title('EEW UDP -- One-Way Delay Time Series', fontsize=13)
    ax.legend(fontsize=8, loc='upper right')
    ax.grid(True)
    fig.tight_layout()
    p = f"{prefix}_owd.png"
    fig.savefig(p, bbox_inches='tight')
    plt.close(fig)
    print(f"  Figure -> {p}")

    # 2. Histogram + fit
    fig, ax = plt.subplots(figsize=(9, 5), dpi=120)
    clipped = np.clip(owd, 0, np.percentile(owd, 99.5))
    ax.hist(clipped, bins=50, density=True, color=ACCENT, alpha=0.7,
            edgecolor='#161b22', label='Empirical density')
    if _SCIPY:
        try:
            pos = clipped[clipped > 0]
            if len(pos) > 10:
                sh, lo, sc = _ss.lognorm.fit(pos, floc=0)
                xf = np.linspace(pos.min(), pos.max(), 500)
                ax.plot(xf, _ss.lognorm.pdf(xf, sh, lo, sc),
                        color=ACCENT2, lw=2, label='Log-normal fit')
        except Exception:
            pass
    for pct, lbl, clr in [(50, 'P50', ACCENT3), (95, 'P95', ACCENT2), (99, 'P99', RED)]:
        v = np.percentile(owd, pct)
        ax.axvline(v, color=clr, ls='--', lw=1.2, label=f'{lbl}={v:.1f}ms')
    ax.set_xlabel('OWD (ms)')
    ax.set_ylabel('Probability density')
    ax.set_title('EEW UDP OWD Distribution', fontsize=13)
    ax.legend(fontsize=8)
    ax.grid(True)
    fig.tight_layout()
    p = f"{prefix}_hist.png"
    fig.savefig(p, bbox_inches='tight')
    plt.close(fig)
    print(f"  Figure -> {p}")

    # 3. CDF
    fig, ax = plt.subplots(figsize=(9, 5), dpi=120)
    sorted_owd = np.sort(owd)
    cdf = np.arange(1, len(sorted_owd) + 1) / len(sorted_owd)
    ax.plot(sorted_owd, cdf * 100, color=ACCENT, lw=2)
    for pct, lbl, clr in [(50, 'P50', ACCENT3), (95, 'P95', ACCENT2), (99, 'P99', RED)]:
        v = np.percentile(owd, pct)
        ax.axvline(v, color=clr, ls='--', lw=1.0, label=f'{lbl}={v:.1f}ms')
        ax.axhline(pct, color=clr, ls=':', lw=0.7, alpha=0.5)
    ax.set_xlabel('OWD (ms)')
    ax.set_ylabel('Cumulative Probability (%)')
    ax.set_title('EEW UDP OWD -- Empirical CDF', fontsize=13)
    ax.legend(fontsize=8)
    ax.set_ylim(0, 101)
    ax.grid(True)
    fig.tight_layout()
    p = f"{prefix}_cdf.png"
    fig.savefig(p, bbox_inches='tight')
    plt.close(fig)
    print(f"  Figure -> {p}")

    # 4. Jitter
    fig, ax = plt.subplots(figsize=(14, 3), dpi=120)
    ax.plot(t_rel, jit, color=ACCENT2, lw=0.8, alpha=0.8, label='EWMA Jitter (RFC 3550)')
    ax.axhline(np.mean(jit), color=ACCENT3, ls='--', lw=1.0, label=f'Mean = {np.mean(jit):.2f} ms')
    ax.set_xlabel('Time (s)')
    ax.set_ylabel('Jitter (ms)')
    ax.set_title('EEW UDP -- Packet Delay Variation (Jitter)', fontsize=13)
    ax.legend(fontsize=8)
    ax.grid(True)
    ax.set_xlim(0, max(t_rel))
    fig.tight_layout()
    p = f"{prefix}_jitter.png"
    fig.savefig(p, bbox_inches='tight')
    plt.close(fig)
    print(f"  Figure -> {p}")

    # 5. Box-per-minute
    df2 = df.copy()
    df2['minute'] = (df2['t_rel'] // 60).astype(int)
    groups = [g['owd_ms'].values for _, g in df2.groupby('minute') if len(g) > 5]
    if len(groups) >= 2:
        fig, ax = plt.subplots(figsize=(max(8, len(groups) * 0.8), 4), dpi=120)
        bp = ax.boxplot(groups, patch_artist=True, notch=False,
                        medianprops=dict(color=ACCENT3, lw=2),
                        flierprops=dict(marker='.', color=RED, alpha=0.3, ms=3))
        for patch in bp['boxes']:
            patch.set_facecolor('#1f2937')
            patch.set_edgecolor(ACCENT)
        ax.set_xticklabels([str(i) for i in range(len(groups))])
        ax.set_xlabel('Minute of capture')
        ax.set_ylabel('OWD (ms)')
        ax.set_title('OWD per Minute -- Box Plot', fontsize=13)
        ax.grid(True, axis='y')
        fig.tight_layout()
        p = f"{prefix}_boxplot.png"
        fig.savefig(p, bbox_inches='tight')
        plt.close(fig)
        print(f"  Figure -> {p}")

    print()


def main():
    parser = argparse.ArgumentParser(description="Offline EEW UDP latency analysis")
    parser.add_argument('csv', help="CSV file from udp_latency_analyzer.py")
    parser.add_argument('--clock-offset', type=float, default=0.0,
                        help="Clock offset to subtract from OWD (ms, from clock_offset_probe.py)")
    parser.add_argument('--trim-start', type=float, default=0.0,
                        help="Trim first N seconds (warmup)")
    parser.add_argument('--trim-end',   type=float, default=0.0,
                        help="Trim last N seconds (cooldown)")
    parser.add_argument('--output-dir', default='.', help="Output directory")
    args = parser.parse_args()

    print()
    print("=" * 60)
    print("  EEW UDP LATENCY -- OFFLINE ANALYSIS")
    print("=" * 60)
    print(f"  File   : {args.csv}")

    df    = load_csv(args.csv, args.clock_offset, args.trim_start, args.trim_end)
    stats = compute_stats(df['owd_ms'])
    print_report(df, stats, args)

    os.makedirs(args.output_dir, exist_ok=True)
    ts_str = datetime.now().strftime('%Y%m%d_%H%M%S')
    prefix = os.path.join(args.output_dir, f"analysis_{ts_str}")
    generate_figures(df, stats, prefix)
    print("  Done.")


if __name__ == '__main__':
    main()
