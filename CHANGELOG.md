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