from django import template
from django.template.defaultfilters import stringfilter

register = template.Library()


@register.filter
@stringfilter
def replace_with_space(value, arg):
    """Removes all values of arg from the given string"""
    return value.replace(arg, ' ')
