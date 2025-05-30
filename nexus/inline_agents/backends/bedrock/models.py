import json

from django.db import models


class Supervisor(models.Model):
    created_on = models.DateTimeField(auto_now_add=True)
    name = models.CharField(max_length=255)
    instruction = models.TextField()
    foundation_model = models.CharField(max_length=255)
    prompt_override_configuration = models.JSONField()
    action_groups = models.JSONField()
    knowledge_bases = models.JSONField()

    human_support_prompt = models.TextField(null=True, blank=True)
    human_support_action_groups = models.JSONField(null=True, blank=True)

    components_prompt = models.TextField(null=True, blank=True)
    components_human_support_prompt = models.TextField(null=True, blank=True)

    @property
    def action_groups_list(self):
        action_groups = []

        for action_group in self.action_groups:
            action_group_dict = {}
            action_group_dict['action_group_name'] = action_group.get('actionGroupName')
            ag_executor = action_group.get('actionGroupExecutor')
            if ag_executor:
                ag_executor_lambda = ag_executor.get('lambda')
                action_group_dict['action_group_arn'] = ag_executor_lambda

            action_groups.append(action_group_dict)

        return json.dumps(action_groups, indent=4)

    @property
    def human_support_action_groups_list(self):
        action_groups = []

        for action_group in self.human_support_action_groups:
            action_group_dict = {}
            action_group_dict['action_group_name'] = action_group.get('actionGroupName')
            ag_executor = action_group.get('actionGroupExecutor')
            if ag_executor:
                ag_executor_lambda = ag_executor.get('lambda')
                action_group_dict['action_group_arn'] = ag_executor_lambda

            action_groups.append(action_group_dict)

        return json.dumps(action_groups, indent=4)