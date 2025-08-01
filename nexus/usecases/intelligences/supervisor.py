from nexus.internals.billing import BillingRESTClient
from nexus.intelligences.models import Conversation
from django.utils.dateparse import parse_date, parse_datetime
from django.utils import timezone
from typing import List, Dict, Any
import datetime


class Supervisor:
    def __init__(self, billing_client: BillingRESTClient = None):
        self.billing_client = billing_client

    def _get_billing_client(self) -> BillingRESTClient:
        if self.billing_client is None:
            self.billing_client = BillingRESTClient()
        return self.billing_client

    def get_supervisor_data(self, project_uuid: str) -> List[Dict[str, Any]]:
        """Get supervisor data for a project"""
        client = self._get_billing_client()
        return client.get_supervisor_data(project_uuid)

    def _create_billing_object(self, billing_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create base billing object with default values"""

        # Convert created_on string to datetime object to match conversation data
        created_on_str = billing_data.get("created_on")
        created_on_datetime = None
        if created_on_str:
            # Try to parse as datetime first
            created_on_datetime = parse_datetime(created_on_str)
            if not created_on_datetime:
                # If that fails, try to parse as date
                created_on_date = parse_date(created_on_str)
                if created_on_date:
                    created_on_datetime = datetime.datetime.combine(created_on_date, datetime.time.min)

            # Make timezone-aware if it's not already
            if created_on_datetime and timezone.is_naive(created_on_datetime):
                created_on_datetime = timezone.make_aware(created_on_datetime)

        billing_object = {
            "created_on": created_on_datetime,
            "urn": billing_data.get("urn"),
            "uuid": None,
            "external_id": billing_data.get("id"),
            "csat": None,
            "topic": None,
            "has_chats_room": billing_data.get("human_support"),
            "start_date": billing_data.get("created_on"),
            "end_date": billing_data.get("end_on"),
            "resolution": "2",  # Mark billing data as "in_progress"
            "name": billing_data.get("name"),  # Add name field from billing data
            "is_billing_only": True
        }

        return billing_object

    def get_supervisor_data_by_date(
        self,
        project_uuid: str,
        start_date: str,
        end_date: str,
        page: int,
        user_token: str = None,
        search: str = None,
        last_external_id: str = None,
    ) -> List[Dict[str, Any]]:
        """Get supervisor data by date with conversation enrichment"""

        client = self._get_billing_client()

        # Get all conversations for this project (date filtering is handled by SupervisorViewset)
        conversations = Conversation.objects.filter(
            project__uuid=project_uuid
        ).select_related('topic').in_bulk(field_name='external_id')

        # Use the provided last_external_id as stopping point
        stop_at_external_id = last_external_id

        # Process billing data with pagination until we reach the stopping point
        supervisor_data = []
        current_page = 1
        has_more_data = True

        while has_more_data:
            # Get billing data for current page
            billing_response = client.get_billing_active_contacts(
                user_token=user_token or "",
                project_uuid=project_uuid,
                start_date=start_date,
                end_date=end_date,
                page=current_page,
                search=search,
            )

            # Extract results from the paginated response
            billing_data = billing_response.get('results', [])

            # If no results, we're done
            if not billing_data:
                break

            # Process billing data - only return billing objects that don't have conversation data
            for billing_object in billing_data:
                billing_id = billing_object.get("id")

                # Check if we've reached the stopping point
                if stop_at_external_id and str(billing_id) == stop_at_external_id:
                    has_more_data = False
                    break

                # Check if this billing object has corresponding conversation data
                has_conversation = False
                if billing_id:
                    # Try exact match first
                    if billing_id in conversations:
                        has_conversation = True
                    else:
                        # Try string conversion if needed
                        billing_id_str = str(billing_id)
                        if billing_id_str in conversations:
                            has_conversation = True

                # Only include billing objects that don't have conversation data
                if not has_conversation:
                    unified_object = self._create_billing_object(billing_object)
                    supervisor_data.append(unified_object)

            # Check if there's a next page
            if billing_response.get('next') is None:
                has_more_data = False
            else:
                current_page += 1

        return supervisor_data
