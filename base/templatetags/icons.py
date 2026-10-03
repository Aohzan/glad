"""Lucide icons rendered from the self-hosted SVG sprite.

Registered as a template builtin, so ``{% icon %}`` works without ``{% load %}``.
"""

from django import template
from django.templatetags.static import static
from django.utils.html import format_html
from django.utils.safestring import mark_safe

register = template.Library()

SPRITE_PATH = "vendors/lucide/sprite.svg"


@register.simple_tag
def icon(name: str, css_class: str = "", label: str = "", size: int | None = None):
    """Inline SVG referencing the Lucide symbol *name*.

    The icon is decorative unless *label* is given, in which case it is
    exposed to assistive technologies under that name. *size* (pixels)
    overrides the default ``1em`` box.
    """
    classes = f"g-icon {css_class}".strip()
    size_attrs = format_html(' width="{0}" height="{0}"', size) if size else ""
    a11y = (
        format_html(' role="img" aria-label="{}"', label)
        if label
        else mark_safe(' aria-hidden="true"')
    )
    return format_html(
        '<svg class="{}"{}{} focusable="false"><use href="{}#{}"></use></svg>',
        classes,
        size_attrs,
        a11y,
        static(SPRITE_PATH),
        name,
    )
