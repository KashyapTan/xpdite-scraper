from pyvis.network import Network
import webbrowser
import os

def create_er_diagram_final_hybrid():
    # --- 1. SETUP ---
    net = Network(height="100vh", width="100vw", bgcolor="#ffffff")
    net.set_options("""
    var options = { "physics": { "enabled": true } }
    """)
    node_color = {"background": "#FFFFFF", "border": "#000000"}

    # --- 2. NODE CREATION ---
    # Add Entities
    entities = [("Professor", 300, 200), ("Department", 300, 800), ("Graduate Student", 1000, 800), ("Project", 1000, 200)]
    for entity, x, y in entities:
        net.add_node(entity, label=entity, shape="box", color=node_color, x=x, y=y, physics=False, size=30)
    
    # Add Relationships from drawing (with "Runs" reverted)
    relationships = [
        ("Works On", 650, 200), 
        ("Manages", 650, 350), 
        ("Supervises", 650, 500), 
        ("works in", 150, 500), 
        ("Runs", 450, 500), # Reverted from Chairman_Of
        ("Majors_In", 650, 800),
        ("Advises", 1200, 800), 
        ("Work Assignment", 1000, 500)
    ]
    for rel, x, y in relationships:
        net.add_node(rel, label=rel, shape="diamond", color=node_color, x=x, y=y, physics=False, size=30)

    # Add Attributes (matching official problem description)
    attributes = {
        "Professor": [
            ("p_ssn", "SSN", 150, 100, True), 
            ("p_name", "name", 300, 100, False),
            ("p_age", "age", 450, 100, False), 
            ("p_rank", "rank", 150, 300, False),
            ("p_spec", "research specialty", 450, 300, False)
        ],
        "Department": [
            ("d_num", "department number", 150, 700, True),
            ("d_name", "department name", 300, 700, False),
            ("d_office", "main office", 450, 700, False)
        ],
        "Graduate Student": [
            ("g_ssn", "SSN", 850, 700, True), 
            ("g_name", "name", 1000, 700, False),
            ("g_age", "age", 1150, 700, False),
            ("g_degree", "degree program", 1000, 900, False)
        ],
        "Project": [
            ("pr_num", "Project number", 850, 100, True),
            ("pr_sponsor", "sponsor name", 1000, 100, False),
            ("pr_start", "starting date", 1150, 100, False),
            ("pr_end", "ending date", 925, 300, False),
            ("pr_budget", "budget", 1075, 300, False)
        ],
        "works in": [("wi_time", "time percentage", 0, 500, False)]
    }
    for parent_node, attrs in attributes.items():
        for attr_id, label, x, y, is_key in attrs:
            if is_key: label = f"{label}\n{'_' * len(label)}"
            net.add_node(attr_id, label=label, shape="ellipse", color=node_color, x=x, y=y, physics=False, size=25, font={"size": 12})
    
    # --- 3. EDGE CREATION ---
    # Connect attributes to their parent nodes
    for parent_node, attrs in attributes.items():
        for attr_id, _, _, _, _ in attrs:
            net.add_edge(parent_node, attr_id, color="black", width=1)
            
    # Connect entities and relationships
    net.add_edge("Professor", "Works On", color="black", width=2)
    net.add_edge("Works On", "Project", color="black", width=2)

    net.add_edge("Professor", "Manages", color="black", width=2)
    net.add_edge("Manages", "Project", color="black", width=3, arrows={"to": {"enabled": True}})

    net.add_edge("Supervises", "Professor", color="black", width=2, arrows={"to": {"enabled": True}})
    net.add_edge("Work Assignment", "Supervises", color="black", width=2)
    
    net.add_edge("Professor", "works in", color="black", width=3)
    net.add_edge("works in", "Department", color="black", width=2)
    
    # Edge for "Runs" (reverted name)
    net.add_edge("Runs", "Professor", color="black", width=2, arrows={"to": {"enabled": True}})
    net.add_edge("Department", "Runs", color="black", width=3)

    net.add_edge("Graduate Student", "Majors_In", color="black", width=3)
    net.add_edge("Majors_In", "Department", color="black", width=2, arrows={"to": {"enabled": True}})

    net.add_edge("Graduate Student", "Advises", color="black", width=3, label="advisee / advisor")
    # net.add_edge("Advises", "Graduate Student", color="black", width=2, label="advisor")

    net.add_edge("Graduate Student", "Work Assignment", color="black", width=2)
    net.add_edge("Work Assignment", "Project", color="black", width=2)
    # net.add_edge("Professor", "Work Assignment", color="black", width=2, label="supervises")

    # --- 4. FINALIZATION ---
    output_file = "er2.html"
    net.save_graph(output_file)
    print(f"Final ER Diagram saved as '{output_file}'")
    webbrowser.open(f"file://{os.path.abspath(output_file)}")

if __name__ == "__main__":
    create_er_diagram_final_hybrid()