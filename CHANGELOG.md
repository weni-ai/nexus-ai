# 2.8.6
## *Update*
    - Change zeroshot from internal communication to function calling
    - Change default zeroshot classifier on routing to function calling classifier

# 2.8.5
## *Add*
    - Small improvements to the commerce route api

# 2.8.4
## *Fix*
    - OpenAI class instance not handleling api_token

# 2.8.3
## *Fix*
    - Missing RecentActivities api filters
    - Brain_on status update not showing up on RecentActivities API

# 2.8.2
## *Fix*
    - Change message type in message preview when Task revoked

# 2.8.1
## *Fix*
    - Update router task to enable msg queueing

# 2.8.0
## *Add*
    - Send llm response to actions

# 2.7.1
## *Add*
    - New commerce all in one customization api

## *Fix*
    - Update Flow not working properly
    - Custom classfier model for specific projects

# 2.7.0
## *Add*
    - Experience manger endpoints. List logs, tags and more.
    - Redis for last 5 messages.
    - Websocket for incoming messages.

## *Update*
    - Now you can update actions uuid.

# 2.6.8
## *Fix*
    - Commerce custom template actions not working

# 2.6.7
## *Fix*
    - Missing classification on serializer
    - Reflection regex not supporting failed messages

# 2.6.6
## *Fix*
    - Routing and Preview not working for specific actions
    - top_k typing

# 2.6.5
## *Update*
    - It's now possible to have multiple Flow's pointing to differente flow uuid.

## *Fix*
    - Issues with message history params not working properly
    - Some event driven message not normalized before update

# 2.6.4
## *Add*
    - MessageLog field source to select logs from preview/router
    - Message history api
    - MessageLog tag analytics

## *Fix*
    - Small pep8 fixes
    - Recent Activities model name params

## *Deleted*
    - Tru lens unused code

# 2.6.3
## *Fix*
    - fix crud for content AI

# 2.6.2
## *Fix*
    - playwright install in docker build

# 2.6.1
## *Fix*
    - Install playwright dependencies

# 2.6.0
## *Add*
    - Reflection step after the user message
    - Groundedness classification on the user message

# 2.5.1
## *Fix*
    - install playwright in docker build

# 2.5.0
## *Add*
    - Bedrock Knowledge Bases

# 2.4.0
## *Add*
    -Accept attachments in preview
# *Fix*
    - Encoding chunk pages error
    - Recent activities token visualization

# 2.3.1
## *Update*
    - IntegratedFeature current_version_setup is now a list of dicts
    - Handle multiple flows integrations

# 2.3.0
## *Add*
    - Zeroshot client

# 2.2.1
## *Fix*
    - Customization activities

# 2.2.0
## *Add*
    - New recent activities
## *Fix*
    - Prompt guard response
    - Missing action details on recent activities

# 2.1.1
## *Fix*
    - Wrong message statement on safeguard methods

# 2.1.0
## *Add*
    - More super user type tokens
    - Prompt Guard llm model, responsible to handle injection attacks
    - Update retail usecase
    - Template action on retail usecases
## *Update*
    - Refactor start_route method
    - Refactor preview method

# 2.0.6
## *Fix*
    - Last message bringing wrong classification messages
    - Ordering after filter routing user last messages

# 2.0.5
## *Fix*
    - Attachment flow start condition

# 2.0.4
## *Fix*
    - Fix action contraints.
## *Add*:
    - SafeCheck model

# 2.0.3
## *Remove*
    - OpenAI function calling

# 2.0.2
## *Fix*
    - Direct_message validation fix

# 2.0.1
## *Add*
    - Add template attachment handler
## *Fix*
    - TemplateAction and Flow model relation

# 2.0.0
## *Add*
    - New TemplateActions models
    - Change communication with mailroom for different actions
    - New fields on actions to define groups and template usage

# 1.10.2
## *Fix*
    - Missing classifier class logs
    - Remove language instruction

# 1.10.1
## *Fix*
    - Fix request_bedrock response

# 1.10.0
## *Add*
    - Create and delete methods to retail application

# 1.9.0
## *Add*
    - invoke_model method to wenigpt

# 1.8.5
## *Fix*
    - ContentBaseLogs answer property

# 1.8.4
## *Fix*
    - Move docs page to /docs, leave / as healthcheck endpoint
# 1.8.3
## *Fix*
    - Fix missing statement on project consumer

# 1.8.2
## *Fix*
    - Add missing rule where you can only have 1 router per project in IntegratedIntelligence model

# 1.8.1
## *Fix*
    - Fix updating name action syntax

# 1.8.0
## *Add*
    - Generate action name use LLM model
    - Sentry app and filter exceptions
## *Update*
    - Check Bearer syntax on prometheus middleware

# 1.7.1
## *Fix*
    - Check project permission on projects updates.

# 1.7.0
## *Add*
    - Return created_at on multiple intelligences api
## *Remove*
    - Add pragma: no cover to files that contains external calls removing it from coverage
## *Fix*
    - Missing permissions unittests
    - Add new permission check for document preview api

# 1.6.0
## *Add*:
    - Document API preview.
## *Fix*:
    - Filename errors when creating a ContentBaseText with a project that has a name with special characters
    - Message history bringing first 5 messages insteado of the 5 last messages

# 1.5.3
## *Add*
    - WeniGPT model for test

# 1.5.2
## *Fix*
    - Missing brain_on log
    - Healthcheck for external llm aplications
    - Metrics endpoint on prometheus format
    - Action now use project auth instead of org auth

# 1.5.1
## *Fix*
    - get_file_info, last_messages as empty list intead of None
    - null actions

# 1.5.0
## *Add*
    - Function calling on router method
    - Wenigpt multi turn conversation
    - wenigpt shark model

## *Update*
    - Refactor function classifier using dependency injection

## *Fix*
    - Exception handler when missing project auth

# 1.4.0
## *Add*
    - allow flows module to request customization endpoint

# 1.3.1
## *Fix*
    - Wenigpt default llm: Add top_k, change hardcoded values to environment variables

# 1.3.0
## *Add*
    - OpenAI function calling for llm
    - Possibility to use ChatGPT on specific projects
## *Update*
    - Default WeniGPT version to "Golfinho"
## *Delete*
    - WeniGPT model version "Boto" removed from the current llm default setup
## *Fix*
    - ChatGPT message to send "assistant" instead of "system"

# 1.2.1
## *Fix*
    - Missing user instance on content base observer

# 1.2.0
## *Add*
    - Create APM service to track the repository endpoints overall performance
    - RecentActivities model to track changes on brain structure models (LLM, Intelligences, Contentbase, Links, Text and Documents)
    - Create a routine to delete Recent activities data after 3 months
    - New observer architecture to create events whenever a model is updated

# 1.1.0
## *Update*
    - Update permissions to check project permission instead of organization permission

# 1.0.26
## *Fix*
    - Flake8 corrections
    - Reference before assignment on IntegratedIntelligence
## *Add*
    - Sentry configuration for debug
