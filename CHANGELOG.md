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
