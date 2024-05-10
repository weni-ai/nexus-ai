# import numpy as np
# from django.conf import settings

# from trulens_eval import (
#     Feedback,
#     OpenAI,
#     Tru,
#     Select,
#     TruCustomApp,
# )
# from trulens_eval.feedback import Groundedness
# from trulens_eval.tru_custom_app import instrument

# from nexus.intelligences.models import ContentBaseLogs

# openai = OpenAI()
# tru = Tru(database_url=settings.TRULENS_DATABASE_URL)


# class WeniGPTLogEvaluation:
#     """
#     WeniGPTLogEvaluation is a helper class,
#     "Trulens" evaluates from @instrument decorator,
#     using input and output from the methods,
#     since we are using logs, this class returns
#     the values that would come from RAG
#     """

#     @instrument
#     def get_chunks(self, log):
#         return log.texts_chunks

#     @instrument
#     def get_question(self, log):
#         return log.question

#     @instrument
#     def get_answer(self, question: str, log: ContentBaseLogs):
#         self.get_question(log)
#         self.get_chunks(log)
#         return log.answer


# # Feedback Functions

# f_qa_relevance = Feedback(
#     openai.relevance_with_cot_reasons,
#     name="Answer Relevance"
# ).on(Select.RecordCalls.get_answer.args.question).on_output()

# # Groundedness
# grounded = Groundedness(groundedness_provider=openai)
# f_groundedness = (
#     Feedback(grounded.groundedness_measure_with_cot_reasons, name="Groundedness")
#     .on(Select.RecordCalls.get_chunks.rets.collect())
#     .on_output()
#     .aggregate(grounded.grounded_statements_aggregator)
# )

# # Question/statement relevance between question and each context chunk.
# f_context_relevance = (
#     Feedback(openai.qs_relevance_with_cot_reasons, name="Context Relevance")
#     .on(Select.RecordCalls.get_question.rets)
#     .on(Select.RecordCalls.get_chunks.rets.collect())
#     .aggregate(np.mean)
# )

# wenigpt_evaluation = WeniGPTLogEvaluation()
# tru_recorder = TruCustomApp(
#     wenigpt_evaluation,
#     app_id=f"WeniGPT v{settings.WENIGPT_VERSION}",
#     feedbacks=[f_qa_relevance, f_context_relevance, f_groundedness]
# )
