from rest_framework.throttling import UserRateThrottle


class CodeExecutionThrottle(UserRateThrottle):
    scope = "code_execution"


class CodeSubmissionThrottle(UserRateThrottle):
    scope = "code_submission"


class AIGenerationThrottle(UserRateThrottle):
    scope = "ai_generation"