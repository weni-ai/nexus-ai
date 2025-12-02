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
