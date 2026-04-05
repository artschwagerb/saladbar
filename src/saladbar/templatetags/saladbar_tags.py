from django import template

from saladbar.conf import get_base_template

register = template.Library()


@register.simple_tag
def saladbar_base_template():
    """Return the configured base template path for use in {% extends %}."""
    return get_base_template()
