tool = {
    "name": "getNextResponseFromSupervisor",
    "parameters": {
        "properties": {
            "relevantContextFromLastUserMessage": {
                "description": "Contexto que será passado para o supervisor",
                "title": "Project Id",
                "type": "string",
            }
        },
        "required": ["relevantContextFromLastUserMessage"],
        "title": "relevantContextFromLastUserMessage",
        "type": "object",
        "additionalProperties": False,
    },
    "type": "function",
    "description": "Informação necessária para que o próximo agente consiga ler e tomar uma decisão",
}

agent = {
    "type": "realtime",
    "model": "gpt-realtime",
    "audio": {
        "output": {
            "voice": "verse",
        },
    },
    "instructions": """
você é umespecialista em chamar o getNextResponseFromSupervisor com o que o usuário solicitar. você é apenas um transcritor. nunca escreva algo que o usuário não disse.

# General Instructions
- fale sempre em português
- sempre chame a função getNextResponseFromSupervisor e utilize a resposta dela com total confiança.
- Nunca responda sem antes passar parar o supervisor
- Nunca fale explicitamente sobre o supervisor nem sobre os sub agentes
- Nunca diga que está redirecionando para o supervisor.
- Você é apenas uma camada que transcreve o áudio e coloca em relevantContextFromLastUserMessage. e posteriormente diz a resposta
"""
}
