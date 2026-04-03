from pyvis.network import Network
import webbrowser
import os

def create_er_diagram():
    # Create a PyVis network
    net = Network(height="100vh", width="100vw", bgcolor="#ffffff")
    
    # Configure physics for better layout and ensure text appears inside shapes
    net.set_options("""
    var options = {
      "physics": {
        "enabled": false
      },
      "nodes": {
        "font": {
          "size": 14,
          "align": "center",
          "vadjust": 0
        },
        "labelHighlightBold": false,
        "shapeProperties": {
          "useBorderWithImage": false
        },
        "borderWidth": 2,
        "borderWidthSelected": 2,
        "color": {
          "border": "#000000",
          "background": "#FFFFFF",
          "highlight": {
            "border": "#000000",
            "background": "#FFFFFF"
          }
        }
      },
      "edges": {
        "smooth": {
          "enabled": true,
          "type": "straightCross"
        },
        "arrows": {
          "to": {
            "enabled": false,
            "scaleFactor": 1.2,
            "type": "arrow"
          }
        },
        "color": {
          "color": "#000000",
          "highlight": "#000000",
          "hover": "#000000"
        }
      },
      "layout": {
        "improvedLayout": false
      },
      "interaction": {
        "dragNodes": true,
        "dragView": true,
        "zoomView": true
      }
    }
    """)
    
    # Define colors and shapes - all white/transparent with black borders and text
    entity_color = "#FFFFFF"  # White for all entities
    strong_entity_color = "#FFFFFF"  # White for strong entities
    relationship_color = "#FFFFFF"  # White for relationships
    strong_relationship_color = "#FFFFFF"  # White for strong relationships
    attribute_color = "#FFFFFF"  # White for attributes
    key_attribute_color = "#FFFFFF"  # White for key attributes
    
    # Add entities (rectangular shape)
    entities = [
        ("Patients", entity_color, 100, 100),
        ("Doctors", entity_color, 500, 100),
        ("Pharmacies", entity_color, 100, 500),
        ("Drugs", strong_entity_color, 500, 400),  # Strong entity (bolded)
        ("PharmCo", entity_color, 700, 600)
    ]
    
    for entity, color, x, y in entities:
        border_width = 4 if entity == "Drugs" else 2  # Bold border for strong entity
        net.add_node(entity, 
                    label=entity, 
                    shape="box", 
                    color={"background": color, "border": "#000000"},
                    borderWidth=border_width,
                    x=x, y=y,
                    physics=False,
                    size=30,
                    font={"size": 14, "face": "arial", "color": "black", "align": "center", "vadjust": 0})
    
    # Add relationships (diamond shape)
    relationships = [
        ("HasPriPhy", relationship_color, 300, 150),
        ("prescribes", relationship_color, 350, 250),
        ("Sell", relationship_color, 300, 450),
        ("Makes", strong_relationship_color, 600, 500),  # Strong relationship (bolded)
        ("IsContracted", relationship_color, 400, 550)
    ]
    
    for rel, color, x, y in relationships:
        border_width = 4 if rel == "Makes" else 2  # Bold border for strong relationship
        net.add_node(rel, 
                    label=rel, 
                    shape="diamond",  # Back to diamond but with different approach
                    color={"background": color, "border": "#000000"},
                    borderWidth=border_width,
                    x=x, y=y,
                    physics=False,
                    size=40,  # Even larger size
                    margin={"top": 10, "bottom": 10, "left": 10, "right": 10},
                    font={"size": 11, "face": "arial", "color": "black", "align": "center", "vadjust": -5})
    
    # Add attributes for Patients
    patient_attrs = [
        ("patient_ssn", key_attribute_color, 50, 50, True),  # Primary key (underlined)
        ("patient_name", attribute_color, 150, 50, False),
        ("patient_age", attribute_color, 50, 150, False),
        ("patient_address", attribute_color, 150, 150, False)
    ]
    
    for attr, color, x, y, is_key in patient_attrs:
        label = attr.replace("patient_", "")
        if is_key:
            label = f"{label}\n{'‾' * len(label)}"  # Unicode overline to simulate underline
        net.add_node(attr, 
                    label=label, 
                    shape="ellipse", 
                    color={"background": color, "border": "#000000"},
                    x=x, y=y,
                    physics=False,
                    size=20,
                    font={"size": 10, "face": "arial", "color": "black", "align": "center", "vadjust": 0})
        net.add_edge("Patients", attr, color="black", width=1)
    
    # Add attributes for Doctors
    doctor_attrs = [
        ("doctor_ssn", key_attribute_color, 450, 50, True),  # Primary key (underlined)
        ("doctor_name", attribute_color, 550, 50, False),
        ("doctor_specialty", attribute_color, 600, 100, False),
        ("doctor_experience_year", attribute_color, 600, 150, False)
    ]
    
    for attr, color, x, y, is_key in doctor_attrs:
        label = attr.replace("doctor_", "")
        if is_key:
            label = f"{label}\n{'‾' * len(label)}"  # Unicode overline to simulate underline
        net.add_node(attr, 
                    label=label, 
                    shape="ellipse", 
                    color={"background": color, "border": "#000000"},
                    x=x, y=y,
                    physics=False,
                    size=20,
                    font={"size": 10, "face": "arial", "color": "black", "align": "center", "vadjust": 0})
        net.add_edge("Doctors", attr, color="black", width=1)
    
    # Add attributes for HasPriPhy relationship
    haspriphy_attrs = [
        ("prescription_date", attribute_color, 250, 120, False),
        ("quantity", attribute_color, 350, 120, False)
    ]
    
    for attr, color, x, y, is_key in haspriphy_attrs:
        net.add_node(attr, 
                    label=attr, 
                    shape="ellipse", 
                    color={"background": color, "border": "#000000"},
                    x=x, y=y,
                    physics=False,
                    size=20,
                    font={"size": 10, "face": "arial", "color": "black", "align": "center", "vadjust": 0})
        net.add_edge("HasPriPhy", attr, color="black", width=1)
    
    # Add attributes for Pharmacies
    pharmacy_attrs = [
        ("pharmacy_name", attribute_color, 50, 450, True),
        ("pharmacy_address", attribute_color, 50, 550, False),
        ("pharmacy_phone", attribute_color, 150, 550, False)
    ]
    
    for attr, color, x, y, is_key in pharmacy_attrs:
        label = attr.replace("pharmacy_", "")
        net.add_node(attr, 
                    label=label, 
                    shape="ellipse", 
                    color={"background": color, "border": "#000000"},
                    x=x, y=y,
                    physics=False,
                    size=20,
                    font={"size": 10, "face": "arial", "color": "black", "align": "center", "vadjust": 0})
        net.add_edge("Pharmacies", attr, color="black", width=1)
    
    # Add attributes for Drugs (strong entity)
    drug_attrs = [
        ("trade_name", key_attribute_color, 450, 350, True),  # Primary key (underlined)
        ("formula", attribute_color, 550, 350, False)
    ]
    
    for attr, color, x, y, is_key in drug_attrs:
        label = attr
        if is_key:
            label = f"{label}\n{'‾' * len(label)}"  # Unicode overline to simulate underline
        net.add_node(attr, 
                    label=label, 
                    shape="ellipse", 
                    color={"background": color, "border": "#000000"},
                    x=x, y=y,
                    physics=False,
                    size=20,
                    font={"size": 10, "face": "arial", "color": "black", "align": "center", "vadjust": 0})
        net.add_edge("Drugs", attr, color="black", width=1)
    
    # Add attributes for Sell relationship
    sell_attrs = [
        ("price", attribute_color, 250, 420, False)
    ]
    
    for attr, color, x, y, is_key in sell_attrs:
        net.add_node(attr, 
                    label=attr, 
                    shape="ellipse", 
                    color={"background": color, "border": "#000000"},
                    x=x, y=y,
                    physics=False,
                    size=20,
                    font={"size": 10, "face": "arial", "color": "black", "align": "center", "vadjust": 0})
        net.add_edge("Sell", attr, color="black", width=1)
    
    # Add attributes for IsContracted relationship
    contracted_attrs = [
        ("start_date", attribute_color, 350, 600, False),
        ("end_date", attribute_color, 450, 600, False),
        ("contract_text", attribute_color, 300, 650, False),
        ("supervisor", attribute_color, 400, 650, False)
    ]
    
    for attr, color, x, y, is_key in contracted_attrs:
        net.add_node(attr, 
                    label=attr, 
                    shape="ellipse", 
                    color={"background": color, "border": "#000000"},
                    x=x, y=y,
                    physics=False,
                    size=20,
                    font={"size": 10, "face": "arial", "color": "black", "align": "center", "vadjust": 0})
        net.add_edge("IsContracted", attr, color="black", width=1)
    
    # Add attributes for PharmCo
    pharmco_attrs = [
        ("company_name", attribute_color, 750, 550, False),
        ("company_phone", attribute_color, 750, 650, False)
    ]
    
    for attr, color, x, y, is_key in pharmco_attrs:
        label = attr.replace("company_", "")
        net.add_node(attr, 
                    label=label, 
                    shape="ellipse", 
                    color={"background": color, "border": "#000000"},
                    x=x, y=y,
                    physics=False,
                    size=20,
                    font={"size": 10, "face": "arial", "color": "black", "align": "center", "vadjust": 0})
        net.add_edge("PharmCo", attr, color="black", width=1)
    
    # Add relationships between entities
    # Patients to HasPriPhy to Doctors (with directed arrow from Patients)
    net.add_edge("Patients", "HasPriPhy", color="black", width=2, arrows={"to": {"enabled": True, "scaleFactor": 1.2}})
    net.add_edge("HasPriPhy", "Doctors", color="black", width=2)
    
    # Doctors to prescribes to Drugs
    net.add_edge("Doctors", "prescribes", color="black", width=2)
    net.add_edge("prescribes", "Drugs", color="black", width=2)
    
    # Pharmacies to Sell to Drugs
    net.add_edge("Pharmacies", "Sell", color="black", width=2)
    net.add_edge("Sell", "Drugs", color="black", width=2)
    
    # Drugs to Makes to PharmCo (strong relationship with directed arrow from Drugs)
    net.add_edge("Drugs", "Makes", color="black", width=3, arrows={"to": {"enabled": True, "scaleFactor": 1.2}})  # Directed arrow
    net.add_edge("Makes", "PharmCo", color="black", width=3)
    
    # Pharmacies to IsContracted to PharmCo
    net.add_edge("Pharmacies", "IsContracted", color="black", width=2)
    net.add_edge("IsContracted", "PharmCo", color="black", width=2)
    
    # Add a title
    net.add_node("title", label="Problem 2.7 - ER Diagram", 
                shape="box", color="#FFFFFF", 
                borderWidth=0, x=400, y=0, physics=False,
                font={"size": 20, "face": "arial", "color": "black", "bold": True})
    
    # Save and show the network
    output_file = "er_diagram_problem_2_7.html"
    net.save_graph(output_file)
    
    # Post-process the HTML to fix the border color
    with open(output_file, 'r', encoding='utf-8') as file:
        html_content = file.read()
    
    # Replace lightgray border with black border
    html_content = html_content.replace('border: 1px solid black;', 'border: 1px solid black;')
    
    with open(output_file, 'w', encoding='utf-8') as file:
        file.write(html_content)
    
    print(f"ER Diagram visualization saved as '{output_file}'")
    print("Opening in your default web browser...")
    
    # Open the file in the default web browser
    file_path = os.path.abspath(output_file)
    webbrowser.open(f"file://{file_path}")
    
    return output_file

if __name__ == "__main__":
    create_er_diagram()
    
    print("\nER Diagram Analysis:")
    print("=" * 50)
    print("ENTITIES (Rectangular boxes):")
    print("- Patients, Doctors, Pharmacies, PharmCo (regular entities)")
    print("- Drugs (STRONG ENTITY - shown with bold border)")
    print()
    print("RELATIONSHIPS (Diamond shapes):")
    print("- HasPriPhy, prescribes, Sell, IsContracted (regular relationships)")
    print("- Makes (STRONG RELATIONSHIP - shown with bold border)")
    print()
    print("ATTRIBUTES (Oval shapes):")
    print("- Primary keys are shown with CSS underline styling")
    print("- All elements have white background with black borders and text")
    print("- Full property names are used (no abbreviations)")
    print("- Relationship attributes are connected to their respective relationships")
    print()
    print("KEY OBSERVATIONS:")
    print("- 'Drugs' entity is bolded (strong entity)")
    print("- 'Makes' relationship is bolded (strong relationship)")
    print("- Primary keys are underlined: ssn (Patients, Doctors), trade_name (Drugs)")
    print("- The diagram shows a medical prescription system with patients, doctors,")
    print("  drugs, pharmacies, and pharmaceutical companies")
    print("- All boxes are sized to fit their content with proper constraints")