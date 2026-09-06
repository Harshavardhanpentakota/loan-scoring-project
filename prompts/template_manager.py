"""
Template Manager for Loan Document Extraction and Underwriting Prompts

This module provides functionality to load and render Jinja templates for
loan document fact extraction and underwriting evaluation summary prompts.
"""

import os
from typing import Dict, Optional
from jinja2 import Environment, FileSystemLoader, Template


class TemplateManager:
    """
    Manages Jinja templates for loan document extraction and explanation prompts.

    Loads and renders templates for loan document extraction (loan_extraction.jinja),
    grounded 3-bullet explanations (explanation.jinja), and executive evaluation
    summaries with criticality classification (evaluation_summary.jinja).
    """

    def __init__(self, template_dir: str = "prompts/templates"):
        """
        Initialize the template manager.

        Args:
            template_dir (str): Directory containing Jinja templates
        """
        self.template_dir = template_dir
        self.env = Environment(
            loader=FileSystemLoader(template_dir), trim_blocks=True, lstrip_blocks=True
        )
        self._templates: Dict[str, Template] = {}
        self._load_templates()

    def _load_templates(self):
        """Load all available .jinja templates in the template directory."""
        if not os.path.exists(self.template_dir):
            return

        for filename in os.listdir(self.template_dir):
            if filename.endswith(".jinja"):
                section_name = filename[:-6]  # Strip .jinja
                try:
                    self._templates[section_name] = self.env.get_template(filename)
                except Exception as e:
                    print(f"❌ Error loading template {filename}: {e}")

    def get_available_sections(self) -> list:
        """
        Get list of available section names.

        Returns:
            list: List of available section names
        """
        return list(self._templates.keys())

    def render_template(self, section_name: str, **kwargs) -> Optional[str]:
        """
        Render a template for a specific section.

        Args:
            section_name (str): Name of the section (basics, work, education, etc.)
            **kwargs: Template variables (e.g., text_content)

        Returns:
            Optional[str]: Rendered template string, or None if template not found
        """
        if section_name not in self._templates:
            print(f"❌ Template not found for section: {section_name}")
            print(f"Available sections: {self.get_available_sections()}")
            return None

        try:
            template = self._templates[section_name]
            return template.render(**kwargs)
        except Exception as e:
            print(f"❌ Error rendering template for {section_name}: {e}")
            return None

    def render_string(self, source: str, **kwargs) -> str:
        """Render a raw Jinja template string.

        Used for role prompt templates (criteria, system message) whose source is
        loaded from the role definition rather than the shared templates dir.
        """
        return self.env.from_string(source).render(**kwargs)
