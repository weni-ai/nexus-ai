import json

from django.forms import Textarea


class PrettyJSONWidget(Textarea):
    def render(self, name, value, attrs=None, renderer=None):
        if value and isinstance(value, str):
            try:
                # Parse the JSON string and then re-format it with indentation
                value_dict = json.loads(value)
                value = json.dumps(value_dict, indent=2)
            except json.JSONDecodeError:
                pass
        elif value and not isinstance(value, str):
            # If it's already a dict or list, just format it
            value = json.dumps(value, indent=2)

        # Call the parent class's render method with the formatted JSON
        return super().render(name, value, attrs, renderer)


class ArrayJSONWidget(PrettyJSONWidget):
    """Widget for ArrayField containing JSONField that properly handles JSON array conversion"""

    def value_from_datadict(self, data, files, name):
        """Convert JSON string back to Python list for ArrayField"""
        value = data.get(name)
        if value is None:
            return None
        if value == "":
            return []
        try:
            parsed = json.loads(value)
            if not isinstance(parsed, list):
                return [parsed] if parsed else []
            return parsed
        except (json.JSONDecodeError, TypeError):
            return []
