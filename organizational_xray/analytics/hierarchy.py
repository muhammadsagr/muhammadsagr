"""Hierarchy engine: builds the reporting graph and derives structural metrics.

Every active employee and every vacant position is a node; an edge
``manager -> employee`` exists when the manager record exists and is active (or
is a vacant position). Terminated managers do not create edges, so their teams
become disconnected and are reported as such.

All algorithms are linear (or near-linear) in the number of records, so the
engine stays fast for 10k+ employees, and none of them can loop forever on
circular data.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import networkx as nx
import numpy as np
import pandas as pd

from utils.config import (
    RS_CEO,
    RS_CIRCULAR,
    RS_DISCONNECTED,
    RS_DUPLICATE,
    RS_INACTIVE,
    RS_INVALID,
    RS_MISSING,
    RS_TERMINATED,
    RS_VACANT,
    RS_VALID,
)


@dataclass
class OrgModel:
    """Result of :func:`build_org_model`. ``df`` is the enriched dataset."""

    df: pd.DataFrame
    graph: nx.DiGraph
    ceo_id: str | None
    cycles: list[list[str]] = field(default_factory=list)
    root_candidates: list[str] = field(default_factory=list)

    # -------------------------------------------------------------- convenience
    @property
    def active(self) -> pd.DataFrame:
        return self.df[self.df["is_active"]]

    @property
    def managers(self) -> pd.DataFrame:
        return self.df[self.df["is_manager"]]

    def node(self, node_id: str) -> pd.Series | None:
        idx = self._index().get(node_id)
        return None if idx is None else self.df.loc[idx]

    def _index(self) -> dict:
        if not hasattr(self, "_idx_cache"):
            first = self.df[~self.df["is_duplicate_id"]]
            self._idx_cache = dict(zip(first["node_id"], first.index))
        return self._idx_cache

    def chain_up(self, node_id: str, max_steps: int = 200) -> list[str]:
        """Node IDs from ``node_id`` up the declared manager chain.

        Follows ``manager_id`` (not the graph) so broken chains are visible, and
        stops at a repeated node (cycle), a missing manager, or ``max_steps``.
        """
        chain, seen = [], set()
        idx = self._index()
        cur = node_id
        while cur and cur not in seen and len(chain) < max_steps:
            chain.append(cur)
            seen.add(cur)
            row_idx = idx.get(cur)
            if row_idx is None:
                break
            cur = self.df.at[row_idx, "manager_id"]
        if cur and cur in seen:
            chain.append(cur)  # show where the loop closes
        return chain

    def direct_report_ids(self, node_id: str, include_vacant: bool = False) -> list[str]:
        if node_id not in self.graph:
            return []
        out = []
        for child in self.graph.successors(node_id):
            if include_vacant or self.graph.nodes[child].get("active"):
                out.append(child)
        return out

    def subtree_ids(self, node_id: str, include_root: bool = True,
                    include_vacant: bool = False) -> list[str]:
        if node_id not in self.graph:
            return [node_id] if include_root else []
        ids = nx.descendants(self.graph, node_id)
        if not include_vacant:
            ids = {i for i in ids if self.graph.nodes[i].get("active")}
        if include_root:
            ids = ids | {node_id}
        return list(ids)


# ============================================================================ build
def _find_ceo(df: pd.DataFrame, graph: nx.DiGraph, in_cycle: set[str]) -> tuple[str | None, list]:
    roots = df[df["is_active"] & df["manager_id"].eq("") & ~df["node_id"].isin(in_cycle)]
    candidates = roots["node_id"].tolist()
    if not candidates:
        return None, []
    if len(candidates) == 1:
        return candidates[0], candidates
    # Prefer the lowest job level (0 = CEO), then the largest organisation.
    sizes = {c: len(nx.descendants(graph, c)) for c in candidates}
    title_ceo = roots["job_title"].str.contains(r"\b(?:CEO|Chief Executive)", case=False, regex=True)
    ranked = roots.assign(
        _lvl=roots["job_level"].fillna(99),
        _ceo=~title_ceo,
        _size=[-sizes[c] for c in roots["node_id"]],
    ).sort_values(["_lvl", "_ceo", "_size"])
    return ranked["node_id"].iloc[0], candidates


def build_org_model(df_norm: pd.DataFrame) -> OrgModel:
    """Build the reporting graph and enrich every record with structural metrics.

    Input must come from :func:`data.loader.normalize`.
    """
    df = df_norm.copy()
    base = df[~df["is_duplicate_id"]]
    status_of = dict(zip(base["node_id"], base["employment_status"]))
    active_of = dict(zip(base["node_id"], base["is_active"]))
    vacant_of = dict(zip(base["node_id"], base["is_vacant"]))
    in_graph = base[base["is_active"] | base["is_vacant"]]

    g = nx.DiGraph()
    for nid, act in zip(in_graph["node_id"], in_graph["is_active"]):
        g.add_node(nid, active=bool(act))
    for nid, mid in zip(in_graph["node_id"], in_graph["manager_id"]):
        if mid and mid in g:  # manager exists and is active / vacant position
            g.add_edge(mid, nid)

    # ---------------------------------------------------------------- cycles
    cycles: list[list[str]] = []
    in_cycle: set[str] = set()
    for comp in nx.strongly_connected_components(g):
        if len(comp) > 1:
            cyc = next(nx.simple_cycles(g.subgraph(comp)))
            cycles.append(_rotate_cycle(cyc))
            in_cycle |= set(comp)
    for n in list(nx.nodes_with_selfloops(g)):
        cycles.append([n])
        in_cycle.add(n)

    ceo_id, root_candidates = _find_ceo(base, g, in_cycle)

    # ---------------------------------------------------------------- depth (BFS from CEO)
    depth: dict[str, int] = {}
    if ceo_id is not None:
        tree = g.copy()
        tree.remove_edges_from(nx.selfloop_edges(tree))
        depth = nx.single_source_shortest_path_length(tree, ceo_id)

    # ---------------------------------------------------------------- reporting status
    def status(row) -> str:
        nid, mid = row.node_id, row.manager_id
        if row.is_duplicate_id:
            return RS_DUPLICATE
        if row.is_vacant:
            return RS_VACANT
        if not row.is_active:
            return RS_INACTIVE
        if nid == ceo_id:
            return RS_CEO
        if nid in in_cycle:
            return RS_CIRCULAR
        if not mid:
            return RS_MISSING
        if mid not in status_of:
            return RS_INVALID
        if not active_of.get(mid) and not vacant_of.get(mid):
            return RS_TERMINATED
        return RS_VALID if nid in depth else RS_DISCONNECTED

    df["reporting_status"] = [status(r) for r in df.itertuples(index=False)]
    df["depth"] = df["node_id"].map(depth).astype("float")
    df.loc[df["is_duplicate_id"], "depth"] = np.nan
    df["manager_status"] = df["manager_id"].map(status_of).fillna("")

    # ---------------------------------------------------------------- spans & subtree sizes
    active_nodes = {n for n, a in g.nodes(data="active") if a}
    direct_active: dict[str, int] = {}
    direct_vacant: dict[str, int] = {}
    for u, v in g.edges():
        if u == v:
            continue
        if v in active_nodes:
            direct_active[u] = direct_active.get(u, 0) + 1
        else:
            direct_vacant[u] = direct_vacant.get(u, 0) + 1
    total = _subtree_active_counts(g, active_nodes, in_cycle)

    df["direct_reports"] = df["node_id"].map(direct_active).fillna(0).astype(int)
    df["vacant_direct_positions"] = df["node_id"].map(direct_vacant).fillna(0).astype(int)
    df["total_reports"] = df["node_id"].map(total).fillna(0).astype(int)
    not_node = ~df["is_active"]
    df.loc[not_node & ~df["is_vacant"], ["direct_reports", "vacant_direct_positions",
                                         "total_reports"]] = 0
    df.loc[df["is_duplicate_id"], ["direct_reports", "vacant_direct_positions",
                                   "total_reports"]] = 0
    df["is_manager"] = df["is_active"] & df["direct_reports"].gt(0)
    df["layer"] = df["depth"].map(lambda d: f"Layer {int(d)}" if pd.notna(d) else "Unreachable")

    return OrgModel(df=df, graph=g, ceo_id=ceo_id, cycles=cycles,
                    root_candidates=root_candidates)


def _rotate_cycle(cyc: list[str]) -> list[str]:
    """Express the loop in reporting order (employee -> manager -> ...), starting at
    its smallest id so results are deterministic. Graph edges run manager -> employee."""
    cyc = list(reversed(cyc))
    i = cyc.index(min(cyc))
    return cyc[i:] + cyc[:i]


def _subtree_active_counts(g: nx.DiGraph, active_nodes: set[str],
                           in_cycle: set[str]) -> dict[str, int]:
    """Number of active descendants per node (excluding itself).

    Cycles are condensed first so the computation always terminates.
    """
    cond = nx.condensation(g)
    members = cond.graph["mapping"]  # node -> component id
    comp_active = {c: sum(1 for n in data["members"] if n in active_nodes)
                   for c, data in cond.nodes(data=True)}
    below: dict[int, int] = {}
    for c in reversed(list(nx.topological_sort(cond))):
        below[c] = sum(below[s] + comp_active[s] for s in cond.successors(c))
    out = {}
    for n in g.nodes:
        c = members[n]
        own = comp_active[c] - (1 if n in active_nodes else 0)
        out[n] = below[c] + own  # members of the same cycle count as reports
    return out


# ============================================================================ queries
def depth_stats(model: OrgModel, df: pd.DataFrame | None = None) -> dict:
    """Min / max / mean / median depth of active employees (CEO excluded)."""
    d = (df if df is not None else model.df)
    d = d[d["is_active"] & d["depth"].notna() & d["node_id"].ne(model.ceo_id)]["depth"]
    if d.empty:
        return {"min": np.nan, "max": np.nan, "mean": np.nan, "median": np.nan, "count": 0}
    return {"min": int(d.min()), "max": int(d.max()), "mean": float(d.mean()),
            "median": float(d.median()), "count": int(d.size)}


def layer_count(df: pd.DataFrame) -> int:
    """Number of structural layers = distinct depths among reachable active employees."""
    d = df.loc[df["is_active"], "depth"].dropna()
    return int(d.nunique()) if not d.empty else 0


def longest_chains(model: OrgModel, top: int = 10, df: pd.DataFrame | None = None) -> pd.DataFrame:
    """The deepest reporting chains (one per leaf employee), with the path."""
    d = df if df is not None else model.df
    d = d[d["is_active"] & d["depth"].notna()].sort_values(
        ["depth", "node_id"], ascending=[False, True]).head(top)
    names = dict(zip(model.df["node_id"], model.df["job_title"]))
    rows = []
    for r in d.itertuples():
        chain = model.chain_up(r.node_id)
        rows.append({
            "employee_id": r.node_id,
            "employee_name": r.employee_name,
            "job_title": r.job_title,
            "department": r.department,
            "depth": int(r.depth),
            "chain": " → ".join(f"{names.get(n, n)}" for n in reversed(chain)),
            "chain_ids": " → ".join(reversed(chain)),
        })
    return pd.DataFrame(rows)


def department_heads(model: OrgModel) -> dict[str, str]:
    """Department -> node_id of its head (top-most active member, largest team)."""
    df = model.df
    act = df[df["is_active"] & df["department"].ne("")]
    dept_of = dict(zip(df["node_id"], df["department"]))
    heads: dict[str, str] = {}
    for dept, grp in act.groupby("department"):
        tops = grp[grp["manager_id"].map(dept_of).ne(dept)]
        if tops.empty:
            tops = grp
        tops = tops.sort_values(["depth", "total_reports"], ascending=[True, False],
                                na_position="last")
        heads[dept] = tops["node_id"].iloc[0]
    return heads


def level_depth_matrix(df: pd.DataFrame) -> pd.DataFrame:
    """Cross-tab of declared Job Level vs measured depth (active employees)."""
    a = df[df["is_active"] & df["depth"].notna() & df["job_level"].notna()]
    if a.empty:
        return pd.DataFrame()
    return pd.crosstab(a["job_level"].astype(int), a["depth"].astype(int))
