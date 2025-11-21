class PostMessageHandler:
    def handle_post_message(
        self,
        final_response: str,
    ) -> str:
        replace_variables = {
            "\\n": "\n",
        }

        for key, value in replace_variables.items():
            final_response = final_response.replace(key, value)

        return final_response
