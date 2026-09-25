"""Organisation network (Employee -> Manager) with NetworkX + Plotly.

The layout is a deterministic "tidy tree": leaves are placed left-to-right in
DFS order and each manager is centred above its team, y = depth. It never
recurses (safe on circular data) and is linear in the number of nodes.
"""
from __future__ import annotations

from dataclasses import dataclass

import networkx as nx
import numpy as np
import pandas as pd
import plotly.graph_objects as go

from analytics.hierarchy import OrgModel
from visualization.theme import GRID, MUTED, SEQUENTIAL, SPAN_COLORS, style

SCOPES = ["Entire Organization", "Business Unit", "Division", "Department", "Specific Manager"]


@dataclass
class NetworkSelection:
    nodes: list[str]
    total_in_scope: int
    truncated: bool
    levels_shown: int | None


def select_nodes(model: OrgModel, scope: str, value: str | None = None,
                 managers_only: bool = False, max_levels: int | None = None,
                 max_nodes: int = 600, include_vacant: bool = False) -> NetworkSelection:
    """Pick the nodes to draw for a scope, keeping the chart readable."""
    df = model.df
    base = df[df["is_active"] | (df["is_vacant"] & include_vacant)]
    base = base[~base["is_duplicate_id"]]
    if scope == "Entire Organization":
        ids = set(base["node_id"])
    elif scope == "Business Unit":
        ids = set(base.loc[base["business_unit"].eq(value), "node_id"])
    elif scope == "Division":
        ids = set(base.loc[base["division"].eq(value), "node_id"])
    elif scope == "Department":
        ids = set(base.loc[base["department"].eq(value), "node_id"])
    elif scope == "Specific Manager":
        ids = set(model.subtree_ids(value, include_root=True, include_vacant=include_vacant))
    else:
        raise ValueError(scope)
    if managers_only:
        mgr = set(df.loc[df["is_manager"], "node_id"])
        keep = ids & mgr
        if scope == "Specific Manager" and value:
            keep.add(value)
        ids = keep
    total = len(ids)

    # Relative depth inside the selection (roots = parent outside the selection)
    rel = _relative_depth(model.graph, ids, root_hint=value if scope == "Specific Manager" else None)
    levels = max_levels
    if levels is not None:
        ids = {n for n in ids if rel.get(n, 0) <= levels}
    truncated = False
    if len(ids) > max_nodes:
        truncated = True
        by_level = pd.Series({n: rel.get(n, 0) for n in ids})
        counts = by_level.value_counts().sort_index().cumsum()
        allowed = counts[counts <= max_nodes]
        lvl = int(allowed.index.max()) if len(allowed) else 0
        ids = set(by_level[by_level <= lvl].index)
        if len(ids) > max_nodes:  # a single very wide level
            ids = set(sorted(ids, key=lambda n: (by_level[n], n))[:max_nodes])
        levels = lvl
    return NetworkSelection(sorted(ids), total, truncated, levels)


def _relative_depth(g: nx.DiGraph, ids: set[str], root_hint: str | None = None) -> dict[str, int]:
    roots = [n for n in ids if not any(p in ids for p in g.predecessors(n))] if ids else []
    if root_hint and root_hint in ids and root_hint not in roots:
        roots.append(root_hint)  # e.g. a manager inside a reporting loop
    depth: dict[str, int] = {}
    frontier = sorted(roots)
    for r in frontier:
        depth[r] = 0
    while frontier:
        nxt = []
        for n in frontier:
            for c in g.successors(n) if n in g else []:
                if c in ids and c not in depth:
                    depth[c] = depth[n] + 1
                    nxt.append(c)
        frontier = nxt
    for n in ids:  # anything unreached (pure cycles) sits at level 0
        depth.setdefault(n, 0)
    return depth


def tree_layout(g: nx.DiGraph, ids: list[str]) -> dict[str, tuple[float, float]]:
    idset = set(ids)
    rel = _relative_depth(g, idset)
    children = {n: sorted(c for c in g.successors(n) if c in idset and rel.get(c) == rel[n] + 1)
                for n in ids if n in g}
    roots = sorted(n for n in ids if rel[n] == 0)
    x: dict[str, float] = {}
    counter = 0.0
    for root in roots:
        stack = [(root, False)]
        while stack:
            node, done = stack.pop()
            kids = children.get(node, [])
            if done or not kids:
                if kids:
                    x[node] = float(np.mean([x[k] for k in kids if k in x]))
                else:
                    x[node] = counter
                    counter += 1
                continue
            stack.append((node, True))
            for k in reversed(kids):
                if k not in x:
                    stack.append((k, False))
        counter += 0.5  # gap between separate trees
    return {n: (x.get(n, 0.0), -float(rel[n])) for n in ids}


def network_figure(model: OrgModel, sel: NetworkSelection, color_by: str = "span",
                   low: int = 3, high: int = 12, height: int = 650) -> go.Figure:
    ids = sel.nodes
    if not ids:
        return style(go.Figure(), height=200)
    pos = tree_layout(model.graph, ids)
    df = model.df.set_index("node_id")
    df = df[~df.index.duplicated()]
    idset = set(ids)

    ex, ey = [], []
    for u, v in model.graph.edges():
        if u in idset and v in idset and u != v:
            (x0, y0), (x1, y1) = pos[u], pos[v]
            ym = (y0 + y1) / 2
            ex += [x0, x0, x1, x1, None]
            ey += [y0, ym, ym, y1, None]
    fig = go.Figure(go.Scatter(x=ex, y=ey, mode="lines", line=dict(color=GRID, width=1),
                               hoverinfo="skip", showlegend=False))

    rows = df.loc[ids]
    xs = [pos[n][0] for n in ids]
    ys = [pos[n][1] for n in ids]
    tot = rows["total_reports"].clip(lower=0).values.astype(float)
    size = 8 + 16 * np.sqrt(tot / tot.max()) if tot.max() > 0 else np.full(len(ids), 8.0)
    hover = [
        f"<b>{n}</b> – {r.employee_name or '(Vacant)'}<br>{r.job_title}<br>{r.department}"
        f"<br>Direct reports: {int(r.direct_reports)} · Total: {int(r.total_reports)}"
        f"<br>Depth: {'' if pd.isna(r.depth) else int(r.depth)} · {r.reporting_status}"
        for n, r in zip(ids, rows.itertuples())
    ]
    if color_by == "span":
        def cat(r):
            if r.is_vacant:
                return "Vacant"
            if not r.is_manager:
                return "Individual contributor"
            if r.direct_reports <= low:
                return "Low"
            return "High" if r.direct_reports > high else "Within Range"
        cats = [cat(r) for r in rows.itertuples()]
        palette = dict(SPAN_COLORS, **{"Individual contributor": "#c3c2b7", "Vacant": "#ffffff"})
        for c in ["Low", "Within Range", "High", "Individual contributor", "Vacant"]:
            idx = [i for i, k in enumerate(cats) if k == c]
            if not idx:
                continue
            fig.add_scatter(x=[xs[i] for i in idx], y=[ys[i] for i in idx], mode="markers",
                            name=f"Span: {c}" if c in SPAN_COLORS else c,
                            marker=dict(size=[size[i] for i in idx], color=palette[c],
                                        line=dict(width=1.5, color=MUTED if c == "Vacant" else "white")),
                            text=[hover[i] for i in idx], hovertemplate="%{text}<extra></extra>")
    else:  # depth (sequential)
        d = rows["depth"].fillna(-1).values
        fig.add_scatter(x=xs, y=ys, mode="markers", name="Depth",
                        marker=dict(size=size, color=d, colorscale=[[i / (len(SEQUENTIAL) - 1), c]
                                                                     for i, c in enumerate(SEQUENTIAL)],
                                    showscale=True, colorbar=dict(title="Depth", thickness=10),
                                    line=dict(width=1, color="white")),
                        text=hover, hovertemplate="%{text}<extra></extra>")
    # Direct labels for the top of the tree only (keeps the chart legible)
    top_ids = [n for n in ids if pos[n][1] == 0 or (len(ids) <= 60)]
    if len(top_ids) <= 40:
        fig.add_scatter(x=[pos[n][0] for n in top_ids], y=[pos[n][1] + 0.18 for n in top_ids],
                        mode="text", text=[str(df.at[n, "job_title"])[:28] for n in top_ids],
                        textfont=dict(size=10, color=MUTED), hoverinfo="skip", showlegend=False)
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    fig.update_layout(dragmode="pan")
    return style(fig, height=height)
