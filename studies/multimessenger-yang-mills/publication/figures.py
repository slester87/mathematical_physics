"""Plot the benchmark energies and tabulate predictive tests from the reference CSV."""
from collections import defaultdict
import csv
from html import escape
import json
import math


def spectrum(groups, window):
    energies = [float(row["line_energy_MeV"]) for rows in groups.values() for row in rows]
    lower = math.floor(min(*energies, *window) * 10)
    upper = math.ceil(max(*energies, *window) * 10)
    left, right = 60, 488
    def x(energy):
        return left + (energy * 10 - lower) * (right - left) / (upper - lower)

    axis = 45 + 47 * len(groups)
    bottom = axis + 48
    lo, hi = map(x, window)
    drawing = [f'<svg class="chart" viewBox="0 0 508 {bottom}" role="img" aria-label="Mean line energies for each confinement scale and gauge group, with the detector count window shaded.">',
               f'<rect class="band" x="{lo:.2f}" y="24" width="{hi-lo:.2f}" height="{axis-24}"/>',
               f'<text class="window-label" x="{(lo+hi)/2:.2f}" y="16" text-anchor="middle">Count window</text>']
    for i, (group, rows) in enumerate(groups.items()):
        y = 57 + 47*i
        drawing.extend([f'<line class="guide" x1="{left}" x2="{right}" y1="{y}" y2="{y}"/>',
                        f'<text class="group" x="{left-10}" y="{y+5}" text-anchor="end">{escape(group)}</text>'])
        for row in rows:
            pos = x(float(row["line_energy_MeV"]))
            scale = float(row["sqrt_sigma_MeV"])
            excluded = row["status"] == "excluded_point"
            if excluded:
                mark = f'<path class="excluded" d="M {pos:.2f} {y-5.5} l 5.5 5.5 -5.5 5.5 -5.5 -5.5 Z"/>'
            else:
                mark = f'<circle class="retained" cx="{pos:.2f}" cy="{y}" r="4"/>'
            drawing.extend([mark, f'<text class="scale" x="{pos:.2f}" y="{y-9}" text-anchor="middle">{scale:.1f}</text>'])
    drawing.append(f'<line class="axis-line" x1="{left}" x2="{right}" y1="{axis}" y2="{axis}"/>')
    for tenth in range(lower, upper + 1):
        pos = x(tenth / 10)
        drawing.extend([f'<line class="axis-line" x1="{pos:.2f}" x2="{pos:.2f}" y1="{axis}" y2="{axis+4}"/>',
                        f'<text class="axis" x="{pos:.2f}" y="{axis+20}" text-anchor="middle">{tenth/10:.1f}</text>'])
    drawing.extend([f'<text class="axis" x="{(left+right)/2}" y="{bottom-3}" text-anchor="middle">Predicted photon energy (MeV)</text>', '</svg>'])
    return (f'<figure><p class="eyebrow">Figure 1</p><p class="chart-title">Line energies by gauge group</p>' +
            ''.join(drawing) + f'<figcaption>The shaded band spans {window[0]:.2f}–{window[1]:.2f} MeV. Labels give '
            '√σ in MeV. <span class="symbol">◆</span> Excluded benchmark &nbsp; ○ Retained benchmark.</figcaption></figure>')


def format_counts(value):
    if value >= 0.001:
        return f"{value:.2f}"
    mantissa, exponent = f"{value:.1e}".split("e")
    return f'{mantissa} × 10<sup>{int(exponent):d}</sup>'


def results_table(groups):
    rows = ['<div class="table-scroll" tabindex="0" role="region" aria-label="Benchmark results"><table aria-label="All benchmark points"><thead><tr>'
            '<th scope="col">Group</th><th scope="col">√σ<br>MeV</th><th scope="col">Line energy<br>MeV</th>'
            '<th scope="col">Expected<br>signal counts</th><th scope="col">Lower tail<br>p</th><th scope="col">Decision</th></tr></thead>']
    for group, points in groups.items():
        rows.append('<tbody>')
        for i, point in enumerate(points):
            status = {"excluded_point":'<span class="flag">◆ Excluded</span>', "retained_point":"○ Retained"}[point["status"]]
            group_cell = f'<th scope="rowgroup" rowspan="{len(points)}">{escape(group)}</th>' if i == 0 else ""
            rows.append(f'<tr>{group_cell}<td class="num">{float(point["sqrt_sigma_MeV"]):.1f}</td>'
                        f'<td class="num">{float(point["line_energy_MeV"]):.3f}</td>'
                        f'<td class="num">{format_counts(float(point["mean_signal_counts"]))}</td>'
                        f'<td class="num">{float(point["lower_tail"]):.4f}</td><td class="decision">{status}</td></tr>')
        rows.append('</tbody>')
    return ''.join(rows) + '</table></div>'


def render(study):
    groups = defaultdict(list)
    with (study / "example/results.csv").open(newline="") as stream:
        for row in csv.DictReader(stream):
            groups[row["group"]].append(row)
    event = json.loads((study / "example/event.json").read_text())
    chart = spectrum(groups, event["sensor"]["count_window_MeV"])
    return {"cover": chart, "figure": chart, "table": results_table(groups)}
