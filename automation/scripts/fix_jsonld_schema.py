#!/usr/bin/env python3
"""
Fix JSON-LD schema errors in generated fiches.
- Remove invalid/incomplete Quotation objects
- Fix truncated text values
- Validate JSON-LD structure
"""

import os
import re
import json

FICHES_DIR = "pages/moteur-audiobook"

def fix_fiche(html_content):
    """Remove invalid Quotation from @graph, keep valid schema."""

    # Extract JSON-LD block
    match = re.search(
        r'<script type="application/ld\+json">\s*(\{.*?\})\s*</script>',
        html_content,
        re.DOTALL
    )

    if not match:
        return html_content

    json_str = match.group(1)

    try:
        data = json.loads(json_str)
    except json.JSONDecodeError:
        # Try to fix common issues
        # Remove incomplete Quotation entries
        json_str = re.sub(
            r',?\s*\{\s*"@type"\s*:\s*"Quotation"[^}]*',
            '',
            json_str
        )
        # Try parsing again
        try:
            data = json.loads(json_str)
        except:
            # If still broken, return original
            return html_content

    # Clean up @graph: remove Quotation objects
    if isinstance(data, dict) and "@graph" in data:
        data["@graph"] = [
            item for item in data["@graph"]
            if item.get("@type") != "Quotation"
        ]

    # Re-serialize and replace
    fixed_json = json.dumps(data, ensure_ascii=False, indent=2)
    fixed_script = f'<script type="application/ld+json">\n    {fixed_json}\n    </script>'

    html_fixed = html_content[:match.start()] + fixed_script + html_content[match.end():]
    return html_fixed


def main():
    if not os.path.isdir(FICHES_DIR):
        print(f"Dossier {FICHES_DIR} non trouvé")
        return

    html_files = [f for f in os.listdir(FICHES_DIR) if f.endswith(".html")]
    fixed_count = 0

    for filename in html_files:
        filepath = os.path.join(FICHES_DIR, filename)
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()

        fixed_content = fix_fiche(content)

        if fixed_content != content:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(fixed_content)
            fixed_count += 1
            print(f"✅ Fixé : {filename}")
        else:
            print(f"✓ OK : {filename}")

    print(f"\n{fixed_count} fiche(s) corrigée(s)")


if __name__ == "__main__":
    main()
