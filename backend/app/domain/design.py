import random
import unicodedata

from .catalog import BY_ID, labels

PROMPT_VERSION = "stadium-v3-architecture"


class InputError(ValueError):
    pass


def validate_answers(answers, *, complete=False, allow_free_text=False):
    if not isinstance(answers, dict):
        raise InputError("answers must be an object")
    unknown = answers.keys() - BY_ID.keys()
    if unknown:
        raise InputError(f"Unknown questions: {', '.join(sorted(unknown))}")
    if complete and answers.keys() != BY_ID.keys():
        raise InputError(
            f"Missing answers: {', '.join(sorted(BY_ID.keys() - answers.keys()))}"
        )
    cleaned = {}
    for key, value in answers.items():
        q = BY_ID[key]
        if key == "signature":
            if not isinstance(value, dict) or value.keys() - {"mode", "text"}:
                raise InputError("signature must contain mode and optional text")
            if value.get("mode") == "surprise":
                if value.get("text") not in (None, ""):
                    raise InputError("Surprise me cannot include signature text")
                cleaned[key] = {"mode": "surprise"}
            elif value.get("mode") == "text":
                if not allow_free_text:
                    raise InputError(
                        "Free-text signature is disabled pending moderation; use Surprise me"
                    )
                text = value.get("text")
                if not isinstance(text, str) or not 1 <= len(text.strip()) <= 140:
                    raise InputError("Signature must contain 1–140 characters")
                if any(unicodedata.category(c).startswith("C") for c in text):
                    raise InputError("Signature cannot contain control characters")
                cleaned[key] = {"mode": "text", "text": text.strip()}
            else:
                raise InputError("signature.mode must be text or surprise")
            continue
        allowed = {o["id"] for o in q["options"]}
        if q["type"] == "multiple":
            if (
                not isinstance(value, list)
                or not all(isinstance(v, str) for v in value)
                or not 1 <= len(value) <= q["max_selections"]
                or len(set(value)) != len(value)
                or not set(value) <= allowed
            ):
                raise InputError(
                    f"{key}: choose 1–{q['max_selections']} distinct valid option IDs"
                )
            cleaned[key] = sorted(value)
        elif not isinstance(value, str) or value not in allowed:
            raise InputError(f"{key}: choose one valid option ID")
        else:
            cleaned[key] = value
    return cleaned


def compatibility(answers):
    """Explanatory treatments only. Never overwrite an answer."""
    notes = []
    if answers.get("roof") == "open" and "solar" in answers.get("environment", []):
        notes.append(
            {
                "code": "solar_off_roof",
                "message": "Keep the stadium open to the sky; place solar panels on entrance and landscape structures.",
            }
        )
    if answers.get("roof") == "open" and answers.get("experience") == "comfort":
        notes.append(
            {
                "code": "open_roof_shade",
                "message": "Keep the bowl open to the sky and provide shade in concourses and surrounding public spaces.",
            }
        )
    if (
        answers.get("use") == "athletics"
        and answers.get("experience") == "close_action"
    ):
        notes.append(
            {
                "code": "athletics_track",
                "message": "Retain the athletics track; proximity to the action is limited by the track around the field.",
            }
        )
    if answers.get("use") == "athletics" and answers.get("shape") in {
        "rectangular",
        "circular",
        "sculptural",
        "asymmetric",
        "wave",
    }:
        notes.append(
            {
                "code": "track_inside_shape",
                "message": "Preserve the selected exterior shape while fitting a continuous oval athletics track inside it.",
            }
        )
    if answers.get("use") == "athletics" and answers.get("roof") == "translucent":
        notes.append(
            {
                "code": "track_roof_visibility",
                "message": "Keep the translucent roof and show the track through an open end or transparent sightline; some lanes may be obscured.",
            }
        )
    return notes


def build_design(answers, seed):
    selected = labels(answers)
    rng = random.Random(seed)
    signatures = {
        "qatar": [
            "A patterned landmark entrance inspired by Qatari courtyards",
            "A spiralling public walkway with geometric screens",
        ],
        "nature": [
            "A planted public promenade around the bowl",
            "A sculptural entrance inspired by branching trees",
        ],
        "dunes": [
            "A dune-shaped sculptural entrance",
            "A flowing public walkway inspired by desert ridges",
        ],
        "waves": [
            "A wave-shaped public promenade",
            "A sculptural entrance inspired by ocean currents",
        ],
        "cosmos": [
            "A constellation-patterned entrance plaza",
            "An orbital public walkway around the stadium",
        ],
        "future_city": [
            "A spiralling public walkway",
            "A glowing geometric entrance plaza",
        ],
    }
    signature = (
        rng.choice(signatures[answers["theme"]])
        if answers["signature"]["mode"] == "surprise"
        else answers["signature"]["text"]
    )
    names = {
        "qatar": "Heritage",
        "nature": "Living",
        "dunes": "Dune",
        "waves": "Tidal",
        "cosmos": "Orbit",
        "future_city": "Tomorrow",
    }
    title = f"{names[answers['theme']]} {rng.choice(['Arena', 'Stadium', 'Park'])}"
    story = (
        f"{title} imagines {selected['use'].lower()} for {selected['capacity']} spectators, {selected['setting'].lower()}. "
        f"Inspired by {selected['theme'].lower()}, it pairs {selected['style'].lower()} with {selected['shape'].lower()}. "
        f"Its signature is {signature[0].lower() + signature[1:]}. "
        f"The concept prioritises {selected['experience'].lower()} and explores {selected['innovation'].lower()}. "
        f"Proposed technologies: {', '.join(selected['technologies'])}. "
        f"Environmental design choices: {', '.join(selected['environment'])}. "
        f"Its future purpose is {selected['legacy'].lower()}. "
        "This is a conceptual visualisation, not an engineered design or verified sustainability assessment."
    )
    roof_terms = {
        "open": "open-to-sky roof",
        "floating": "floating canopy",
        "tensile": "tensile canopy",
        "retractable": "retractable roof",
        "translucent": "translucent roof",
        "solar": "solar canopy",
    }
    signature_short = signature.split(" inspired by ")[0].strip()
    if signature_short.lower().startswith(("a ", "an ")):
        signature_short = signature_short.split(" ", 1)[1]
    local_prompt = (
        f"Photorealistic aerial view: {answers['shape'].replace('_', ' ')} "
        f"{answers['use'].replace('_', ' ')} stadium, {selected['capacity']} seats, "
        f"{answers['setting'].replace('_', ' ')}. Show full exterior, open seating bowl, green pitch and stands. "
        f"{roof_terms[answers['roof']]}, {answers['style'].replace('_', ' ')} design with "
        f"{answers['theme'].replace('_', ' ')} motifs, {answers['palette']} "
        f"{', '.join(material.replace('_', ' ') for material in answers['materials'])} facade. "
        f"{signature_short}, public plaza and gardens. Realistic daylight, no text or logos."
    )
    from .architecture import architecture

    structured = architecture(answers, signature, seed)
    return {
        **structured,
        "title": title,
        "summary": story,
        "summary_language": "en",
        "capacity": selected["capacity"],
        "signature": signature,
        "local_prompt": local_prompt,
        "prompt_version": PROMPT_VERSION,
    }
