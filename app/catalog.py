"""Client questionnaire. IDs are stable API values; labels are presentation copy."""
VERSION = "qma-2026-11-09-v1"


def question(number, key, title, choices, maximum=1):
    return {"number": number, "id": key, "title": title,
            "type": "single" if maximum == 1 else "multiple", "min_selections": 1,
            "max_selections": maximum,
            "options": [{"id": value, "label": label} for value, label in choices]}


QUESTIONS = [
    question(1, "use", "What will your stadium be used for?", [
        ("football", "Football"), ("multi_sport", "Multi-sport"), ("athletics", "Athletics"),
        ("community", "Community sport"), ("entertainment", "Concerts and entertainment"),
        ("hybrid", "A hybrid sports and events venue")]),
    question(2, "capacity", "How many spectators should your stadium welcome?", [
        ("20000", "20,000"), ("40000", "40,000"), ("60000", "60,000"), ("80000_plus", "80,000 or more")]),
    question(3, "setting", "Where do you imagine your stadium?", [
        ("city", "In the city"), ("sea", "Beside the sea"), ("desert", "In the desert"),
        ("mountains", "Among mountains"), ("park", "Within a green park"), ("future_district", "In a future urban district")]),
    question(4, "theme", "What theme or story should inspire your stadium?", [
        ("qatar", "Qatar and its heritage"), ("nature", "Nature and living forms"), ("dunes", "Desert and dunes"),
        ("waves", "Sea and waves"), ("cosmos", "Space and the cosmos"), ("future_city", "The city of tomorrow")]),
    question(5, "style", "Which architectural style best expresses your vision?", [
        ("futuristic", "Futuristic"), ("parametric", "Parametric and geometric"), ("minimalist", "Contemporary minimalist"),
        ("organic", "Organic and flowing"), ("industrial", "Industrial high-tech"),
        ("qatari", "A contemporary interpretation of Qatari architecture")]),
    question(6, "shape", "What overall shape should your stadium have?", [
        ("oval", "Oval bowl"), ("circular", "Circular bowl"), ("rectangular", "Rectangular bowl"),
        ("asymmetric", "Asymmetric form"), ("wave", "Wave-shaped form"), ("sculptural", "A sculptural free-form landmark")]),
    question(7, "roof", "What kind of roof would you like?", [
        ("open", "Open to the sky"), ("floating", "A floating canopy"), ("tensile", "A lightweight tensile roof"),
        ("retractable", "A retractable roof"), ("translucent", "A translucent roof"), ("solar", "A solar-integrated canopy")]),
    question(8, "materials", "Which facade and material qualities appeal to you?", [
        ("glass_steel", "Glass and steel"), ("perforated_metal", "Perforated metal"), ("stone", "A stone or mineral texture"),
        ("translucent", "A translucent skin"), ("timber", "A timber-inspired finish"),
        ("digital", "A facade with integrated digital media")], 2),
    question(9, "palette", "Which colour palette and lighting mood should define it?", [
        ("ivory", "White and ivory with soft light"), ("silver", "Silver and grey with crisp light"),
        ("charcoal", "Charcoal with dramatic light"), ("earth", "Earthy tones with warm light"),
        ("nature", "Nature-inspired colours"), ("team", "A vibrant team-colour identity")]),
    question(10, "experience", "What should visitors enjoy most inside your stadium?", [
        ("close_action", "Feeling close to the action"), ("comfort", "Generous shade and comfort"),
        ("social", "Social terraces and shared spaces"), ("immersive", "Immersive light and media"),
        ("views", "Open views towards the surrounding landscape")]),
    question(11, "innovation", "What should be your stadium's boldest innovation?", [
        ("moving_facade", "An adaptive moving facade"), ("modular_bowl", "An expandable modular bowl"),
        ("transformable_field", "A transformable event field"), ("floating_structure", "A dramatic floating-looking structure"),
        ("gardens", "Gardens integrated into the building"), ("reconfigurable", "A reconfigurable venue for different events")]),
    question(12, "technologies", "Which technologies should bring your stadium to life?", [
        ("ai_guidance", "AI visitor guidance"), ("ar", "Augmented-reality experiences"),
        ("smart_crowd", "Smart crowd and mobility management"), ("responsive_media", "Responsive lighting and media"),
        ("digital_twin", "A digital twin for operations"), ("interactive_fans", "Interactive fan participation")], 2),
    question(13, "environment", "Which environmental strategies matter most to you?", [
        ("solar", "Solar energy"), ("water", "Water reuse"), ("passive", "Passive cooling and shade"),
        ("recycled", "Reused or recycled materials"), ("modular", "Modular construction for reuse"),
        ("transport", "Public transport and walking"), ("biodiversity", "Planting and biodiversity")], 3),
    question(14, "legacy", "How should your stadium serve people in the future?", [
        ("community", "Everyday community sport"), ("academy", "A sports academy and learning centre"),
        ("culture", "A cultural and entertainment destination"), ("park", "A public park and recreation hub"),
        ("flexible", "A flexible venue for many events"), ("relocation", "A venue designed for relocation or reuse")]),
    {"number": 15, "id": "signature", "title": "What one signature feature would make your stadium unforgettable?",
     "type": "signature", "max_length": 140, "modes": ["text", "surprise"]},
]
BY_ID = {q["id"]: q for q in QUESTIONS}


def labels(answers):
    result = {}
    for key, value in answers.items():
        if key == "signature":
            result[key] = value
        else:
            choices = {o["id"]: o["label"] for o in BY_ID[key]["options"]}
            result[key] = [choices[v] for v in value] if isinstance(value, list) else choices[value]
    return result
