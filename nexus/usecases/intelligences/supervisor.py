from nexus.internals.billing import BillingRESTClient

from nexus.intelligences.models import Conversation


class Supervisor:
    def __init__(
        self,
        billing_client: BillingRESTClient = None
    ):
        self.billing_client = billing_client

    def _get_billing_client(self) -> BillingRESTClient:
        if self.billing_client is None:
            self.billing_client = BillingRESTClient()
        return self.billing_client

    def get_supervisor_data(
        self,
        project_uuid: str,
    ):
        client = self._get_billing_client()
        return client.get_supervisor_data(project_uuid)

    def get_supervisor_data_by_date(
        self,
        project_uuid: str,
        start_date: str,
        end_date: str,
        page: int,
    ):
        client = self._get_billing_client()

        # Get billing data
        billing_data = client.get_supervisor_data_by_date(
            project_uuid,
            start_date,
            end_date,
            page
        )

        # Get conversation data
        conversation_data = Conversation.objects.filter(
            project_uuid=project_uuid,
            created_at__gte=start_date,
            created_at__lte=end_date
        )

        # Create a empty list to store all the correct data
        supervisor_data = []

        # Verify if the billing objects exists on the conversation data
        for billing_object in billing_data:
            conversation = conversation_data.filter(external_id=billing_object.get("id")).first()
            # If a conversation object of the billing data exists, add it to the list with some of the conversation fields (csat, topic)
            if conversation:
                supervisor_data.append({
                    "created_on": conversation.created_at,
                    "urn": conversation.message.urn,
                    "uuid": conversation.uuid,
                    "csat": conversation.csat,
                    "topic": conversation.topic
                })
            else:
                # If not exists add the object to the list with only the billing data itself
                supervisor_data.append(billing_object)

        return supervisor_data
