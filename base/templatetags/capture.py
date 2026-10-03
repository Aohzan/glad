"""Template tag rendering a part of a template once to reuse its output."""

from django import template
from django.utils.safestring import mark_safe

register = template.Library()


class CaptureNode(template.Node):
    """Store the rendered, whitespace-collapsed content in a context variable."""

    #: Lets the blocks inside the tag be overridden by the child templates.
    child_nodelists = ("nodelist",)

    def __init__(self, nodelist, name: str):
        self.nodelist = nodelist
        self.name = name

    def render(self, context) -> str:
        # The content is rendered (hence escaped) already.
        context[self.name] = mark_safe(" ".join(self.nodelist.render(context).split()))
        return ""


@register.tag
def capture(parser, token):
    """``{% capture name %}…{% endcapture %}`` renders its content into *name*."""
    bits = token.split_contents()
    if len(bits) != 2:
        raise template.TemplateSyntaxError("Usage: {% capture name %}…{% endcapture %}")
    nodelist = parser.parse(("endcapture",))
    parser.delete_first_token()
    return CaptureNode(nodelist, bits[1])
