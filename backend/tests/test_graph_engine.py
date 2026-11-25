"""Tests for NetworkX KnowledgeGraphEngine computation layer."""

from app.graph.engine import KnowledgeGraphEngine


def test_engine_nodes_edges_and_layout():
    engine = KnowledgeGraphEngine()
    engine.add_entity_node("n1", "FastAPI", "Technology")
    engine.add_entity_node("n2", "Python", "Technology")
    engine.add_entity_node("n3", "Qdrant", "Technology")

    engine.add_relationship_edge("e1", "n1", "n2", "USES")
    engine.add_relationship_edge("e2", "n1", "n3", "INTEGRATES_WITH")

    assert len(engine.graph) == 3
    assert engine.graph.number_of_edges() == 2

    # Compute spring layout
    engine.compute_layout(width=800, height=500)
    for nid in ["n1", "n2", "n3"]:
        assert engine.graph.nodes[nid]["x"] is not None
        assert engine.graph.nodes[nid]["y"] is not None
        assert 0 <= engine.graph.nodes[nid]["x"] <= 800
        assert 0 <= engine.graph.nodes[nid]["y"] <= 500


def test_engine_neighborhood_traversal_and_depth_limits():
    engine = KnowledgeGraphEngine()
    # Linear chain: A -> B -> C -> D
    engine.add_entity_node("A", "Node A", "Concept")
    engine.add_entity_node("B", "Node B", "Concept")
    engine.add_entity_node("C", "Node C", "Concept")
    engine.add_entity_node("D", "Node D", "Concept")

    engine.add_relationship_edge("e1", "A", "B", "CONNECTS")
    engine.add_relationship_edge("e2", "B", "C", "CONNECTS")
    engine.add_relationship_edge("e3", "C", "D", "CONNECTS")

    # Depth 1 from A should include A and B
    nodes_d1, edges_d1 = engine.get_neighborhood("A", max_depth=1)
    node_ids_d1 = {n["id"] for n in nodes_d1}
    assert node_ids_d1 == {"A", "B"}
    assert len(edges_d1) == 1

    # Depth 2 from A should include A, B, C
    nodes_d2, edges_d2 = engine.get_neighborhood("A", max_depth=2)
    node_ids_d2 = {n["id"] for n in nodes_d2}
    assert node_ids_d2 == {"A", "B", "C"}
    assert len(edges_d2) == 2

    # Enforced depth cap of 3
    nodes_d10, _ = engine.get_neighborhood("A", max_depth=10)
    assert len(nodes_d10) <= 4


def test_engine_shortest_path_and_stats():
    engine = KnowledgeGraphEngine()
    engine.add_entity_node("X", "Node X", "Concept")
    engine.add_entity_node("Y", "Node Y", "Concept")
    engine.add_entity_node("Z", "Node Z", "Concept")

    engine.add_relationship_edge("e1", "X", "Y", "REL")
    engine.add_relationship_edge("e2", "Y", "Z", "REL")

    path = engine.shortest_path("X", "Z")
    assert path == ["X", "Y", "Z"]

    stats = engine.get_stats()
    assert stats["total_entities"] == 3
    assert stats["total_relationships"] == 2
    assert len(stats["top_connected_entities"]) == 3
    assert stats["top_connected_entities"][0]["id"] == "Y"  # Y has degree 2
