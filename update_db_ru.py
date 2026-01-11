
import os
import django
from django.utils import translation
from django.utils.encoding import force_str

# Setup Django environment
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "legalize_site.settings")
django.setup()

from clients.models import DocumentRequirement, DocumentType

def update_russian_names():
    translation.activate('ru')
    
    updated_count = 0
    requirements = DocumentRequirement.objects.all()
    
    print(f"Found {requirements.count()} requirements.")
    
    for req in requirements:
        try:
            # Check if it's a standard document type
            if req.document_type in DocumentType.values:
                # Get the Russian translation for this type
                # We need to temporarily force Russian override just to be sure, 
                # although activate() should cover it.
                with translation.override('ru'):
                    ru_label = force_str(DocumentType(req.document_type).label)
                
                if ru_label and req.custom_name_ru != ru_label:
                    req.custom_name_ru = ru_label
                    req.save()
                    updated_count += 1
                    print(f"Updated {req.document_type}: {ru_label}")
            else:
                print(f"Skipping custom/unknown type: {req.document_type}")
                
        except Exception as e:
            print(f"Error updating {req.id}: {e}")

    print(f"Successfully updated {updated_count} records with Russian translations.")

if __name__ == "__main__":
    update_russian_names()
