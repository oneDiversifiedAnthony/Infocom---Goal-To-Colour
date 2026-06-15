"""Add colour names to each RGB entry in countries.json."""

import json
import math
import os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
JSON_PATH = os.path.join(SCRIPT_DIR, "countries.json")

# Named colours with RGB values
NAMED_COLOURS = {
    "White": (255, 255, 255),
    "Black": (0, 0, 0),
    "Red": (255, 0, 0),
    "Dark Red": (139, 0, 0),
    "Maroon": (128, 0, 0),
    "Crimson": (220, 20, 60),
    "Scarlet": (206, 17, 38),
    "Green": (0, 128, 0),
    "Dark Green": (0, 100, 0),
    "Forest Green": (0, 100, 60),
    "Lime Green": (30, 181, 58),
    "Blue": (0, 0, 255),
    "Dark Blue": (0, 0, 139),
    "Navy": (0, 0, 128),
    "Royal Blue": (0, 56, 168),
    "Sky Blue": (108, 172, 228),
    "Cerulean": (0, 129, 194),
    "Yellow": (255, 255, 0),
    "Gold": (255, 206, 0),
    "Amber": (255, 191, 0),
    "Orange": (255, 165, 0),
    "Dark Orange": (245, 131, 24),
    "Teal": (0, 106, 167),
    "Indigo": (60, 59, 110),
    "Burgundy": (128, 0, 32),
    "Coral Red": (218, 41, 28),
}


def colour_distance(c1, c2):
    """Weighted Euclidean distance (human perception weights)."""
    r1, g1, b1 = c1
    r2, g2, b2 = c2
    return math.sqrt(2 * (r1 - r2) ** 2 + 4 * (g1 - g2) ** 2 + 3 * (b1 - b2) ** 2)


def closest_colour_name(rgb):
    r, g, b = rgb
    min_dist = float("inf")
    best_name = "Unknown"
    for name, ref in NAMED_COLOURS.items():
        d = colour_distance((r, g, b), ref)
        if d < min_dist:
            min_dist = d
            best_name = name
    return best_name


def main():
    with open(JSON_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    for country, info in sorted(data["teams"].items()):
        colours = info.get("colours", [])
        named = []
        for rgb in colours:
            name = closest_colour_name(rgb[:3])
            named.append(name)
        print(f"{country:25s}  {named}")

        # Update: append name as 4th element
        new_colours = []
        for rgb in colours:
            name = closest_colour_name(rgb[:3])
            new_colours.append([rgb[0], rgb[1], rgb[2], name])
        info["colours"] = new_colours

    with open(JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"\nUpdated: {JSON_PATH}")


if __name__ == "__main__":
    main()
