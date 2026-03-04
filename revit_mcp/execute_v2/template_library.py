"""
Template Library — pre-built IronPython code templates for common Revit operations.

Templates are stored in execute_v2/templates/templates.json.
Supports fuzzy search, parameter rendering, and user-defined templates.
"""

import json
import logging
import os
import re
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger("kukai.execute_v2.template_library")

# Default templates directory
TEMPLATES_DIR = Path(__file__).parent / "templates"
DEFAULT_TEMPLATES_PATH = TEMPLATES_DIR / "templates.json"


def _slugify(text: str) -> str:
    """Convert text to a URL-safe slug id."""
    text = text.lower().strip()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[\s_-]+', '_', text)
    return text.strip('_')


class TemplateLibrary:
    """Library of reusable IronPython code templates for Revit."""

    def __init__(self, templates_path: str = None):
        """
        Args:
            templates_path: Path to templates.json. Defaults to built-in templates.
        """
        self.templates_path = templates_path or str(DEFAULT_TEMPLATES_PATH)
        self._templates: List[Dict] = []
        self._load()

    def _load(self):
        """Load templates from JSON file."""
        try:
            if os.path.exists(self.templates_path):
                with open(self.templates_path, "r", encoding="utf-8") as f:
                    self._templates = json.load(f)
                logger.info("Loaded %d templates from %s", len(self._templates), self.templates_path)
            else:
                self._templates = []
                logger.warning("Templates file not found: %s", self.templates_path)
        except (json.JSONDecodeError, IOError) as e:
            logger.error("Failed to load templates: %s", e)
            self._templates = []

    def _save(self):
        """Save templates back to JSON file."""
        os.makedirs(os.path.dirname(self.templates_path), exist_ok=True)
        with open(self.templates_path, "w", encoding="utf-8") as f:
            json.dump(self._templates, f, ensure_ascii=False, indent=2)

    def search(self, query: str) -> List[Dict]:
        """
        Fuzzy search templates by name, description, and tags.

        Returns top 3 matches sorted by relevance score.
        """
        if not query:
            return []

        query_lower = query.lower()
        query_words = set(query_lower.split())
        scored = []

        for tmpl in self._templates:
            score = 0
            name_lower = tmpl.get("name", "").lower()
            desc_lower = tmpl.get("description", "").lower()
            tags = [t.lower() for t in tmpl.get("tags", [])]

            # Exact substring matches
            if query_lower in name_lower:
                score += 10
            if query_lower in desc_lower:
                score += 5

            # Word-level matches
            for word in query_words:
                if len(word) < 2:
                    continue
                if word in name_lower:
                    score += 3
                if word in desc_lower:
                    score += 2
                for tag in tags:
                    if word in tag or tag in word:
                        score += 4

            if score > 0:
                scored.append((score, tmpl))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [item[1] for item in scored[:3]]

    def get(self, template_id: str) -> Optional[Dict]:
        """Get template by ID."""
        for tmpl in self._templates:
            if tmpl.get("id") == template_id:
                return dict(tmpl)
        return None

    def render(self, template_id: str, params: Dict) -> str:
        """
        Render a template with given parameters.

        Substitutes {param_name} placeholders in code_template.

        Returns:
            Ready-to-execute IronPython code string.

        Raises:
            ValueError: If template not found.
        """
        tmpl = self.get(template_id)
        if tmpl is None:
            raise ValueError("Template not found: {}".format(template_id))

        code = tmpl.get("code_template", "")

        # Merge default params with provided overrides
        merged = dict(tmpl.get("params", {}))
        merged.update(params)

        # Simple placeholder substitution
        for key, value in merged.items():
            code = code.replace("{" + key + "}", str(value))

        return code

    def save_user_template(self, name: str, description: str, code: str, tags: List[str]) -> str:
        """
        Save a user-defined template.

        Args:
            name: Human-readable template name.
            description: What the template does.
            code: IronPython code (with optional {param} placeholders).
            tags: Search tags.

        Returns:
            Generated template ID.
        """
        template_id = _slugify(name)

        # Check for duplicates, append suffix if needed
        existing_ids = {t["id"] for t in self._templates}
        if template_id in existing_ids:
            counter = 2
            while "{}{}".format(template_id, counter) in existing_ids:
                counter += 1
            template_id = "{}{}".format(template_id, counter)

        new_template = {
            "id": template_id,
            "name": name,
            "description": description,
            "category": "Пользовательские",
            "params": {},
            "code_template": code,
            "tags": tags,
        }

        self._templates.append(new_template)
        self._save()
        logger.info("Saved user template: %s (id=%s)", name, template_id)
        return template_id

    def list_all(self) -> List[Dict]:
        """List all templates (id, name, description, tags only)."""
        return [
            {
                "id": t["id"],
                "name": t["name"],
                "description": t.get("description", ""),
                "tags": t.get("tags", []),
            }
            for t in self._templates
        ]
