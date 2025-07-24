import pendulum


class MockBillingRESTClient:

    def get_billing_active_contacts(self, project_uuid, start_date, end_date, page, user_token=None):
        return {
            "count": 8326,
            "next": f"http://<base_url>/v1/{project_uuid}/conversations/?end={end_date}&page={page}&start={start_date}",
            "previous": None,
            "results": [
                {
                    "id": 0,
                    "created_on": pendulum.now().subtract(days=1).to_datetime_string(),
                    "human_support": False,
                    "urn": "whatsapp:5511999999999",
                    "end_on": pendulum.now().to_datetime_string()
                },
                {
                    "id": 1,
                    "created_on": pendulum.now().subtract(days=1).to_datetime_string(),
                    "human_support": True,
                    "urn": "whatsapp:5511999999999",
                    "end_on": pendulum.now().to_datetime_string()
                }
            ]
        }


class MockBillingRESTClientMultiPage:
    """Mock billing client that supports pagination with multiple pages"""

    def __init__(self, total_pages=3, items_per_page=5):
        self.total_pages = total_pages
        self.items_per_page = items_per_page
        self.total_items = total_pages * items_per_page

    def get_billing_active_contacts(self, project_uuid, start_date, end_date, page, user_token=None):
        page = int(page) if page else 1

        # Generate items for this page
        results = []
        start_id = (page - 1) * self.items_per_page

        for i in range(self.items_per_page):
            item_id = start_id + i
            if item_id >= self.total_items:
                break

            results.append({
                "id": item_id,
                "created_on": pendulum.now().subtract(days=item_id).to_datetime_string(),
                "human_support": item_id % 2 == 0,  # Alternate between True/False
                "urn": f"whatsapp:5511{str(item_id).zfill(8)}",
                "end_on": pendulum.now().subtract(days=item_id - 1).to_datetime_string()
            })

        # Determine next and previous URLs
        next_url = None
        previous_url = None

        if page < self.total_pages:
            next_url = f"http://<base_url>/v1/{project_uuid}/conversations/?end={end_date}&page={page + 1}&start={start_date}"

        if page > 1:
            previous_url = f"http://<base_url>/v1/{project_uuid}/conversations/?end={end_date}&page={page - 1}&start={start_date}"

        return {
            "count": self.total_items,
            "next": next_url,
            "previous": previous_url,
            "results": results
        }
