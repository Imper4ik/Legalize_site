from django import template

register = template.Library()

@register.filter
def get_by_type(documents, doc_type):
    return documents.filter(doc_type=doc_type).first()
