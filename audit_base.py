import re
with open(r"c:\Users\aliss\Desktop\Raya System\templates\base.html", "r", encoding="utf-8") as f:
    content = f.read()

pages_in_base = set()
for match in re.finditer(r"has_page\s*\(\s*['\"]([^'\"]+)['\"]\s*\)", content):
    pages_in_base.add(match.group(1))

from audit_permissions import PAGES_REGISTRY

registry_pages = set(PAGES_REGISTRY.keys())
print("Pages in Registry NOT checked in base.html:", registry_pages - pages_in_base)
