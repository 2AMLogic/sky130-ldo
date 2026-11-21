"""Block-independent reproduction: resistance-graph build caps are unreachable
from the CLI and mark ordinary rail geometry graph_too_large.

Three synthetic cases against klayout_tools.extract_resistance_graph at the
pinned build, each repeated with the private keyword-only knobs raised,
showing the params exist in Python but no `klt extract`/`klt pex` flag reaches
them (unlike `klt power`'s `max_decomposition_cells` spec field, #3124).

Run: uv run --with 'klayout-tools @ git+<pin>' python repro_graph_caps.py
"""

import klayout.db as kdb
from klayout_tools.extract_resistance_graph import (
    DEFAULT_MAX_DECOMPOSITION_CELLS,
    MAX_GRAPH_EDGES,
    MAX_GRAPH_NODES,
    MAX_GRAPH_TERMINALS,
    PortInput,
    RoleInput,
    build_resistance_graph,
)

DBU = 0.001  # um per dbu step


def summarize(tag, graph):
    print(f"{tag}: status={graph.status} nodes={len(graph.nodes)} edges={len(graph.edges)}")
    for diag in graph.diagnostics:
        print(f"    {diag.code}: {diag.message}")


# -- Case A: terminal cap ---------------------------------------------------
# One plain 20 x 4 um metal1 rectangle with 1 um-wide terminal ports spaced
# along it. 64 ports solve; 65 mark the whole net unsupported.

def case_a(n_ports, max_terminals=MAX_GRAPH_TERMINALS):
    poly = kdb.Polygon(kdb.Box(0, 0, 20000, 4000))
    role = RoleInput("metal1", 0.125, (poly,))
    ports = [
        PortInput(f"t{i:03d}", (("metal1", kdb.Box(i * 300, 0, i * 300 + 1000, 4000)),))
        for i in range(n_ports)
    ]
    return build_resistance_graph([role], ports, [], DBU, max_terminals=max_terminals)


# -- Case B: decomposition-cell cap -----------------------------------------
# One metal1 plate with a 100 x 10 lattice of 1 x 1 um holes (the geometry
# class of a strapped/poured power rail: metal kept only where straps run).
# Two terminal ports on opposite corners. The hole edges force a
# decomposition grid over the 4096-cell cap, so the whole net is unsupported.

def case_b(cols=100, rows=10, max_cells=DEFAULT_MAX_DECOMPOSITION_CELLS):
    region = kdb.Region(kdb.Box(0, 0, (cols + 1) * 2000, (rows + 1) * 2000))
    for i in range(cols):
        for j in range(rows):
            hole = kdb.Box(i * 2000 + 500, j * 2000 + 500, i * 2000 + 1500, j * 2000 + 1500)
            region -= kdb.Region(hole)
    poly = next(region.merged().each())
    role = RoleInput("metal1", 0.125, (poly,))
    ports = [
        PortInput("A", (("metal1", kdb.Box(0, 0, 1000, 1000)),)),
        PortInput("B", (("metal1", kdb.Box(cols * 2000 + 1000, rows * 2000 + 1000, (cols + 1) * 2000, (rows + 1) * 2000)),)),
    ]
    return build_resistance_graph([role], ports, [], DBU, max_cells=max_cells)


print(f"caps in this build: MAX_GRAPH_TERMINALS={MAX_GRAPH_TERMINALS} "
      f"MAX_GRAPH_NODES={MAX_GRAPH_NODES} MAX_GRAPH_EDGES={MAX_GRAPH_EDGES} "
      f"DEFAULT_MAX_DECOMPOSITION_CELLS={DEFAULT_MAX_DECOMPOSITION_CELLS}")
print()
summarize("A1: 20x4 um plate, 64 terminal ports", case_a(64))
summarize("A2: same plate, 65 terminal ports", case_a(65))
summarize("A3: same plate, 65 ports, max_terminals=128", case_a(65, max_terminals=128))
print()
summarize("B1: 100x10-hole plate, 2 terminals, default cap", case_b())
summarize("B2: same plate, 2 terminals, max_cells=65536", case_b(max_cells=65536))
