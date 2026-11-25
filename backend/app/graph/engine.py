"""NetworkX-powered computation engine for LUMO Knowledge Graph."""

from __future__ import annotations

import math
from typing import Any

import networkx as nx

from app.core.logging import get_logger

logger = get_logger("graph.engine")


class KnowledgeGraphEngine:
    """In-memory NetworkX graph computation layer for traversal, clustering, centrality, and layout."""

    def __init__(self) -> None:
        self.graph: nx.MultiDiGraph = nx.MultiDiGraph()
        self._undirected_cache: nx.Graph | None = None

    def clear(self) -> None:
        self.graph.clear()
        self._undirected_cache = None

    def add_entity_node(
        self,
        entity_id: str,
        name: str,
        entity_type: str,
        description: str | None = None,
        confidence: float = 1.0,
        sources_count: int = 0,
        x: float | None = None,
        y: float | None = None,
    ) -> None:
        self.graph.add_node(
            entity_id,
            id=entity_id,
            label=name,
            type=entity_type,
            description=description,
            confidence=confidence,
            sources_count=sources_count,
            x=x,
            y=y,
        )
        self._undirected_cache = None

    def add_relationship_edge(
        self,
        edge_id: str,
        source_id: str,
        target_id: str,
        relationship_type: str,
        weight: float = 1.0,
        confidence: float = 1.0,
        evidence_count: int = 1,
        first_snippet: str | None = None,
    ) -> None:
        if not self.graph.has_node(source_id) or not self.graph.has_node(target_id):
            return

        self.graph.add_edge(
            source_id,
            target_id,
            key=edge_id,
            id=edge_id,
            label=relationship_type,
            weight=weight,
            confidence=confidence,
            evidence_count=evidence_count,
            first_snippet=first_snippet,
        )
        self._undirected_cache = None

    def compute_layout(
        self,
        width: float = 800.0,
        height: float = 470.0,
        padding: float = 60.0,
    ) -> None:
        """Compute visual (x, y) coordinates using spring layout for clean SVG rendering."""
        if len(self.graph) == 0:
            return

        try:
            # Use undirected view for organic force layout
            undirected = self.graph.to_undirected(as_view=True)
            # Use spring layout with deterministic seed
            pos = nx.spring_layout(undirected, seed=42, k=1.2 / math.sqrt(max(len(self.graph), 1)), iterations=50)

            usable_w = width - (2 * padding)
            usable_h = height - (2 * padding)

            for node_id, (px, py) in pos.items():
                # Map [-1, 1] to [padding, width - padding]
                norm_x = padding + ((px + 1.0) / 2.0) * usable_w
                norm_y = padding + ((py + 1.0) / 2.0) * usable_h

                self.graph.nodes[node_id]["x"] = round(float(norm_x), 1)
                self.graph.nodes[node_id]["y"] = round(float(norm_y), 1)
        except Exception as exc:
            logger.warning("Spring layout computation fallback: %s", exc)

    def get_neighborhood(
        self,
        entity_id: str,
        max_depth: int = 2,
        max_nodes: int = 50,
        entity_types: set[str] | None = None,
        relationship_types: set[str] | None = None,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Bounded BFS neighborhood expansion centered on entity_id."""
        if not self.graph.has_node(entity_id):
            return [], []

        max_depth = max(1, min(max_depth, 3))  # Hard cap at depth 3 for safety
        visited_nodes: set[str] = {entity_id}
        queue: list[tuple[str, int]] = [(entity_id, 0)]

        while queue and len(visited_nodes) < max_nodes:
            curr_node, curr_depth = queue.pop(0)
            if curr_depth >= max_depth:
                continue

            # Check successors and predecessors
            neighbors = list(self.graph.successors(curr_node)) + list(self.graph.predecessors(curr_node))
            for neighbor in neighbors:
                if neighbor in visited_nodes:
                    continue

                node_data = self.graph.nodes[neighbor]
                if entity_types and node_data.get("type") not in entity_types:
                    continue

                visited_nodes.add(neighbor)
                queue.append((neighbor, curr_depth + 1))
                if len(visited_nodes) >= max_nodes:
                    break

        # Collect nodes
        result_nodes: list[dict[str, Any]] = []
        for nid in visited_nodes:
            nd = dict(self.graph.nodes[nid])
            nd["degree"] = self.graph.degree(nid)
            result_nodes.append(nd)

        # Collect edges between visited nodes
        result_edges: list[dict[str, Any]] = []
        seen_edges: set[str] = set()

        for u in visited_nodes:
            for v, edges in self.graph[u].items():
                if v in visited_nodes:
                    for edge_key, ed in edges.items():
                        if edge_key in seen_edges:
                            continue
                        if relationship_types and ed.get("label") not in relationship_types:
                            continue
                        seen_edges.add(edge_key)
                        edge_dict = dict(ed)
                        edge_dict["from"] = u
                        edge_dict["to"] = v
                        result_edges.append(edge_dict)

        return result_nodes, result_edges

    def get_stats(self) -> dict[str, Any]:
        """Calculate graph metrics including degree centrality and top connected entities."""
        total_nodes = self.graph.number_of_nodes()
        total_edges = self.graph.number_of_edges()

        if total_nodes == 0:
            return {
                "total_entities": 0,
                "entities_by_type": {},
                "total_relationships": 0,
                "relationships_by_type": {},
                "total_documents_represented": 0,
                "graph_density": 0.0,
                "top_connected_entities": [],
            }

        entities_by_type: dict[str, int] = {}
        for _, data in self.graph.nodes(data=True):
            etype = data.get("type", "Concept")
            entities_by_type[etype] = entities_by_type.get(etype, 0) + 1

        relationships_by_type: dict[str, int] = {}
        for _, _, data in self.graph.edges(data=True):
            label = data.get("label", "RELATED_TO")
            relationships_by_type[label] = relationships_by_type.get(label, 0) + 1

        # Density calculation
        undirected = self.graph.to_undirected(as_view=True)
        density = round(float(nx.density(undirected)), 4)

        # Degree ranking
        degree_list = [
            {
                "id": nid,
                "label": self.graph.nodes[nid].get("label", nid),
                "type": self.graph.nodes[nid].get("type", "Concept"),
                "degree": deg,
            }
            for nid, deg in self.graph.degree()
        ]
        degree_list.sort(key=lambda item: -item["degree"])

        return {
            "total_entities": total_nodes,
            "entities_by_type": entities_by_type,
            "total_relationships": total_edges,
            "relationships_by_type": relationships_by_type,
            "graph_density": density,
            "top_connected_entities": degree_list[:10],
        }

    def shortest_path(self, source_id: str, target_id: str) -> list[str] | None:
        """Find the shortest connection path between two entities."""
        if not self.graph.has_node(source_id) or not self.graph.has_node(target_id):
            return None
        try:
            undirected = self.graph.to_undirected(as_view=True)
            return list(nx.shortest_path(undirected, source=source_id, target=target_id))
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return None
