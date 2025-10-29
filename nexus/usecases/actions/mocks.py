class mock_action_genarate_name:
    def request_action_name(self, payload):
        return {"action_name": "O que é um Chatbot"}

    def error_request_action_name(self, payload):
        return {"error": "Erro ao gerar nome"}
