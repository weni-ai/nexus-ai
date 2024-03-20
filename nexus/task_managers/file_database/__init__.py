from typing import List
from abc import ABC, abstractmethod


class GPTDatabase(ABC):
    def format_output(self, text_answers):
        answers = []
        if text_answers:
            for answer in text_answers:
                answer = answer.strip()
                ans = ""
                for ch in answer:
                    if ch == '\n':
                        break
                    ans += ch
                answers.append({"text": ans})
        return answers

    @abstractmethod
    def request_gpt(self, contexts: List, question: str, language: str, content_base_uuid: str):
        pass
