"""Mermaid flowchart and graph parser for Excalidraw MCP."""

import re
from typing import Literal
from .contracts import GraphCluster, GraphEdge, GraphNode, LayoutType, Direction
from .errors import SceneError

# Node shape patterns in order of precedence (more specific delimiters first)
NODE_PATTERNS = [
    # Double circle: id(((label))) or id((label))
    (re.compile(r"^([A-Za-z0-9_-]+)\(\(\((.*?)\)\)\)$"), "ellipse"),
    (re.compile(r"^([A-Za-z0-9_-]+)\(\((.*?)\)\)$"), "ellipse"),
    # Cylinder: id[(label)]
    (re.compile(r"^([A-Za-z0-9_-]+)\[\((.*?)\)\]$"), "rectangle"),
    # Stadium: id([label])
    (re.compile(r"^([A-Za-z0-9_-]+)\(\[(.*?)\]\)$"), "rectangle"),
    # Subroutine: id[[label]]
    (re.compile(r"^([A-Za-z0-9_-]+)\[\[(.*?)\]\]$"), "rectangle"),
    # Diamond: id{label}
    (re.compile(r"^([A-Za-z0-9_-]+)\{(.*?)\}$"), "diamond"),
    # Rounded: id(label)
    (re.compile(r"^([A-Za-z0-9_-]+)\((.*?)\)$"), "rectangle"),
    # Rectangle: id[label]
    (re.compile(r"^([A-Za-z0-9_-]+)\[(.*?)\]$"), "rectangle"),
    # Plain identifier: id
    (re.compile(r"^([A-Za-z0-9_-]+)$"), "rectangle"),
]

# Pattern to identify and split edges in a line
EDGE_SPLIT_PATTERN = re.compile(
    r"""
    \s*
    (
        -->\|([^|]+)\|            # -->|label|
        |
        --\s*([^-\n]+?)\s*-->     # -- label -->
        |
        -->                       # -->
        |
        ---\|([^|]+)\|            # ---|label|
        |
        --\s*([^-\n]+?)\s*---     # -- label ---
        |
        ---                       # ---
        |
        -\.->\|([^|]+)\|          # -.->|label|
        |
        -\.-\s*([^.\n]+?)\s*\.->  # -.- label .->
        |
        -\.->                     # -.->
        |
        ==>\|([^|]+)\|            # ==>|label|
        |
        ==\s*([^=\n]+?)\s*==>     # == label ==>
        |
        ==>                       # ==>
    )
    \s*
    """,
    re.VERBOSE,
)


def _clean_label(label: str) -> str:
    cleaned = label.strip()
    if (cleaned.startswith('"') and cleaned.endswith('"')) or (
        cleaned.startswith("'") and cleaned.endswith("'")
    ):
        cleaned = cleaned[1:-1].strip()
    # Unescape common escaped chars
    cleaned = cleaned.replace("\\n", "\n").replace('\\"', '"')
    return cleaned


def _parse_node_token(token: str) -> tuple[str, str, str]:
    """Parse a node token into (node_id, label, shape)."""
    token = token.strip()
    for pattern, shape in NODE_PATTERNS:
        match = pattern.match(token)
        if match:
            node_id = match.group(1).strip()
            if len(match.groups()) > 1 and match.group(2) is not None:
                raw_label = match.group(2)
                label = _clean_label(raw_label)
                if not label:
                    label = node_id
            else:
                label = node_id
            return node_id, label, shape

    # Fallback: standalone identifier token (must be full match)
    m = re.fullmatch(r"^([A-Za-z0-9_-]+)$", token.strip())
    if m:
        nid = m.group(1)
        return nid, nid, "rectangle"
    raise SceneError(f"Cannot parse node syntax: '{token}'")


def parse_mermaid(
    mermaid_code: str,
    direction: Direction | None = None,
    layout: LayoutType = "layered",
) -> tuple[list[GraphNode], list[GraphEdge], list[GraphCluster], Direction, LayoutType]:
    """Parse Mermaid graph or flowchart code into GraphNodes, GraphEdges, and GraphClusters."""
    if not isinstance(mermaid_code, str) or not mermaid_code.strip():
        raise SceneError("Mermaid code cannot be empty")

    raw_lines = mermaid_code.strip().splitlines()
    lines = []
    for line in raw_lines:
        line_str = line.strip()
        # Strip markdown fences
        if line_str.startswith("```"):
            continue
        # Strip Mermaid comments
        if line_str.startswith("%%"):
            continue
        if line_str:
            lines.append(line_str)

    if not lines:
        raise SceneError("Mermaid code contains no content")

    unsupported_match = re.match(
        r"^(?:sequenceDiagram|classDiagram|stateDiagram(?:-v2)?|erDiagram|gantt|gitGraph|pie|journey|mindmap|quadrantChart|C4Context|C4Container|C4Component)\b",
        lines[0],
        re.IGNORECASE,
    )
    if unsupported_match:
        diagram_type = unsupported_match.group(0)
        raise SceneError(
            f"Mermaid '{diagram_type}' diagrams are not supported yet. Only flowchart and graph diagrams ('flowchart TD', 'flowchart LR', 'graph TD', 'graph LR') can be rendered."
        )

    detected_direction: Direction = "horizontal"
    start_idx = 0

    # Header check
    header_match = re.match(
        r"^(?:flowchart|graph)\s+(TD|TB|LR|RL|BT)(?:\s*;|\s*$)?", lines[0], re.IGNORECASE
    )
    if header_match:
        dir_code = header_match.group(1).upper()
        if dir_code in ("TD", "TB", "BT"):
            detected_direction = "vertical"
        else:
            detected_direction = "horizontal"
        start_idx = 1
    elif re.match(r"^(?:flowchart|graph)(?:\s*;|\s*$)?", lines[0], re.IGNORECASE):
        detected_direction = "horizontal"
        start_idx = 1

    final_direction: Direction = direction if direction is not None else detected_direction

    nodes_dict: dict[str, dict] = {}
    edges_list: list[GraphEdge] = []
    clusters_dict: dict[str, GraphCluster] = {}
    subgraph_stack: list[str] = []

    subgraph_header_pat = re.compile(
        r"""^subgraph\s+
            (?:
                "([^"]+)"                   # subgraph "Title"
                |
                ([A-Za-z0-9_-]+)            # subgraph id
                (?:\s*\[\s*(.*?)\s*\])?     # [Title]
            )
        """,
        re.VERBOSE | re.IGNORECASE,
    )

    for line_idx in range(start_idx, len(lines)):
        line = lines[line_idx].rstrip(";")
        line_clean = line.strip()

        if not line_clean:
            continue

        # Check for subgraph end
        if line_clean.lower() == "end":
            if subgraph_stack:
                subgraph_stack.pop()
            continue

        # Check for subgraph start
        sub_match = subgraph_header_pat.match(line_clean)
        if sub_match:
            quoted_title = sub_match.group(1)
            sub_id = sub_match.group(2)
            sub_bracket_label = sub_match.group(3)

            if quoted_title is not None:
                cluster_id = re.sub(r"[^A-Za-z0-9_-]", "_", quoted_title).strip("_")
                cluster_label = quoted_title
            else:
                cluster_id = sub_id
                cluster_label = sub_bracket_label if sub_bracket_label else sub_id

            cluster_id = cluster_id or f"cluster_{len(clusters_dict) + 1}"
            cluster_label = _clean_label(cluster_label) or cluster_id

            if cluster_id not in clusters_dict:
                clusters_dict[cluster_id] = GraphCluster(id=cluster_id, label=cluster_label)

            subgraph_stack.append(cluster_id)
            continue

        # Check for classDef, style, click, etc. (ignore directive styling safely)
        if re.match(r"^(?:classDef|class|style|click|linkStyle)\s+", line_clean):
            continue

        current_cluster = subgraph_stack[-1] if subgraph_stack else None

        # Check if line contains edge connections
        edge_matches = list(EDGE_SPLIT_PATTERN.finditer(line_clean))
        if edge_matches:
            # We have one or more edge connectors: split tokens
            tokens = []
            labels = []
            last_end = 0
            for em in edge_matches:
                node_part = line_clean[last_end : em.start()].strip()
                if node_part:
                    tokens.append(node_part)
                # Determine label from groups
                # Groups: 1=full, 2=-->|label|, 3=-- label -->, 4=---|label|, 5=-- label ---,
                # 6=-.->|label|, 7=-.- label .->, 8===>|label|, 9=== label ==>
                label_candidate = ""
                for g in em.groups()[1:]:
                    if g:
                        label_candidate = _clean_label(g)
                        break
                labels.append(label_candidate)
                last_end = em.end()

            tail_part = line_clean[last_end:].strip()
            if tail_part:
                tokens.append(tail_part)

            # Register each stage (which can have multiple nodes separated by &)
            stage_nodes = []
            for tok in tokens:
                sub_toks = [p.strip() for p in re.split(r"\s+&\s+", tok) if p.strip()]
                parsed_stage = []
                for sub_tok in sub_toks:
                    nid, nlabel, nshape = _parse_node_token(sub_tok)
                    if nid not in nodes_dict:
                        nodes_dict[nid] = {
                            "id": nid,
                            "label": nlabel,
                            "shape": nshape,
                            "cluster": current_cluster,
                        }
                    else:
                        if nlabel != nid:
                            nodes_dict[nid]["label"] = nlabel
                        if nshape != "rectangle":
                            nodes_dict[nid]["shape"] = nshape
                        if current_cluster and not nodes_dict[nid].get("cluster"):
                            nodes_dict[nid]["cluster"] = current_cluster
                    parsed_stage.append(nid)
                stage_nodes.append(parsed_stage)

            # Link consecutive stages with edges
            for i in range(len(stage_nodes) - 1):
                sources = stage_nodes[i]
                targets = stage_nodes[i + 1]
                edge_lbl = labels[i] if i < len(labels) else ""
                for src in sources:
                    for tgt in targets:
                        if src != tgt:
                            edges_list.append(GraphEdge(source=src, target=tgt, label=edge_lbl))
        else:
            # Isolated node definition or multiple separated nodes
            # If line has multiple nodes (e.g. A[Label] & B[Label])
            parts = re.split(r"\s+&\s+", line_clean)
            for part in parts:
                part = part.strip()
                if part:
                    nid, nlabel, nshape = _parse_node_token(part)
                    if nid not in nodes_dict:
                        nodes_dict[nid] = {
                            "id": nid,
                            "label": nlabel,
                            "shape": nshape,
                            "cluster": current_cluster,
                        }
                    else:
                        if nlabel != nid:
                            nodes_dict[nid]["label"] = nlabel
                        if nshape != "rectangle":
                            nodes_dict[nid]["shape"] = nshape
                        if current_cluster and not nodes_dict[nid].get("cluster"):
                            nodes_dict[nid]["cluster"] = current_cluster

    if not nodes_dict:
        raise SceneError("No valid nodes found in Mermaid code")

    graph_nodes = [
        GraphNode(
            id=d["id"],
            label=d["label"],
            shape=d["shape"],
            cluster=d.get("cluster"),
        )
        for d in nodes_dict.values()
    ]
    graph_clusters = list(clusters_dict.values())

    return graph_nodes, edges_list, graph_clusters, final_direction, layout
