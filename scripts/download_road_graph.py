"""Optional: requires `python -m pip install osmnx`; downloads a Chennai drive graph."""
from pathlib import Path
import osmnx as ox

target=Path(__file__).resolve().parents[1]/"data"/"processed"/"roads"/"chennai.graphml"
target.parent.mkdir(parents=True,exist_ok=True)
G=ox.graph_from_place("Chennai, Tamil Nadu, India",network_type="drive",simplify=True)
ox.save_graphml(G,target)
print(f"Saved {G.number_of_nodes()} nodes and {G.number_of_edges()} edges to {target}")
