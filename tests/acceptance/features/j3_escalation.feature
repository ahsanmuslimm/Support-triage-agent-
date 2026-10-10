Feature: J3 - Escalation with Context
  Scenario: Multiple failed resolution attempts
    @pending
    Given a customer has had 3 failed resolution attempts
    When they send another message
    Then the system escalates to a senior agent
    And the agent receives full context including all messages
