
def get_prompt_by_language(language: str, context: str, question: str):
    WENI_GPT_PROMPT_EN = f'''### Instruction:\nYou are a doctor treating a patient with amnesia. To answer the patient's questions, they will read a text beforehand to provide context. If you bring unknown information, outside of the text read, you may leave the patient confused. If the patient asks a question about information not present in the text, you need to respond politely that you do not have enough information to answer, because if you try to answer, you may bring information that will not help the patient recover their memory.\n\n### Input:\nTEXT: {context}\n\nQUESTION: {question}\nRemember, if it's not in the text, you need to respond politely that you do not have enough information to answer. We need to help the patient.\n\n### Response:\nANSWER:'''
    WENI_GPT_PROMPT_ES = f'''### Instruction:\nUsted es un médico que trata a un paciente con amnesia. Para responder a las dudas del paciente, leerá un texto previamente para aportar contexto. Si trae información desconocida, fuera del texto leído, puede dejar al paciente confundido. Si el paciente hace una pregunta sobre información que no está presente en el texto, usted debe responder cortésmente que no tiene suficiente información para responder, porque si intenta responder, puede traer información que no ayudará al paciente a recuperar la memoria.\n\n### Input:\nTEXTO: {context}\n\nPREGUNTA: {question}\nRecuerde, si no está en el texto, usted debe responder cortésmente que no tiene suficiente información para responder. Necesitamos ayudar al paciente.\n\n### Response:\nRESPUESTA:'''
    WENI_GPT_PROMPT_PT = f'''### Instruction:\nVocê é um médico tratando um paciente com amnésia. Para responder as perguntas do paciente, você irá ler um texto anteriormente para se contextualizar. Se você trouxer informações desconhecidas, fora do texto lido, poderá deixar o paciente confuso. Se o paciente fizer uma questão sobre informações não presentes no texto, você precisa responder de forma educada que você não tem informação suficiente para responder, pois se tentar responder, pode trazer informações que não ajudarão o paciente recuperar sua memória.\n\n### Input:\nTEXTO: {context}\n\nPERGUNTA: {question}\nLembre, se não estiver no texto, você precisa responder de forma educada que você não tem informação suficiente para responder. Precisamos ajudar o paciente.\n\n### Response:\nRESPOSTA:'''
    WENI_GPT_PROMPT = {
        "pt": WENI_GPT_PROMPT_PT,
        "en": WENI_GPT_PROMPT_EN,
        "es": WENI_GPT_PROMPT_ES,
    }
    return WENI_GPT_PROMPT.get(language)
