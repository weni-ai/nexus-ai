

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

    def handle_preview_post_message(
        self,
        preview_content: str,
    ) -> str:

        content_message = preview_content["content"]["message"]
        fixed_content_message = self.handle_post_message(content_message)

        preview_content["content"]["message"] = fixed_content_message

        return preview_content

    def handle_channel_post_message(
        self,
        msgs
    ):

        if isinstance(msgs, str):
            msgs = self.handle_post_message(msgs.get("msg"))
            return msgs

        for msg in msgs:
            msg["msg"]["text"] = self.handle_post_message(msg["msg"]["text"])

        return msgs
