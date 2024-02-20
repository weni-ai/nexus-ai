from trulens_eval import OpenAI
from trulens_eval import Feedback, Select
from trulens_eval.feedback import Groundedness


openai = OpenAI()


# Answer Relevance
f_qa_relevance = Feedback(
    openai.relevance_with_cot_reasons,
    name="Answer Relevance"
).on_input_output()


# Context Relevance
f_qs_relevance = Feedback(
    openai.qs_relevance_with_cot_reasons,
    name="Context Relevance"
).on_input().on(Select.RecordCalls.retrive_chunks.rets.collect())


# Groundedness
grounded = Groundedness(groundedness_provider=openai)
f_groundedness = (
    Feedback(grounded.groundedness_measure_with_cot_reasons, name = "Groundedness")
    .on(Select.RecordCalls.retrive_chunks.rets.collect())
    .on_output()
    .aggregate(grounded.grounded_statements_aggregator)
)
